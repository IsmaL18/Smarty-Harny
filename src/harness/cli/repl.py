"""REPL : lecture des lignes, commandes de session, « continuer ? » (ADR-0008, ADR-0005).

Notion : boucle-agent. Seule couche qui interagit avec l'utilisateur : le noyau (`Session`)
ne fait ni `print` ni `input`. `read_line` et `write` sont injectés pour les tests.
"""

import asyncio
import signal
from collections.abc import AsyncIterator, Callable

from harness.cli.render import render
from harness.config import Config, ModelProfile
from harness.cost import format_usd
from harness.events import TurnEnded
from harness.models.base import ModelClient, ProviderError
from harness.session import Event, Session
from harness.tools.environment import Environment, LocalEnvironment

COMMANDS = (
    "/quit : quitte et affiche le coût total",
    "/detail : bascule entre lignes-titres et détail complet",
    "/model <alias> : change de modèle (sans alias : liste les modèles)",
)
_YES = {"oui", "o", "yes", "y"}
_NO = {"non", "n", "no"}


async def run(
    config: Config,
    client_factory: Callable[[ModelProfile], ModelClient],
    read_line: Callable[
        [str], str
    ],  # comme input(prompt) ; peut lever EOFError / KeyboardInterrupt
    write: Callable[[str], None],
    model_override: str | None = None,  # option de lancement --model
    environment: Environment
    | None = None,  # défaut : LocalEnvironment() sur le dossier courant
) -> None:
    env = environment or LocalEnvironment(
        max_output_chars=config.tools.max_output_chars
    )

    def say(text: str = "") -> None:
        write(text + "\n")

    # --- Démarrage (ADR-0008 §6) : config → --model → check → affichage → invite
    alias = model_override or config.default_model
    if alias not in config.models:
        say(
            f"Modèle inconnu : '{alias}'. Modèles disponibles : {', '.join(config.models)}."
        )
        return
    client = client_factory(config.models[alias])
    try:
        await client.check()
    except ProviderError as error:
        say(error.message_fr)
        return

    session = Session(config, client, env)
    say(f"Dossier de travail : {env.workdir}")
    say(f"Modèle actif : {alias}")
    say(
        f"Limites : {config.limits.max_steps_per_turn} étapes par tour, "
        f"budget {format_usd(config.limits.budget_usd)}"
    )
    profile = config.models[alias]
    if profile.api_base and (
        profile.input_price_per_mtok is None or profile.output_price_per_mtok is None
    ):
        say("Coût non estimé pour ce modèle : le budget ne s'applique pas.")
    say("Commandes : " + " · ".join(COMMANDS))

    detail = False

    async def play(events: AsyncIterator[Event]) -> str | None:
        """Affiche un tour ; Ctrl+C annule la tâche, que le noyau referme proprement."""
        reason: str | None = None

        async def drain() -> None:
            nonlocal reason
            async for event in events:
                text = render(event, detail)
                if text:
                    say(text)
                if isinstance(event, TurnEnded):
                    reason = event.reason

        loop = asyncio.get_running_loop()
        task = asyncio.ensure_future(drain())
        installed = True
        try:
            loop.add_signal_handler(signal.SIGINT, task.cancel)
        except (NotImplementedError, RuntimeError, ValueError):
            installed = False  # pas dans le thread principal : pas de Ctrl+C géré
        try:
            await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            say("Tour interrompu.")
        finally:
            if installed:
                loop.remove_signal_handler(signal.SIGINT)
        return reason

    def ask_continue() -> bool:
        """« Oui » accorde une tranche ; Ctrl+C / Ctrl+D valent « non » (ADR-0001 §6)."""
        while True:
            try:
                answer = read_line("Continuer ? (oui/non) ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                say()
                return False
            if answer in _YES:
                return True
            if answer in _NO:
                return False
            say("Répondez par oui ou non.")

    async def handle_turn(text: str) -> None:
        reason = await play(session.run_turn(text))
        while reason in ("step_limit", "budget_limit") and ask_continue():
            reason = await play(session.resume_turn(grant=True))
        say(session.cost.display())

    async def switch_model(new_alias: str) -> None:
        nonlocal alias
        if new_alias not in config.models:
            say(
                f"Modèle inconnu : '{new_alias}'. Modèles disponibles : {', '.join(config.models)}."
            )
            return
        new_client = client_factory(config.models[new_alias])
        try:
            await (
                new_client.check()
            )  # le nouveau client n'est installé qu'après un check réussi
        except ProviderError as error:
            say(f"{error.message_fr}\nLe modèle actif reste : {alias}.")
            return
        session.set_client(new_client)
        alias = new_alias
        say(f"Modèle actif : {alias}")

    while True:
        try:
            line = read_line("> ").strip()
        except EOFError:
            say()
            break
        except KeyboardInterrupt:
            say()  # Ctrl+C à l'invite ne quitte pas (CA-19)
            continue
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/detail":
            detail = not detail
            say("Mode détaillé : " + ("activé" if detail else "désactivé"))
        elif line.startswith("/model"):
            argument = line[len("/model") :].strip()
            if argument:
                await switch_model(argument)
            else:
                say(f"Modèle actif : {alias}. Modèles : {', '.join(config.models)}")
        elif line.startswith("/"):
            say("Commande inconnue. Commandes :")
            for command in COMMANDS:
                say("  " + command)
        else:
            await handle_turn(line)

    say(f"Total de la session — {session.cost.display()}")
