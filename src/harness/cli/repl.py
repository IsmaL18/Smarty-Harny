"""REPL : lecture des lignes, commandes de session, « continuer ? » (ADR-0008, ADR-0005).

Notion : boucle-agent. Seule couche qui interagit avec l'utilisateur : le noyau (`Session`)
ne fait ni `print` ni `input`. `read_line` et `write` sont injectés pour les tests.
"""

import asyncio
import json
import signal
from collections.abc import AsyncIterator, Callable
from datetime import datetime

from harness.cli import startup
from harness.cli.render import render
from harness.cli.startup import Opened, Refused
from harness.config import Config, ModelProfile
from harness.cost import format_usd
from harness.events import (
    AssistantMessage,
    RecordingFailed,
    ToolCallFinished,
    ToolCallStarted,
    TurnEnded,
)
from harness.models.base import ModelClient, ProviderError
from harness.session import (
    NOT_REQUESTS,
    Event,
    RestoredState,
    Session,
)
from harness.sessions.journal import (
    JournalError,
    SessionInfo,
    list_sessions,
    resolve,
)
from harness.tools.base import ToolResult
from harness.tools.environment import Environment, LocalEnvironment
from harness.tools.toolsets import TOOLSETS

COMMANDS = (
    "/quit : quitte et affiche le coût total",
    "/detail : bascule entre lignes-titres et détail complet",
    "/model <alias> : change de modèle (sans alias : liste les modèles)",
    "/resume [id|numéro] : ouvre une autre session du dossier (sans argument : la liste)",
    "/branch : repart d'avant une demande précédente de la conversation",
)
_YES = {"oui", "o", "yes", "y"}
_NO = {"non", "n", "no"}


def format_sessions(infos: list[SessionInfo], numbered: bool = False) -> list[str]:
    """Une ligne par session (spec §4.2), de la plus récente à la plus ancienne."""
    lines = []
    for number, info in enumerate(infos, start=1):
        when = datetime.fromtimestamp(info.last_activity).strftime("%Y-%m-%d %H:%M")
        plural = "demande" if info.requests == 1 else "demandes"
        lines.append(
            (f"{number}. " if numbered else "")
            + f"{info.id}  {when}  {info.requests} {plural}  {info.cost}  {info.model}"
            + ("  [occupée]" if info.busy else "")
            + f"  « {info.first_request} »"
        )
    return lines


def _replay(restored: RestoredState, detail: bool, say: Callable[[str], None]) -> None:
    """Réaffiche la conversation de la branche active dans le mode d'affichage restauré."""
    names: dict[str, str] = {}
    for message in restored.messages:
        match message.get("role"):
            case "user":
                if message["content"] not in NOT_REQUESTS:
                    say(f"> {message['content']}")
            case "assistant":
                events: list[object] = []
                if message.get("content"):
                    events.append(AssistantMessage(message["content"]))
                for call in message.get("tool_calls") or []:
                    name = call["function"]["name"]
                    names[call["id"]] = name
                    try:
                        arguments = json.loads(
                            call["function"].get("arguments") or "{}"
                        )
                    except json.JSONDecodeError:
                        arguments = {}
                    events.append(ToolCallStarted(name, arguments))
                for event in events:
                    if text := render(event, detail):
                        say(text)
            case "tool":
                shown = restored.display.get(message["tool_call_id"], {})
                result = ToolResult(
                    message["content"],
                    shown.get("is_error", message["content"].startswith("error")),
                    shown.get("title"),
                    shown.get("detail"),
                )
                name = names.get(message["tool_call_id"], "?")
                if text := render(ToolCallFinished(name, result), detail):
                    say(text)


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
    resume: str | None = None,  # option de lancement --resume
    host_workdir: str | None = None,  # identité du dossier ; défaut : le chemin local
    on_refusal: Callable[[str], None]
    | None = None,  # refus de reprise (stderr) ; défaut : write
    secrets: tuple[str, ...] = (),  # valeurs masquées dans le journal et les sorties
) -> int:
    env = environment or LocalEnvironment(
        max_output_chars=config.tools.max_output_chars
    )

    def say(text: str = "") -> None:
        write(text + "\n")

    def refuse(text: str) -> None:
        (on_refusal or write)(text + "\n")

    # --- Démarrage (ADR-0008 §6) : config → reprise → --model → check → affichage → invite
    host = host_workdir or str(env.workdir)
    stale_s = config.sessions.lock_stale_s

    async def open_session(
        ref: str | None, override: str | None, report: Callable[[str], None]
    ) -> Opened | int:
        """Ouvre une session neuve ou reprise ; sinon rend le code de sortie du refus."""
        opened = await startup.open_session(
            config,
            client_factory,
            env,
            host,
            secrets,
            resume=ref,
            model_override=override,
        )
        if isinstance(opened, Refused):
            (report if opened.journal_failure else say)(opened.message)
            return 2 if opened.journal_failure else 1
        return opened

    opened = await open_session(resume, model_override, refuse)
    if isinstance(opened, int):
        return opened
    assert opened.journal is not None  # le REPL enregistre toujours
    journal, alias = opened.journal, opened.alias
    # Purge après l'ouverture : la session reprise est verrouillée, donc épargnée.
    startup.purge_at_launch(config, env, say, refuse)
    session = Session(config, opened.client, env, journal, opened.restored, secrets)
    detail = opened.restored.detail if opened.restored else False

    def banner(current: Opened) -> None:
        j = current.journal
        assert j is not None
        say(f"Session : {j.session_id}" + (" (reprise)" if current.restored else ""))
        say(f"Dossier de travail : {env.workdir}")
        toolset = config.tools.toolset
        say(f"Ensemble d'outils : {toolset} ({', '.join(TOOLSETS[toolset])})")
        say(f"Modèle actif : {current.alias}")
        say(
            f"Limites : {config.limits.max_steps_per_turn} étapes par tour, "
            f"budget {format_usd(config.limits.budget_usd)}"
        )
        profile = config.models[current.alias]
        if profile.api_base and (
            profile.input_price_per_mtok is None
            or profile.output_price_per_mtok is None
        ):
            say("Coût non estimé pour ce modèle : le budget ne s'applique pas.")
        say("Commandes : " + " · ".join(COMMANDS))
        for warning in j.warnings:
            say(f"Avertissement : {warning}")
        if current.restored is not None:
            say(
                f"Reprise de la session {j.session_id} — créée le {j.created[:10]} · "
                f"modèle {current.alias} · {session.cost.display()}"
            )
            _replay(current.restored, detail, say)

    banner(opened)

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

    def record(write_state: Callable[..., None], *args) -> None:
        """Écriture d'état hors tour : un échec prévient, la conversation continue."""
        try:
            write_state(*args)
        except JournalError as failure:
            say(render(RecordingFailed(str(failure)), detail) or "")

    def warn_if_unrecorded() -> None:
        if (failure := session.take_recording_failure()) is not None:
            say(render(RecordingFailed(failure), detail) or "")

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

    async def switch_session(argument: str) -> None:
        """`/resume` : ferme la session courante et ouvre celle qui est choisie (spec §4.3)."""
        nonlocal journal, session, alias, detail
        infos = list_sessions(env.workdir, host, stale_s)
        if not argument:
            for line in format_sessions(infos, numbered=True) or [
                "Aucune session dans ce dossier."
            ]:
                say(line)
            return
        ref = argument
        if argument.isdigit() and len(argument) <= 3:  # numéro de la liste
            if not 1 <= int(argument) <= len(infos):
                say(
                    f"Numéro de session inconnu : {argument}. /resume liste les sessions."
                )
                return
            ref = infos[int(argument) - 1].id
        try:
            target = resolve(env.workdir, ref)
        except JournalError as failure:
            say(str(failure))
            return
        if target == journal.session_id:
            say("Cette session est déjà la session courante.")
            return
        # La cible est ouverte *avant* de fermer la courante : un refus ne perd rien.
        target_session = await open_session(target, None, say)
        if isinstance(target_session, int):
            return
        session.close()
        journal.close()
        assert target_session.journal is not None
        journal, alias = target_session.journal, target_session.alias
        session = Session(
            config,
            target_session.client,
            env,
            journal,
            target_session.restored,
            secrets,
        )
        detail = target_session.restored.detail if target_session.restored else False
        banner(target_session)

    def branch_session() -> None:
        """`/branch` : liste les demandes, puis repart d'avant celle qui est choisie."""
        requests = session.requests()
        if not requests:
            say("Aucune demande dans cette conversation : rien à rejouer.")
            return
        say("Demandes de la branche active :")
        for number, text in enumerate(requests, start=1):
            say(f"{number}. {' '.join(text.split())[:80]}")
        try:
            answer = read_line(
                "Repartir d'avant la demande n° (vide : annuler) "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            say()
            return
        if not answer.isdigit() or not 1 <= int(answer) <= len(requests):
            say("Aucun changement de branche.")
            return
        session.branch(int(answer) - 1)
        warn_if_unrecorded()
        say(
            "Attention : les fichiers du dossier de travail ne sont pas restaurés, ils "
            "peuvent différer de ce que cette branche a vu. Les fichiers déjà lus "
            "doivent être relus avant d'être modifiés."
        )
        say("Saisissez la nouvelle demande.")

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
        except ProviderError as failure:
            say(f"{failure.message_fr}\nLe modèle actif reste : {alias}.")
            return
        session.set_client(new_client)
        record(journal.model_changed, new_alias)
        alias = new_alias
        say(f"Modèle actif : {alias}")

    try:
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
                record(journal.display_mode, detail)
                say("Mode détaillé : " + ("activé" if detail else "désactivé"))
            elif line == "/resume" or line.startswith("/resume "):
                await switch_session(line[len("/resume") :].strip())
            elif line == "/branch":
                branch_session()
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
    finally:
        session.close()  # nettoie un run non enregistré, même sur exception
        journal.close()  # rend le verrou de session

    say(f"Total de la session — {session.cost.display()}")
    return 0
