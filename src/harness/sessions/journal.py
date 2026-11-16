"""Journal de session : JSONL en ajout seul, reprise robuste (ADR-0012 §1-§4).

Notion : sessions-et-journal (docs/notions/).

Le journal est la source de vérité de la session : ce que le modèle voit à la reprise est
reconstruit depuis lui. Chaque entrée est écrite d'un seul `write` sur un descripteur
`O_APPEND`, dès qu'elle se produit : un arrêt brutal perd au plus l'entrée en cours.
Les entrées sont chaînées par `parentId` : la branche active se reconstitue en remontant
depuis la dernière entrée écrite, ce qui rendra les branches possibles sans rien réécrire.

La lecture n'interprète les anomalies qu'en lecture seule ; les réparations (ligne
tronquée, appel sans résultat) sont des **ajouts**, faits au premier ajout de la session.
"""

import json
import os
import secrets
import shutil
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from harness.cost import CostTracker
from harness.session import NOT_REQUESTS, RestoredState, StoreError
from harness.tools.outputs import RESERVED_DIR, ensure_gitignore, redact, tidy

FORMAT = 1
SESSIONS_DIR = "sessions"
ORPHAN_RESULT = "error: action interrompue, état inconnu"
HEARTBEAT_S = 10  # ADR-0012 §3 : le bail est renouvelé toutes les 10 s au plus

# Séparateurs de ligne que `json.dumps` n'échappe pas : ils couperaient une entrée en
# deux pour un lecteur qui découpe avec `str.splitlines()`.
_STRUCTURE = frozenset({"id", "parentId", "ts", "type", "kind", "session", "workdir"})
_LINE_SEPARATORS = {"\u2028": "\\u2028", "\u2029": "\\u2029", "\x85": "\\u0085"}


class JournalError(StoreError):
    """Journal inutilisable ; le message est destiné à l'utilisateur (en français)."""


# ---------------------------------------------------------------------- verrou


class SessionLock:
    """Verrou à bail : un fichier `<id>.lock` créé en `O_EXCL` et renouvelé (ADR-0012 §3).

    Un processus tué brutalement ne libère rien : le verrou devient périmé, soit parce que
    son bail a expiré, soit parce que son processus n'existe plus (même hôte). On ne
    s'appuie sur aucune sémantique de verrou du système de fichiers (`flock`).
    """

    def __init__(self, path: Path, stale_s: float):
        self._path = path
        self._stale_s = stale_s
        self._token = secrets.token_hex(8)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(self) -> bool:
        for _ in range(2):
            if self._create():
                self._start_heartbeat()
                return True
            if not self.is_stale():
                return False
            # Reprise d'un verrou périmé : le renommage est atomique, un seul gagnant.
            graveyard = self._path.with_name(f"{self._path.name}.{self._token}.stale")
            try:
                os.rename(self._path, graveyard)
            except OSError:
                return False
            graveyard.unlink(missing_ok=True)
        return False

    def owned(self) -> bool:
        """Ce processus détient-il encore le verrou ? (repris par un autre : non)"""
        return self._owned()

    def release(self) -> None:
        self._stop.set()
        if self._owned():
            self._path.unlink(missing_ok=True)

    def _create(self) -> bool:
        try:
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w") as handle:
            json.dump(
                {
                    "token": self._token,
                    "hostname": socket.gethostname(),
                    "pid": os.getpid(),
                },
                handle,
            )
        return True

    def _owned(self) -> bool:
        try:
            return json.loads(self._path.read_text())["token"] == self._token
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def is_stale(self) -> bool:
        try:
            age = time.time() - self._path.stat().st_mtime
            if age > self._stale_s:
                return True
            holder = json.loads(self._path.read_text())
            return holder["hostname"] == socket.gethostname() and not _pid_alive(
                holder["pid"]
            )
        except FileNotFoundError:
            return True  # libéré entre-temps : on peut le prendre
        except (OSError, ValueError, KeyError, TypeError):
            return False  # contenu en cours d'écriture : le bail frais protège

    def _start_heartbeat(self) -> None:
        interval = min(HEARTBEAT_S, self._stale_s / 3)

        def beat() -> None:
            # Fil dédié, pas la boucle asyncio : elle peut être bloquée par un outil.
            while not self._stop.wait(interval):
                if not self._owned():
                    return  # le verrou a été repris par un autre
                try:
                    os.utime(self._path)
                except OSError:
                    return

        self._thread = threading.Thread(target=beat, daemon=True)
        self._thread.start()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --------------------------------------------------------------------- lecture


@dataclass
class _Parsed:
    header: dict
    entries: list[dict]  # entrées valides, dans l'ordre du fichier
    warnings: list[str] = field(default_factory=list)
    skipped_line: int | None = None  # ligne finale ignorée, à marquer au premier ajout
    needs_newline: bool = False  # la ligne ignorée n'est pas terminée par `\n`


@dataclass(frozen=True)
class SessionInfo:
    """Une ligne de la liste des sessions (spec §4.2)."""

    id: str
    last_activity: float  # date de modification du journal (ADR-0012 §5)
    first_request: str
    requests: int
    cost: str
    model: str
    busy: bool


def _directory(workdir: Path) -> Path:
    return workdir / RESERVED_DIR / SESSIONS_DIR


def _parse(path: Path) -> _Parsed:
    """Lit un journal sans rien modifier ; refuse (`JournalError`) ce qui est inutilisable."""
    label = f"Session {path.stem}"
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if not raw.strip():
        raise JournalError(f"{label} : le journal est vide (aucun en-tête).")
    terminated = raw.endswith("\n")
    lines = raw.split("\n")
    if terminated:
        lines.pop()
    header = _json_object(lines[0])
    if header is None or header.get("type") != "header":
        raise JournalError(f"{label} : en-tête illisible (première ligne du journal).")
    if header.get("format") != FORMAT:
        raise JournalError(
            f"{label} : version de format inconnue ({header.get('format')!r}) ; "
            f"ce harness lit le format {FORMAT}."
        )
    if not all(isinstance(header.get(k), str) for k in ("session", "workdir", "model")):
        raise JournalError(f"{label} : en-tête illisible (champs manquants).")

    decoded = [(n, _entry(text)) for n, text in enumerate(lines[1:], start=2) if text]
    # Une ligne invalide désignée par une entrée `skipped_line` est une réparation passée.
    repaired = {
        e["line"]
        for _, e in decoded
        if e and e["type"] == "state" and e.get("kind") == "skipped_line"
    }
    parsed = _Parsed(header, [])
    seen: set[int] = set()
    for index, (number, entry) in enumerate(decoded):
        last = index == len(decoded) - 1
        if entry is None:
            if last:
                parsed.warnings.append(
                    f"{label} : la ligne {number} du journal est tronquée, elle est ignorée."
                )
                parsed.skipped_line = number
                parsed.needs_newline = not terminated
            elif number not in repaired:
                raise JournalError(
                    f"{label} : la ligne {number} du journal est invalide (JSON illisible)."
                )
            continue
        if entry["parentId"] is not None and entry["parentId"] not in seen:
            raise JournalError(
                f"{label} : la ligne {number} désigne une entrée inexistante "
                f"(parentId {entry['parentId']})."
            )
        seen.add(entry["id"])
        parsed.entries.append(entry)
    if not parsed.entries:
        raise JournalError(f"{label} : le journal ne contient aucune conversation.")
    return parsed


def _json_object(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _entry(text: str) -> dict | None:
    entry = _json_object(text)
    valid = (
        entry is not None
        and isinstance(entry.get("id"), int)
        and (entry.get("parentId") is None or isinstance(entry["parentId"], int))
        and isinstance(entry.get("type"), str)
    )
    return entry if valid else None


def _active_chain(entries: list[dict]) -> list[dict]:
    """Branche active : de la dernière entrée écrite jusqu'à la racine."""
    by_id = {e["id"]: e for e in entries}
    chain: list[dict] = []
    cursor: dict | None = entries[-1]
    while cursor is not None:
        chain.append(cursor)
        parent = cursor["parentId"]
        cursor = by_id[parent] if parent is not None else None
    chain.reverse()
    return chain


def _orphan_calls(messages: list[dict]) -> list[str]:
    """Identifiants des appels d'action restés sans résultat (arrêt brutal)."""
    pending: dict[str, None] = {}
    for message in messages:
        if message.get("role") == "assistant":
            for tool_call in message.get("tool_calls") or []:
                pending[tool_call["id"]] = None
        elif message.get("role") == "tool":
            pending.pop(message.get("tool_call_id", ""), None)
    return list(pending)


def resolve(workdir: Path, ref: str) -> str:
    """Identifiant complet de la session désignée par `ref` (identifiant ou préfixe)."""
    directory = _directory(workdir)
    known = sorted(p.stem for p in directory.glob("*.jsonl"))
    matches = [i for i in known if ref and i.startswith(ref)]
    if ref in matches:
        return ref
    if not matches:
        raise JournalError(
            f"Session inconnue dans ce dossier : '{ref}'. "
            "Listez les sessions du dossier avec --sessions."
        )
    if len(matches) > 1:
        raise JournalError(
            f"Préfixe '{ref}' ambigu : sessions candidates {', '.join(matches)}. "
            "Donnez un préfixe plus long."
        )
    return matches[0]


def list_sessions(
    workdir: Path, host_workdir: str, lock_stale_s: float
) -> list[SessionInfo]:
    """Sessions lisibles du dossier, de la plus récente à la plus ancienne."""
    infos = []
    for path in _directory(workdir).glob("*.jsonl"):
        try:
            parsed = _parse(path)
            last_activity = path.stat().st_mtime
        except (JournalError, OSError):
            continue  # vide, en-tête seul, illisible : ni listé ici (spec §6)
        if parsed.header["workdir"] != host_workdir:
            continue
        chain = _active_chain(parsed.entries)
        requests = [
            e["message"]["content"]
            for e in chain
            if e["type"] == "message"
            and e["message"].get("role") == "user"
            and e["message"].get("content") not in NOT_REQUESTS
        ]
        cost = CostTracker()
        model = parsed.header["model"]
        for entry in parsed.entries:
            if entry["type"] == "usage":
                cost.add(entry["cost_usd"], entry["usage"])
            elif entry["type"] == "state" and entry.get("kind") == "model_changed":
                model = entry["model"]
        infos.append(
            SessionInfo(
                path.stem,
                last_activity,
                " ".join(str(requests[0]).split())[:60] if requests else "",
                len(requests),
                cost.display(),
                model,
                _is_busy(path.with_suffix(".lock"), lock_stale_s),
            )
        )
    return sorted(infos, key=lambda info: info.last_activity, reverse=True)


def _is_busy(lock_path: Path, stale_s: float) -> bool:
    return lock_path.exists() and not SessionLock(lock_path, stale_s).is_stale()


# --------------------------------------------------------------------- journal


class Journal:
    def __init__(
        self,
        directory: Path,
        header: dict,
        *,
        written: bool,
        lock_stale_s: float,
        next_id: int = 1,
        head: int | None = None,
        model: str = "",
        secrets_: tuple[str, ...] = (),
    ):
        self._secrets = secrets_  # valeurs masquées à l'écriture (CA-S4)
        self._messages: dict[int, dict] = {}  # entrées `message`, pour /branch
        self._directory = directory
        self._header = header
        self._written = written  # le fichier existe : l'en-tête n'est plus à écrire
        self._pending: list[dict] = []
        self._next_id = next_id
        self._head = head
        self._parents: dict[int, int | None] = {}
        self._model = model  # modèle actif, consigné sur les messages assistant
        self._lock = SessionLock(directory / f"{header['session']}.lock", lock_stale_s)
        self._lock_stale_s = lock_stale_s
        # Réparations à ajouter avant le premier ajout de la session (jamais de réécriture).
        self._repair_line: int | None = None
        self._prefix = ""  # `\n` qui ferme une ligne tronquée, écrit avec la réparation
        self._orphans: list[str] = []
        self.warnings: list[str] = []

    @property
    def session_id(self) -> str:
        return self._header["session"]

    @property
    def created(self) -> str:
        return self._header["created"]

    # ----------------------------------------------------------- construction

    @classmethod
    def new(
        cls,
        workdir: Path,
        host_workdir: str,
        model: str,
        lock_stale_s: float = 30,
        secrets_: tuple[str, ...] = (),
    ) -> "Journal":
        """Session neuve ; le fichier n'est créé qu'à la première demande (CA-S3)."""
        header = {
            "type": "header",
            "format": FORMAT,
            "session": secrets.token_hex(4),
            "workdir": host_workdir,
            "created": _now(),
            "model": model,
        }
        return cls(
            _directory(workdir),
            header,
            written=False,
            model=model,
            lock_stale_s=lock_stale_s,
            secrets_=secrets_,
        )

    @classmethod
    def resume(
        cls,
        workdir: Path,
        host_workdir: str,
        ref: str,
        lock_stale_s: float = 30,
        secrets_: tuple[str, ...] = (),
    ) -> tuple["Journal", RestoredState]:
        """Rouvre une session. Rien n'est écrit ici, sauf le verrou (ADR-0012 §4)."""
        directory = _directory(workdir)
        session_id = resolve(workdir, ref)
        parsed = _parse(directory / f"{session_id}.jsonl")
        header, entries = parsed.header, parsed.entries
        if header["workdir"] != host_workdir:
            raise JournalError(
                f"Session {session_id} : elle appartient à un autre dossier de travail "
                f"({header['workdir']}). Relancez le harness depuis ce dossier."
            )
        chain = _active_chain(entries)

        # Cumuls et état de session : sur tout le journal, toutes branches comprises.
        model, detail = header["model"], False
        usages: list[tuple[dict, float | None]] = []
        for entry in entries:
            if entry["type"] == "usage":
                usages.append((entry["usage"], entry["cost_usd"]))
            elif entry["type"] == "state" and entry.get("kind") == "model_changed":
                model = entry["model"]
            elif entry["type"] == "state" and entry.get("kind") == "display_mode":
                detail = bool(entry["detail"])
        budget_grants = sum(
            1
            for e in entries
            if e["type"] == "state"
            and e.get("kind") == "grant"
            and e.get("limit") == "budget"
        )
        messages = [e["message"] for e in chain if e["type"] == "message"]
        display = {
            e["message"]["tool_call_id"]: e["display"]
            for e in chain
            if e["type"] == "message" and "display" in e
        }
        files: dict[str, str] = {}
        for e in chain:
            if e["type"] == "file_seen":
                files[e["path"]] = e["sha256"]
            elif e["type"] == "state" and e.get("kind") == "branch":
                files.clear()  # le dossier a pu changer : tout est à relire (CA-S22)
        orphans = _orphan_calls(messages)
        messages += [
            {"role": "tool", "tool_call_id": call_id, "content": ORPHAN_RESULT}
            for call_id in orphans
        ]

        journal = cls(
            directory,
            header,
            written=True,
            lock_stale_s=lock_stale_s,
            next_id=max(e["id"] for e in entries) + 1,
            head=entries[-1]["id"],
            model=model,
            secrets_=secrets_,
        )
        journal._parents = {e["id"]: e["parentId"] for e in entries}
        journal._messages = {e["id"]: e for e in entries if e["type"] == "message"}
        journal._repair_line = parsed.skipped_line
        journal._prefix = "\n" if parsed.needs_newline else ""
        journal._orphans = orphans
        journal.warnings = parsed.warnings
        if not journal._lock.acquire():
            raise JournalError(
                f"Session {session_id} occupée : elle est ouverte par un autre processus. "
                "Fermez-la ou attendez qu'elle se libère."
            )
        return journal, RestoredState(
            messages, usages, model, files, detail, display, budget_grants
        )

    def close(self) -> None:
        """Libère le verrou (fermeture normale ou reprise refusée plus loin)."""
        self._lock.release()

    # ------------------------------------------------- SessionStore (noyau)

    def message(self, message: dict, display: dict | None = None) -> None:
        fields: dict = {"message": message}
        if message.get("role") == "assistant":
            fields["model"] = self._model
        if display:
            fields["display"] = (
                display  # titre et diff : rendu seulement, le modèle ne les voit pas
            )
        self._append("message", **fields)

    def usage(self, usage: dict, cost_usd: float | None) -> None:
        self._append("usage", usage=usage, cost_usd=cost_usd)  # None = non estimé

    def file_seen(self, path: str, digest: str) -> None:
        self._append("file_seen", path=path, sha256=digest)

    def retract(self) -> None:
        """Demande restée sans réponse : nouveau point de départ, rien n'est effacé."""
        assert self._head is not None
        self._append("state", kind="retract", parent=self._parents[self._head])

    def branch(self, request: int) -> None:
        """Repart d'avant la demande n° `request` (0 = la première) de la branche active.

        Rien n'est réécrit : une entrée `branch` dont le parent est l'entrée précédant la
        demande ouvre la nouvelle branche ; l'ancienne reste dans le journal (ADR-0012 §2).
        """
        self._repair()  # les appels orphelins font partie de la branche active
        chain = self._chain()
        requests = [e for e in chain if _is_request(e)]
        self._append("state", kind="branch", parent=requests[request]["parentId"])

    def _chain(self) -> list[dict]:
        chain, cursor = [], self._head
        while cursor is not None:
            if cursor in self._messages:
                chain.append(self._messages[cursor])
            cursor = self._parents[cursor]
        chain.reverse()
        return chain

    # ------------------------------------------------------------ interface

    def interrupted(self) -> None:
        """Interruption (Ctrl+C, SIGTERM) : consignée comme changement d'état (spec §4.1)."""
        self._append("state", kind="interrupted")

    def granted(self, kind: str) -> None:
        """Tranche accordée à « continuer ? » (spec §4.1) ; seule la tranche de budget
        se restaure : la limite d'étapes est par tour."""
        self._append("state", kind="grant", limit=kind)

    def model_changed(self, alias: str) -> None:
        self._model = alias
        self._append("state", kind="model_changed", model=alias)

    def display_mode(self, detail: bool) -> None:
        self._append("state", kind="display_mode", detail=detail)

    # -------------------------------------------------------------- interne

    def _append(self, type_: str, **fields) -> None:
        self._repair()
        parent = fields.pop("parent", self._head)
        entry = {
            "id": self._next_id,
            "parentId": parent,
            "ts": _now(),
            "type": type_,
            **fields,
        }
        self._parents[entry["id"]] = parent
        if type_ == "message":
            self._messages[entry["id"]] = entry
        self._next_id += 1
        self._head = entry["id"]
        self._pending.append(entry)
        # Avant la première demande, l'état s'accumule : ni fichier ni session (CA-S3).
        if self._written or type_ == "message":
            self._flush()

    def _repair(self) -> None:
        """Ajoute, avant le premier ajout de la session, ce qui répare une anomalie lue."""
        line, orphans = self._repair_line, self._orphans
        self._repair_line, self._orphans = None, []
        if line is not None:
            self._append("state", kind="skipped_line", line=line)
        for call_id in orphans:
            self._append(
                "message",
                message={
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": ORPHAN_RESULT,
                },
            )

    def _flush(self) -> None:
        try:
            self._flush_lines()
        except OSError as failure:  # disque plein, droits : le noyau désactive (ADR §2)
            raise JournalError(
                f"Écriture du journal impossible ({failure.strerror or failure})."
            ) from failure

    def _flush_lines(self) -> None:
        if self._written and not self._lock.owned():
            self._pending = []
            raise JournalError(
                "Le verrou de la session a été repris par un autre processus."
            )
        lines = [_dump(entry, self._secrets) for entry in self._pending]
        self._pending = []
        if not self._written:
            self._create(lines)
        else:
            prefix, self._prefix = self._prefix, ""
            self._write(
                self._directory / f"{self.session_id}.jsonl",
                lines,
                create=False,
                prefix=prefix,
            )

    def _create(self, lines: list[str]) -> None:
        """En-tête et premières entrées en une seule écriture ; `O_EXCL` : id unique."""
        self._directory.mkdir(parents=True, exist_ok=True)
        ensure_gitignore(self._directory.parent)
        while True:
            path = self._directory / f"{self.session_id}.jsonl"
            try:
                self._write(path, [_dump(self._header), *lines], create=True)
                break
            except FileExistsError:
                self._header["session"] = secrets.token_hex(4)
        self._written = True
        # Le verrou porte le nom de la session : il se prend une fois l'identifiant acquis.
        self._lock = SessionLock(
            self._directory / f"{self.session_id}.lock", self._lock_stale_s
        )
        if not self._lock.acquire():
            raise JournalError(
                f"Session {self.session_id} : verrou impossible à prendre à la création."
            )

    @staticmethod
    def _write(path: Path, lines: list[str], *, create: bool, prefix: str = "") -> None:
        flags = os.O_WRONLY | os.O_APPEND | (os.O_CREAT | os.O_EXCL if create else 0)
        data = (prefix + "\n".join(lines) + "\n").encode("utf-8")
        fd = os.open(path, flags, 0o644)
        try:
            while data:
                data = data[os.write(fd, data) :]
        finally:
            os.close(fd)


def _is_request(entry: dict) -> bool:
    message = entry["message"] if entry["type"] == "message" else {}
    return message.get("role") == "user" and message.get("content") not in NOT_REQUESTS


def _dump(entry: dict, secrets_: tuple[str, ...] = ()) -> str:
    # Le masquage porte sur la ligne sérialisée : il couvre aussi une clé affichée par
    # une commande du modèle, où qu'elle apparaisse dans l'entrée (ADR-0012 §2).
    # Les champs de structure (type, ts, kind…) ne portent jamais de secret : les masquer
    # abîmerait la lecture du journal avec un secret court.
    entry = {
        key: value if key in _STRUCTURE else _redacted(value, secrets_)
        for key, value in entry.items()
    }
    text = json.dumps(entry, ensure_ascii=False)
    for char, escaped in _LINE_SEPARATORS.items():
        text = text.replace(char, escaped)
    return text


def _redacted(value, secrets_: tuple[str, ...]):
    """Masque dans les valeurs texte, jamais dans la syntaxe JSON : un secret court
    (`"`, `1`) ne doit pas pouvoir casser la ligne. Une clé affichée par une commande
    est dans une valeur, donc couverte (ADR-0012 §2)."""
    if isinstance(value, str):
        return redact(value, secrets_)
    if isinstance(value, list):
        return [_redacted(item, secrets_) for item in value]
    if isinstance(value, dict):
        return {key: _redacted(item, secrets_) for key, item in value.items()}
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


# ------------------------------------------------- suppression et purge (ADR-0012 §5)


def delete(workdir: Path, session_id: str, lock_stale_s: float) -> None:
    """Supprime une session : sorties d'abord, journal ensuite (un arrêt au milieu laisse
    un journal sans sorties, cas toléré ; l'ordre inverse laisserait un dossier orphelin).

    Le verrou est pris pour la durée de la suppression : une session occupée est refusée,
    et deux suppressions concurrentes ne se marchent pas dessus.
    """
    directory = _directory(workdir)
    lock = SessionLock(directory / f"{session_id}.lock", lock_stale_s)
    if not lock.acquire():
        raise JournalError(
            f"Session {session_id} occupée : elle est ouverte par un autre processus. "
            "Fermez-la avant de la supprimer."
        )
    try:
        root = workdir / RESERVED_DIR
        shutil.rmtree(root / "outputs" / session_id, ignore_errors=True)
        (directory / f"{session_id}.jsonl").unlink(missing_ok=True)
    finally:
        lock.release()
    try:
        directory.rmdir()  # seulement s'il est vide
    except OSError:
        pass
    tidy(workdir / RESERVED_DIR)


def purge_expired(
    workdir: Path, retention_days: float, lock_stale_s: float, now: float | None = None
) -> tuple[int, list[str]]:
    """Supprime les sessions sans activité depuis plus de `retention_days` jours.

    L'ancienneté est la date de modification du journal (dernière activité, rien d'autre
    ne le touche). Le contenu n'est pas lu : un journal d'un format inconnu est purgé selon
    l'âge. Une session occupée est ignorée ; un échec n'arrête pas les suivantes.
    Rend le nombre de sessions purgées et les échecs (messages à afficher).
    """
    now = time.time() if now is None else now
    purged, failures = 0, []
    for path in sorted(_directory(workdir).glob("*.jsonl")):
        try:
            if now - path.stat().st_mtime <= retention_days * 86400:
                continue
            delete(workdir, path.stem, lock_stale_s)
            purged += 1
        except JournalError:
            continue  # occupée : jamais purgée
        except OSError as failure:
            failures.append(f"Purge de la session {path.stem} impossible : {failure}")
    return purged, failures
