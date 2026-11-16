"""Configuration immuable (ADR-0007)."""

import tomllib
from dataclasses import dataclass, field, fields
from typing import Any

from harness.tools.toolsets import DEFAULT_TOOLSET, TOOLSETS


class ConfigError(Exception):
    """Configuration invalide ; le message (en français) nomme la clé et la correction."""


@dataclass(frozen=True)
class Limits:
    max_steps_per_turn: int = 25
    budget_usd: float = 1.00


@dataclass(frozen=True)
class ToolsConfig:
    max_read_chars: int = 40000
    max_output_chars: int = 20000
    command_timeout_s: float = 120
    max_saved_output_mb: int = 50
    toolset: str = DEFAULT_TOOLSET


@dataclass(frozen=True)
class SessionsConfig:
    lock_stale_s: float = 30  # bail du verrou de session (ADR-0012 §3)
    retention_days: float = (
        30  # purge des sessions inactives au lancement (ADR-0012 §5)
    )


@dataclass(frozen=True)
class ModelProfile:
    model: str
    api_base: str | None = None
    api_key_env: str | None = None
    max_output_tokens: int = 8192
    request_timeout_s: float = 300
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None


@dataclass(frozen=True)
class Config:
    default_model: str
    models: dict[str, ModelProfile]
    limits: Limits = field(default_factory=Limits)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    sessions: SessionsConfig = field(default_factory=SessionsConfig)


def _number(
    section: str, key: str, value: object, kind: type, allow_zero: bool = False
) -> Any:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    if not ok or value < 0 or (value == 0 and not allow_zero):  # type: ignore[operator]
        nom = "un entier" if kind is int else "un nombre"
        positif = "positif ou nul" if allow_zero else "strictement positif"
        raise ConfigError(f"[{section}] {key} doit être {nom} {positif}.")
    return value  # type: ignore[return-value]


def _check_keys(section: str, raw: dict, allowed: set[str]) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(
            f"Clé inconnue dans [{section}] : {', '.join(sorted(unknown))}. "
            f"Clés admises : {', '.join(sorted(allowed))}."
        )


def load_config(toml_text: str) -> Config:
    """Construit la configuration depuis le contenu TOML (HARNESS_CONFIG_TOML).

    Toute erreur est une `ConfigError` en français qui nomme la clé et la correction.
    """
    try:
        raw = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Configuration illisible (TOML invalide) : {exc}") from exc
    _check_keys(
        "racine", raw, {"default_model", "limits", "tools", "sessions", "models"}
    )

    limits_raw = raw.get("limits", {})
    _check_keys("limits", limits_raw, {f.name for f in fields(Limits)})
    limits = Limits(
        **{
            key: _number(
                "limits", key, value, int if key == "max_steps_per_turn" else float
            )
            for key, value in limits_raw.items()
        }
    )

    tools_raw = raw.get("tools", {})
    _check_keys("tools", tools_raw, {f.name for f in fields(ToolsConfig)})
    toolset = tools_raw.get("toolset", DEFAULT_TOOLSET)
    if toolset not in TOOLSETS:
        raise ConfigError(
            f"[tools] toolset : ensemble inconnu '{toolset}'. "
            f"Ensembles disponibles : {', '.join(TOOLSETS)}."
        )
    tools = ToolsConfig(
        toolset=toolset,
        **{
            key: _number(
                "tools", key, value, float if key == "command_timeout_s" else int
            )
            for key, value in tools_raw.items()
            if key != "toolset"
        },
    )

    sessions_raw = raw.get("sessions", {})
    _check_keys("sessions", sessions_raw, {f.name for f in fields(SessionsConfig)})
    sessions = SessionsConfig(
        **{
            key: _number("sessions", key, value, float)
            for key, value in sessions_raw.items()
        }
    )

    models: dict[str, ModelProfile] = {}
    for alias, profile_raw in raw.get("models", {}).items():
        section = f"models.{alias}"
        _check_keys(section, profile_raw, {f.name for f in fields(ModelProfile)})
        if not isinstance(profile_raw.get("model"), str):
            raise ConfigError(
                f"[{section}] model est obligatoire (identifiant LiteLLM)."
            )
        profile = dict(profile_raw)
        for key in ("api_base", "api_key_env"):
            if key in profile and not isinstance(profile[key], str):
                raise ConfigError(f"[{section}] {key} doit être une chaîne.")
        for key, kind in (
            ("max_output_tokens", int),
            ("request_timeout_s", float),
            ("input_price_per_mtok", float),
            ("output_price_per_mtok", float),
        ):
            if key in profile:
                profile[key] = _number(
                    section, key, profile[key], kind, allow_zero=key.endswith("_mtok")
                )
        models[alias] = ModelProfile(**profile)
    if not models:
        raise ConfigError(
            "Aucun modèle : ajoutez au moins une section [models.<alias>]."
        )

    default = raw.get("default_model")
    if not isinstance(default, str) or default not in models:
        raise ConfigError(
            f"default_model doit nommer un alias de [models] (alias : {', '.join(models)})."
        )
    return Config(
        default_model=default,
        models=models,
        limits=limits,
        tools=tools,
        sessions=sessions,
    )
