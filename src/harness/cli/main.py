"""Point d'entrée réel : argparse, garde conteneur, câblage (ADR-0006, ADR-0007, ADR-0008).

Seul module qui lit l'environnement et câble les implémentations réelles ; validé par
l'humain (CA-25), pas par les tests automatisés.
"""

import argparse
import asyncio
import os
import sys

from harness.cli import repl
from harness.config import ConfigError, load_config
from harness.models.litellm_client import LiteLLMClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness", description="Agent de code en terminal."
    )
    parser.add_argument(
        "--model", help="alias de modèle (remplace default_model pour la session)"
    )
    args = parser.parse_args(argv)

    if not os.environ.get("HARNESS_IN_CONTAINER"):
        print(
            "Le harness ne fonctionne que dans son conteneur. "
            "Lancez-le avec bin/harness depuis le dossier de travail voulu.",
            file=sys.stderr,
        )
        return 1
    toml_text = os.environ.get("HARNESS_CONFIG_TOML")
    if not toml_text:
        print(
            "HARNESS_CONFIG_TOML est vide : lancez le harness avec bin/harness.",
            file=sys.stderr,
        )
        return 1
    try:
        config = load_config(toml_text)
    except ConfigError as error:
        print(f"Configuration invalide : {error}", file=sys.stderr)
        return 1

    try:
        import readline  # noqa: F401  (édition de ligne pour input())
    except ImportError:
        pass
    asyncio.run(
        repl.run(
            config,
            LiteLLMClient,
            input,
            lambda text: print(text, end="", flush=True),
            model_override=args.model,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
