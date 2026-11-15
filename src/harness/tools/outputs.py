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
from pathlib import Path

RESERVED_DIR = ".harness"
STALE_AFTER_S = (
    24 * 3600
)  # restes d'un arrêt brutal, purgés au lancement (ADR-0011 §12)


class SavedOutput:
    """Fichier de sortie ouvert ; l'écriture s'arrête au plafond disque (ADR-0011 §7)."""

    def __init__(self, path: Path, cap_bytes: int):
        self.path = path
        self.incomplete = False
        self._cap = cap_bytes
        self._size = 0
        self._handle = path.open("wb")

    def write(self, text: str) -> None:
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
        self._handle.close()


class OutputStore:
    def __init__(self, workdir: Path, max_mb: int):
        self._root = workdir / RESERVED_DIR
        self._session_dir = self._root / "outputs" / secrets.token_hex(4)
        self._cap_bytes = max_mb * 1024 * 1024
        self._count = 0

    def open_next(self) -> SavedOutput:
        self._session_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self._root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")
        self._count += 1
        os.utime(self._session_dir)  # signale une session vivante à la purge
        return SavedOutput(
            self._session_dir / f"cmd-{self._count}.txt", self._cap_bytes
        )

    def cleanup(self) -> None:
        """Fin de session : supprime ses sorties, puis `.harness/` s'il est vide."""
        shutil.rmtree(self._session_dir, ignore_errors=True)
        _tidy(self._root)

    @staticmethod
    def purge_stale(workdir: Path, now: float | None = None) -> None:
        """Supprime les dossiers de session dont rien n'a bougé depuis 24 h.

        Une session concurrente dans le même dossier est récente : elle n'est pas touchée.
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
            try:
                stale = folder.is_dir() and now - _newest_mtime(folder) > STALE_AFTER_S
            except OSError:  # session concurrente qui nettoie en même temps
                continue
            if stale:
                shutil.rmtree(folder, ignore_errors=True)
        _tidy(root)


def _newest_mtime(folder: Path) -> float:
    times = [folder.stat().st_mtime]
    times += [p.stat().st_mtime for p in folder.iterdir()]
    return max(times)


def _tidy(root: Path) -> None:
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
