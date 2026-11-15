"""Coercition des arguments d'outil, pilotée par le schéma (ADR-0009 §5-§7).

Notion : tool-calling (docs/notions/tool-calling.md).

Les modèles se trompent souvent sur la *forme* d'un argument (`"3"` au lieu de `3`,
un objet au lieu d'une liste d'un objet, une liste sérialisée en texte) sans se tromper
sur son sens. On corrige ces formes-là, à un seul endroit, pour tous les outils.
Règle stricte : en cas de doute on ne touche à rien, et `jsonschema` refuse ensuite
la valeur avec un message qui nomme l'argument et la forme attendue.
"""

import json
import re
from typing import Any

_INTEGER = re.compile(r"-?\d+")
_NUMBER = re.compile(r"-?\d+(\.\d+)?")


def coerce_arguments(args: dict, schema: dict) -> dict:
    """Renvoie une copie des arguments dont les formes sont corrigées d'après le schéma."""
    return _coerce(args, schema)


def _coerce(value: Any, schema: dict) -> Any:
    kind = schema.get("type")
    if kind == "integer" and isinstance(value, str) and _INTEGER.fullmatch(value):
        return int(value)
    if kind == "number" and isinstance(value, str) and _NUMBER.fullmatch(value):
        return float(value) if "." in value else int(value)
    if kind == "boolean" and isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        return value
    if kind == "array":
        value = _as_list(value)
        item_schema = schema.get("items")
        if isinstance(value, list) and item_schema:
            return [_coerce(item, item_schema) for item in value]
        return value
    if kind == "object":
        value = _as_object(value)
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            return {
                key: _coerce(item, properties[key]) if key in properties else item
                for key, item in value.items()
            }
    return value


def _decode(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _as_list(value: Any) -> Any:
    if isinstance(value, str):
        value = _decode(value)  # texte non JSON : on ne devine pas
    if isinstance(value, dict):
        return [value]  # un objet seul devient une liste d'un élément
    return value


def _as_object(value: Any) -> Any:
    if isinstance(value, str):
        decoded = _decode(value)
        if isinstance(decoded, dict):
            return decoded
    return value
