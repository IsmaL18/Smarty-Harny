"""État des fichiers pour les outils : suivi des lectures, dossier réservé (ADR-0010 §3-§6).

Notion : tool-calling (docs/notions/tool-calling.md).

`edit_file` refuse de modifier un fichier que l'agent n'a pas lu, ou qui a changé depuis :
sans cela, le modèle remplace du texte qu'il imagine, pas celui qui est sur le disque.
La comparaison porte sur l'empreinte du *contenu* ; la date de modification ne sert qu'à
savoir si une commande shell a touché un fichier, jamais à refuser.
"""

import hashlib
import re
from pathlib import Path

from harness.tools.environment import Environment
from harness.tools.outputs import RESERVED_DIR

BINARY_SNIFF_BYTES = 8192


def decode_text(data: bytes) -> str | None:
    """Le texte UTF-8 du fichier, ou None s'il est binaire."""
    if b"\x00" in data[:BINARY_SNIFF_BYTES]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def split_lines(text: str) -> list[str]:
    """Lignes avec leur fin (`\\n` seulement : pas les autres séparateurs Unicode)."""
    return [line for line in re.split(r"(?<=\n)", text) if line]


def is_reserved(env: Environment, path: str) -> bool:
    reserved = env.workdir / RESERVED_DIR
    target = env.resolve(path)
    return target == reserved or reserved in target.parents


RESERVED_MESSAGE = (
    f"error: {RESERVED_DIR}/ is reserved for the harness's saved outputs; "
    "choose another path"
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileTracker:
    """Fichiers lus, écrits ou modifiés par l'agent pendant la session."""

    def __init__(self) -> None:
        # chemin résolu → (empreinte du contenu, (mtime_ns, taille))
        self._seen: dict[Path, tuple[str, tuple[int, int] | None]] = {}

    async def record(self, env: Environment, path: str, data: bytes) -> None:
        self._seen[env.resolve(path)] = (_digest(data), await env.stat(path))

    def check(self, env: Environment, path: str, data: bytes) -> str:
        """« ok », « unread » (jamais lu) ou « changed » (contenu différent de la lecture)."""
        seen = self._seen.get(env.resolve(path))
        if seen is None:
            return "unread"
        return "ok" if seen[0] == _digest(data) else "changed"

    async def clean_files(self, env: Environment) -> list[Path]:
        """Fichiers suivis dont l'état disque est celui de leur dernier enregistrement."""
        return [
            key
            for key, (_, stat) in self._seen.items()
            if await env.stat(str(key)) == stat
        ]

    async def absorb(self, env: Environment, before: list[Path]) -> None:
        """Après une commande de l'agent : ré-enregistre ceux de `before` qu'elle a changés.

        Un fichier déjà modifié de l'extérieur *avant* la commande n'est pas dans `before` :
        il reste signalé comme périmé (ADR-0010 §5).
        """
        for key in before:
            if await env.stat(str(key)) == self._seen[key][1]:
                continue
            try:
                data = await env.read_bytes(str(key))
            except OSError:
                self._seen.pop(
                    key, None
                )  # supprimé : « fichier absent » à la modification
                continue
            await self.record(env, str(key), data)
