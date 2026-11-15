"""Environment : seul accès des outils au système (ADR-0002 §7, ADR-0005 §3).

Une seule implémentation en v0 (`LocalEnvironment`, qui s'exécute dans le conteneur) ;
l'interface permet de changer de backend sans toucher aux outils.
"""

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RunOutcome:
    output: str  # stdout+stderr fusionnés, tronqué à max_output_chars
    exit_code: int | None  # None si tué
    timed_out: bool
    discarded_chars: int


class Environment(Protocol):
    workdir: Path

    async def read_bytes(self, path: str) -> bytes: ...
    async def write_bytes(self, path: str, data: bytes) -> None: ...
    async def run(self, command: str, timeout: float) -> RunOutcome: ...


class LocalEnvironment:
    """Exécute dans le processus courant ; les chemins relatifs partent de `workdir`
    (par défaut le dossier courant du processus)."""

    def __init__(self, workdir: Path | None = None, max_output_chars: int = 20000):
        self.workdir = (workdir or Path.cwd()).resolve()
        self._max_output_chars = max_output_chars

    def _resolve(self, path: str) -> Path:
        # Aucun confinement ici : la frontière est le conteneur (ADR-0002 §5).
        return self.workdir / path  # un chemin absolu remplace le préfixe

    async def read_bytes(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    async def write_bytes(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def run(self, command: str, timeout: float) -> RunOutcome:
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
        # Tampon plafonné (octets) : une commande bavarde (`yes`) ne sature pas la mémoire.
        cap = self._max_output_chars * 4
        buffer = bytearray()
        discarded = 0

        async def pump() -> None:
            nonlocal discarded
            while chunk := await proc.stdout.read(65536):  # type: ignore[union-attr]
                room = cap - len(buffer)
                buffer.extend(chunk[:room])
                discarded += max(0, len(chunk) - room)
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
        except asyncio.CancelledError:
            kill_group()
            pump_task.cancel()
            await proc.wait()
            raise

        text = buffer.decode("utf-8", errors="replace")
        omitted = discarded
        if len(text) > self._max_output_chars:
            omitted += len(text) - self._max_output_chars
            text = text[: self._max_output_chars]
        return RunOutcome(
            output=text,
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            discarded_chars=omitted,
        )
