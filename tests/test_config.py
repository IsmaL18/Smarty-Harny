"""Validation de la configuration : une valeur invalide est refusée en nommant la clé.

ADR-0007 : toute erreur est une `ConfigError` en français qui nomme la clé.
"""

import pytest

from harness.config import ConfigError, load_config


def _toml(**profile_values: str) -> str:
    """Configuration minimale ; les valeurs sont données en syntaxe TOML brute."""
    lines = "\n".join(f"{key} = {value}" for key, value in profile_values.items())
    return f'default_model = "m"\n[models.m]\nmodel = "openai/x"\n{lines}\n'


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("input_price_per_mtok", "-1"),
        ("input_price_per_mtok", '"3"'),
        ("input_price_per_mtok", "true"),
        ("output_price_per_mtok", "-0.5"),
        ("output_price_per_mtok", '"quinze"'),
        ("output_price_per_mtok", "false"),
        ("max_output_tokens", "8192.5"),
    ],
)
def test_invalid_profile_numbers_are_refused_naming_the_key(key, raw):
    """Prix négatif / chaîne / booléen et `max_output_tokens` non entier : refusés."""
    with pytest.raises(ConfigError, match=key):
        load_config(_toml(**{key: raw}))


def test_zero_prices_are_accepted():
    """Un prix de 0 est valide (serveur gratuit mais budgété)."""
    config = load_config(_toml(input_price_per_mtok="0", output_price_per_mtok="0.0"))

    profile = config.models["m"]
    assert profile.input_price_per_mtok == 0
    assert profile.output_price_per_mtok == 0
