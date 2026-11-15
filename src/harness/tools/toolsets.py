"""Ensembles d'outils nommés (ADR-0009 §1).

Notion : tool-calling (docs/notions/tool-calling.md).

L'ensemble actif décide de ce que le modèle *voit* et peut appeler. Ce n'est pas une
sécurité : c'est une restriction du catalogue exposé (voir ADR-0009, Conséquences).
Ce module ne dépend de rien pour que la configuration puisse l'importer sans cycle.
"""

DEFAULT_TOOLSET = "full"

TOOLSETS: dict[str, tuple[str, ...]] = {
    "full": ("read_file", "write_file", "edit_file", "shell"),
    "read_only": ("read_file",),
}
