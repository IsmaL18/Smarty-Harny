"""Sorties de commande enregistrées sur disque (ADR-0011 §6-§12).

Notion : context-engineering (docs/notions/).

Quand une sortie dépasse le budget, le modèle n'en voit que le début et la fin ; la
sortie complète est écrite dans `<travail>/.harness/outputs/<session>/cmd-<n>.txt` pour
qu'il puisse la relire par plage avec `read_file`. Le dossier est exclu de Git par son
propre `.gitignore` et disparaît avec la session.
"""

import os
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path

RESERVED_DIR = ".harness"
STALE_AFTER_S = (
    24 * 3600
)  # restes d'un arrêt brutal, purgés au lancement (ADR-0011 §12)


class SavedOutput:
    """Fichier de sortie ouvert ; l'écriture s'arrête au plafond disque (ADR-0011 §7)."""

    def __init__(self, path: Path, cap_bytes: int, secrets_: tuple[str, ...] = ()):
        self.path = path
        self.incomplete = False
        self._cap = cap_bytes
        self._size = 0
        self._handle = path.open("wb")
        self._secrets = secrets_
        # Une clé peut être coupée entre deux blocs : on retient la fin du dernier bloc,
        # de la longueur de la plus longue clé moins un, jusqu'au bloc suivant.
        self._hold = max((len(s) for s in secrets_), default=1) - 1
        self._pending = ""

    def write(self, text: str) -> None:
        if not self._secrets:
            self._emit(text)
            return
        buffer = redact(self._pending + text, self._secrets)
        keep = self._hold
        self._pending = buffer[len(buffer) - keep :] if keep else ""
        self._emit(buffer[: len(buffer) - keep])

    def _emit(self, text: str) -> None:
        if self.incomplete:
            return
        data = text.encode("utf-8", errors="replace")
        room = self._cap - self._size
        if len(data) > room:
            # Coupe sur une frontière de caractère : un octet UTF-8 tronqué rendrait le
            # fichier illisible pour read_file.
            data = data[: max(room, 0)].decode("utf-8", errors="ignore").encode("utf-8")
            self.incomplete = True
        self._handle.write(data)
        self._size += len(data)

    def close(self) -> None:
        pending, self._pending = self._pending, ""
        if pending:
            self._emit(pending)
        self._handle.close()


REDACTED = "[REDACTED]"


def redact(text: str, secrets_: tuple[str, ...]) -> str:
    """Remplace la valeur exacte de chaque secret (ADR-0012 §2). Une clé transformée
    (base64, découpée par le modèle) n'est pas reconnue : limite acceptée."""
    for secret in secrets_:
        text = text.replace(secret, REDACTED)
    return text


class OutputStore:
    """Sorties d'une session. Enregistrée : le dossier porte l'identifiant de la session
    et vit autant qu'elle (ADR-0012 §5) ; non enregistrée : dossier éphémère, nettoyé."""

    def __init__(
        self,
        workdir: Path,
        max_mb: int,
        session_id: Callable[[], str] | None = None,
        secrets_: tuple[str, ...] = (),
    ):
        self._root = workdir / RESERVED_DIR
        # Appelable : l'identifiant d'une session neuve peut encore changer à sa création.
        ephemeral = secrets.token_hex(4)
        self._session_id = session_id or (lambda: ephemeral)
        self._cap_bytes = max_mb * 1024 * 1024
        self._secrets = secrets_
        self._count = 0

    @property
    def _session_dir(self) -> Path:
        return self._root / "outputs" / self._session_id()

    def open_next(self) -> SavedOutput:
        self._session_dir.mkdir(parents=True, exist_ok=True)
        ensure_gitignore(self._root)
        self._count += 1
        os.utime(self._session_dir)  # signale une session vivante à la purge
        return SavedOutput(
            self._session_dir / f"cmd-{self._count}.txt", self._cap_bytes, self._secrets
        )

    def cleanup(self) -> None:
        """Run non enregistré : supprime ses sorties, puis `.harness/` s'il est vide."""
        shutil.rmtree(self._session_dir, ignore_errors=True)
        tidy(self._root)

    @staticmethod
    def purge_stale(workdir: Path, now: float | None = None) -> None:
        """Supprime les dossiers de session dont rien n'a bougé depuis 24 h.

        Une session concurrente dans le même dossier est récente : elle n'est pas touchée.
        Un dossier qui a un journal appartient à une session enregistrée : jamais purgé ici.
        """
        root = workdir / RESERVED_DIR
        outputs = root / "outputs"
        if not outputs.is_dir():
            return
        now = time.time() if now is None else now
        try:
            folders = list(outputs.iterdir())
        except OSError:
            return
        for folder in folders:
            if (root / "sessions" / f"{folder.name}.jsonl").exists():
                continue
            try:
                stale = folder.is_dir() and now - _newest_mtime(folder) > STALE_AFTER_S
            except OSError:  # session concurrente qui nettoie en même temps
                continue
            if stale:
                shutil.rmtree(folder, ignore_errors=True)
        tidy(root)


def ensure_gitignore(root: Path) -> None:
    """Le dossier réservé s'exclut lui-même de Git (ADR-0011 §10)."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")


def _newest_mtime(folder: Path) -> float:
    times = [folder.stat().st_mtime]
    times += [p.stat().st_mtime for p in folder.iterdir()]
    return max(times)


def tidy(root: Path) -> None:
    outputs = root / "outputs"
    try:
        outputs.rmdir()  # seulement s'il est vide
    except OSError:
        pass
    try:
        if {p.name for p in root.iterdir()} <= {".gitignore"}:
            shutil.rmtree(root, ignore_errors=True)
    except OSError:
        pass
