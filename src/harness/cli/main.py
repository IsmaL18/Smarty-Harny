"""Point d'entrée réel : argparse, garde conteneur, câblage (ADR-0006, ADR-0007, ADR-0008).

Seul module qui lit l'environnement et câble les implémentations réelles ; validé par
l'humain (CA-25), pas par les tests automatisés.
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Callable

from harness.cli import headless, repl
from harness.config import ConfigError, ModelProfile, load_config
from harness.models.base import ModelClient
from harness.models.litellm_client import LiteLLMClient, key_env
from harness.sessions.journal import JournalError, delete, list_sessions, resolve
from harness.tools.environment import LocalEnvironment


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[ModelProfile], ModelClient] = LiteLLMClient,
) -> int:
    parser = argparse.ArgumentParser(
        prog="harness", description="Agent de code en terminal."
    )
    parser.add_argument(
        "--model", help="alias de modèle (remplace default_model pour la session)"
    )
    parser.add_argument(
        "--resume", metavar="ID", help="reprend la session d'identifiant ID"
    )
    parser.add_argument(
        "--sessions", action="store_true", help="liste les sessions du dossier courant"
    )
    parser.add_argument(
        "--delete", metavar="ID", help="supprime la session ID (journal et sorties)"
    )
    parser.add_argument(
        "-p", "--prompt", metavar="TEXTE", help="une seule demande, sans interaction"
    )
    parser.add_argument(
        "--output-format",
        choices=("text", "jsonl"),
        default="text",
        help="format de sortie du mode -p : réponse seule (text) ou flux JSONL",
    )
    parser.add_argument(
        "--no-session",
        action="store_true",
        help="mode -p : n'enregistre aucune session",
    )
    args = parser.parse_args(argv)
    if args.no_session and args.prompt is None:
        parser.error("--no-session ne s'utilise qu'avec -p/--prompt")
    if args.no_session and args.resume:
        parser.error("--no-session et --resume sont incompatibles")
    # Mode non interactif : tout échec de démarrage est un code 2 (spec §4.8.3).
    start_failure = 2 if args.prompt is not None else 1

    if not os.environ.get("HARNESS_IN_CONTAINER"):
        print(
            "Le harness ne fonctionne que dans son conteneur. "
            "Lancez-le avec bin/harness depuis le dossier de travail voulu.",
            file=sys.stderr,
        )
        return start_failure
    toml_text = os.environ.get("HARNESS_CONFIG_TOML")
    if not toml_text:
        print(
            "HARNESS_CONFIG_TOML est vide : lancez le harness avec bin/harness.",
            file=sys.stderr,
        )
        return start_failure
    try:
        config = load_config(toml_text)
    except ConfigError as error:
        print(f"Configuration invalide : {error}", file=sys.stderr)
        return start_failure

    try:
        import readline  # noqa: F401  (édition de ligne pour input())
    except ImportError:
        pass
    host_workdir = os.environ.get("HARNESS_HOST_WORKDIR")
    if args.sessions:
        env = LocalEnvironment(max_output_chars=config.tools.max_output_chars)
        infos = list_sessions(
            env.workdir, host_workdir or str(env.workdir), config.sessions.lock_stale_s
        )
        for line in repl.format_sessions(infos) or ["Aucune session dans ce dossier."]:
            print(line)
        return 0
    if args.delete:
        env = LocalEnvironment(max_output_chars=config.tools.max_output_chars)
        try:
            session_id = resolve(env.workdir, args.delete)
            answer = input(
                f"Supprimer la session {session_id} (journal et sorties enregistrées) ? "
                "(oui/non) "
            )
            if answer.strip().lower() not in ("oui", "o", "yes", "y"):
                print("Rien n'a été supprimé.")
                return 0
            delete(env.workdir, session_id, config.sessions.lock_stale_s)
        except JournalError as failure:
            print(failure, file=sys.stderr)
            return 2
        print(f"Session {session_id} supprimée.")
        return 0
    # Les clés API ne sont jamais écrites : leurs valeurs sont masquées à l'écriture.
    key_names = {key_env(profile) for profile in config.models.values()}
    secrets = tuple(
        sorted(
            {os.environ[name] for name in key_names if name and os.environ.get(name)},
            key=len,
            reverse=True,
        )
    )
    # Dans le conteneur, le dossier est toujours /workspace : l'identité d'une session
    # est le chemin de l'hôte, passé par le lanceur (ADR-0012 §1.3).
    if args.prompt is not None:
        return asyncio.run(
            headless.run(
                config,
                client_factory,
                args.prompt,
                output_format=args.output_format,
                model_override=args.model,
                resume=args.resume,
                no_session=args.no_session,
                host_workdir=host_workdir,
                secrets=secrets,
            )
        )
    return asyncio.run(
        repl.run(
            config,
            client_factory,
            input,
            lambda text: print(text, end="", flush=True),
            model_override=args.model,
            resume=args.resume,
            host_workdir=host_workdir,
            on_refusal=lambda text: print(text, end="", file=sys.stderr, flush=True),
            secrets=secrets,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
