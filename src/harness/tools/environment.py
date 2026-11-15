"""Environment : seul accès des outils au système (ADR-0002 §7, ADR-0005 §3, ADR-0011 §5).

Une seule implémentation en v0 (`LocalEnvironment`, qui s'exécute dans le conteneur) ;
l'interface permet de changer de backend sans toucher aux outils.
"""

import asyncio
import codecs
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from harness.tools.outputs import OutputStore, SavedOutput
from harness.tools.truncate import (
    COMMAND_HEAD_SHARE,
    Truncation,
    cut_middle,
    tail_size,
)


@dataclass(frozen=True)
class RunOutcome:
    text: str  # sortie complète si elle tient au budget, sinon son début
    tail: str  # fin de la sortie (vide si rien n'est omis)
    truncation: Truncation | None
    exit_code: int | None  # None si tué
    timed_out: bool


class Environment(Protocol):
    workdir: Path

    def resolve(self, path: str) -> Path: ...
    async def stat(self, path: str) -> tuple[int, int] | None: ...
    async def read_bytes(self, path: str) -> bytes: ...
    async def write_bytes(self, path: str, data: bytes) -> None: ...
    async def run(
        self, command: str, timeout: float, store: OutputStore | None = None
    ) -> RunOutcome: ...


class _OutputCapture:
    """Lit la sortie au fil de l'eau en mémoire bornée (ADR-0011 §5-§6).

    On ne garde que les `budget` premiers caractères et une fenêtre glissante de la fin ;
    tant que le budget n'est pas dépassé, `first` *est* la sortie entière. Le fichier sur
    disque n'est ouvert qu'au premier dépassement.
    """

    def __init__(self, budget: int, store: OutputStore | None):
        self._budget = budget
        self._store = store
        self._window_size = tail_size(budget, COMMAND_HEAD_SHARE) + 1
        self._first = ""
        self._window = ""
        self._chars = 0
        self._newlines = 0
        self._ends_with_newline = True
        self._saved: SavedOutput | None = None

    def feed(self, text: str) -> None:
        if not text:
            return
        if (
            self._saved is None
            and self._store
            and self._chars + len(text) > self._budget
        ):
            self._saved = self._store.open_next()
            self._saved.write(self._first)
        if self._saved is not None:
            self._saved.write(text)
        self._chars += len(text)
        self._newlines += text.count("\n")
        self._ends_with_newline = text.endswith("\n")
        if len(self._first) < self._budget:
            self._first += text[: self._budget - len(self._first)]
        self._window = (self._window + text)[-self._window_size :]

    def close(self) -> None:
        """Ferme le fichier enregistré ; idempotent, sûr après une annulation."""
        if self._saved is not None:
            self._saved.close()

    def finish(self) -> tuple[str, str, Truncation | None]:
        self.close()
        if self._chars <= self._budget:
            return self._first, "", None
        total_lines = self._newlines + (0 if self._ends_with_newline else 1)
        head, tail, truncation = cut_middle(
            self._first,
            self._window,
            self._chars,
            total_lines,
            self._budget,
            COMMAND_HEAD_SHARE,
        )
        if self._saved is not None:
            truncation = Truncation(
                truncation.unit,
                truncation.first,
                truncation.last,
                truncation.total,
                saved_path=str(self._saved.path),
                saved_incomplete=self._saved.incomplete,
            )
        return head, tail, truncation


class LocalEnvironment:
    """Exécute dans le processus courant ; les chemins relatifs partent de `workdir`
    (par défaut le dossier courant du processus)."""

    def __init__(self, workdir: Path | None = None, max_output_chars: int = 20000):
        self.workdir = (workdir or Path.cwd()).resolve()
        self._max_output_chars = max_output_chars

    def resolve(self, path: str) -> Path:
        # Aucun confinement ici : la frontière est le conteneur (ADR-0002 §5).
        return Path(
            os.path.normpath(self.workdir / path)
        )  # un chemin absolu remplace le préfixe

    async def stat(self, path: str) -> tuple[int, int] | None:
        try:
            info = self.resolve(path).stat()
        except OSError:
            return None
        return info.st_mtime_ns, info.st_size

    async def read_bytes(self, path: str) -> bytes:
        return self.resolve(path).read_bytes()

    async def write_bytes(self, path: str, data: bytes) -> None:
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def run(
        self, command: str, timeout: float, store: OutputStore | None = None
    ) -> RunOutcome:
        # Nouveau groupe de processus : on peut tuer la commande *et* ses enfants,
        # sinon un petit-enfant garderait le tube ouvert (ADR-0005 §3).
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.workdir,
            start_new_session=True,
        )
        assert proc.stdout is not None
        capture = _OutputCapture(self._max_output_chars, store)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        async def pump() -> None:
            while chunk := await proc.stdout.read(65536):  # type: ignore[union-attr]
                capture.feed(decoder.decode(chunk))
            capture.feed(decoder.decode(b"", final=True))
            await proc.wait()

        def kill_group() -> None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        timed_out = False
        pump_task = asyncio.ensure_future(pump())
        try:
            await asyncio.wait_for(asyncio.shield(pump_task), timeout)
        except TimeoutError:
            timed_out = True
            kill_group()
            await pump_task
        except BaseException:
            # Annulation ou erreur : ne laisser ni processus ni fichier ouvert.
            kill_group()
            pump_task.cancel()
            await proc.wait()
            capture.close()
            raise

        head, tail, truncation = capture.finish()
        return RunOutcome(
            text=head,
            tail=tail,
            truncation=truncation,
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
        )
