"""Mode headless : une demande en argument, sortie texte ou JSONL, code de sortie (ADR-0012 §7).

Notion : mode-headless. Le noyau est le même que celui du REPL : ce module consomme
`Session.run_turn` et ne l'appelle jamais avec `resume_turn`, donc ne pose jamais la
question « continuer ? ». Le statut du run vient du dernier événement `TurnEnded`.

Contrat avec le script appelant :
- stdout est réservé au protocole (réponse finale en texte, flux JSONL sinon) ;
- tout le reste (titres d'actions, coût, avertissements, erreurs) va sur stderr ;
- le code de sortie et la ligne finale `result` disent la même chose.
"""

import asyncio
import contextlib
import json
import os
import signal
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from harness.cli import startup
from harness.cli.render import render
from harness.cli.startup import Opened, Refused
from harness.config import Config, ModelProfile
from harness.events import (
    AssistantMessage,
    LimitReached,
    ProviderFailed,
    RecordingFailed,
    StepCompleted,
    ToolCallFinished,
    ToolCallStarted,
    TurnEnded,
)
from harness.models.base import ModelClient
from harness.session import Session
from harness.tools.environment import Environment, LocalEnvironment

# Codes de sortie (spec §4.8.3).
OK, FAILED, USAGE, LIMIT, INTERRUPTED = 0, 1, 2, 3, 130
# Version du schéma du flux JSONL, portée par `run_started` ; documentée dans le README.
SCHEMA = 1
_STATUS = {
    "done": ("ok", OK),
    "provider_error": ("error", FAILED),
    "step_limit": ("limit", LIMIT),
    "budget_limit": ("limit", LIMIT),
    "interrupted": ("interrupted", INTERRUPTED),
}


@contextlib.contextmanager
def _reserved_stdout() -> Iterator[int]:
    """Garde le descripteur 1 d'origine pour le seul protocole et rend un descripteur dessus.

    Pendant le run, le descripteur 1 et `sys.stdout` pointent vers stderr : une
    bibliothèque qui imprime, un `print` oublié, un sous-processus héritant de stdout ne
    peuvent plus polluer le flux que lit le script (spec §4.8.1, piège classique du
    headless). Tout est remis en place à la sortie, pour que `main` reste appelable
    plusieurs fois dans un même processus.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    protocol_fd = os.dup(1)
    saved_stdout = sys.stdout
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    try:
        yield protocol_fd
    finally:
        sys.stdout.flush()
        os.dup2(protocol_fd, 1)
        os.close(protocol_fd)
        sys.stdout = saved_stdout


@dataclass
class _Outcome:
    reason: str = (
        "interrupted"  # `TurnEnded.reason` ; « interrupted » si le tour est annulé
    )
    detail: str = ""  # cause ou limite, pour l'humain et la ligne finale
    error_kind: str | None = None
    answer: str | None = None
    steps: int = 0
    recording_failure: str | None = None  # l'enregistrement s'est arrêté (ADR-0012 §2)


@dataclass(frozen=True)
class _Channels:
    """Les trois sorties du run : protocole JSONL, protocole texte, journal humain (stderr)."""

    emit: Callable[[dict], None]
    write_out: Callable[[str], None]
    log: Callable[[str], None]


@dataclass(frozen=True)
class _Options:
    output_format: str
    model_override: str | None
    resume: str | None
    no_session: bool
    host: str
    secrets: tuple[str, ...]


async def run(
    config: Config,
    client_factory: Callable[[ModelProfile], ModelClient],
    prompt: str,
    *,
    output_format: str = "text",
    model_override: str | None = None,
    resume: str | None = None,
    no_session: bool = False,
    environment: Environment | None = None,
    host_workdir: str | None = None,
    secrets: tuple[str, ...] = (),
) -> int:
    env = environment or LocalEnvironment(
        max_output_chars=config.tools.max_output_chars
    )
    with _reserved_stdout() as protocol_fd:

        def write_out(text: str) -> None:
            """Seule porte vers le vrai stdout : un seul `write`, visible tout de suite."""
            os.write(protocol_fd, text.encode())

        def emit(obj: dict) -> None:
            write_out(json.dumps(obj, ensure_ascii=False) + "\n")

        def log(text: str) -> None:
            print(text, file=sys.stderr, flush=True)

        options = _Options(
            output_format, model_override, resume, no_session,
            host_workdir or str(env.workdir), secrets,
        )  # fmt: skip
        return await _run(
            config,
            client_factory,
            prompt,
            env,
            _Channels(emit, write_out, log),
            options,
        )


async def _run(
    config: Config,
    client_factory: Callable[[ModelProfile], ModelClient],
    prompt: str,
    env: Environment,
    out: _Channels,
    options: _Options,
) -> int:
    # --- Démarrage : tout échec ici est un code 2, rien n'a été exécuté ni écrit.
    opened = await startup.open_session(
        config, client_factory, env, options.host, options.secrets,
        resume=options.resume, model_override=options.model_override,
        record=not options.no_session,
    )  # fmt: skip
    if isinstance(opened, Refused):
        out.log(opened.message)
        return USAGE
    session = Session(
        config, opened.client, env, opened.journal, opened.restored, options.secrets
    )
    try:
        startup.purge_at_launch(config, env, out.log, out.log)
        return await _play(
            session, opened, prompt, env, out, options.output_format == "jsonl"
        )
    finally:
        session.close()
        if opened.journal:
            opened.journal.close()


async def _play(
    session: Session,
    opened: Opened,
    prompt: str,
    env: Environment,
    out: _Channels,
    jsonl: bool,
) -> int:
    emit, write_out, log = out.emit, out.write_out, out.log
    journal, alias, resumed = opened.journal, opened.alias, opened.restored is not None
    session_id = journal.session_id if journal else None
    if jsonl:
        emit(
            {
                "type": "run_started", "schema": SCHEMA, "session": session_id,
                "model": alias, "workdir": str(env.workdir), "resumed": resumed,
            }
        )  # fmt: skip
    else:
        log(
            f"Session : {session_id or 'aucune (--no-session)'}"
            + (" (reprise)" if resumed else "")
        )
    for warning in journal.warnings if journal else []:
        if jsonl:
            emit({"type": "warning", "message": warning})
        log(f"Avertissement : {warning}")

    outcome = _Outcome()

    def on_event(event: object) -> None:
        match event:
            case StepCompleted():
                outcome.steps += 1
                outcome.answer = (
                    None  # seul le texte du dernier message du tour est la réponse
                )
            case ToolCallStarted(name, arguments, call_id):
                if jsonl:
                    emit(
                        {
                            "type": "tool_call",
                            "id": call_id,
                            "name": name,
                            "arguments": arguments,
                        }
                    )
            case ToolCallFinished(name, result, call_id):
                if jsonl:
                    emit({
                        "type": "tool_result", "id": call_id, "name": name,
                        "content": result.content, "is_error": result.is_error,
                    })  # fmt: skip
            case AssistantMessage(text):
                if jsonl:
                    emit({"type": "assistant_message", "text": text})
                outcome.answer = text
            case LimitReached(_, summary):
                outcome.detail = summary
            case ProviderFailed(error):
                outcome.detail, outcome.error_kind = error.message_fr, error.kind
            case RecordingFailed(message):
                outcome.recording_failure = message
                if jsonl:
                    emit({"type": "warning", "message": message})
            case TurnEnded(reason):
                outcome.reason = reason
        # Texte lisible par un humain : toujours sur stderr, jamais sur stdout.
        if text := render(event, detail=False):
            log(text)

    async def drain() -> None:
        async for event in session.run_turn(prompt):
            on_event(event)

    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(drain())
    handled: list[signal.Signals] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            # Le processus du conteneur est le PID 1 : sans gestionnaire explicite,
            # SIGTERM (docker stop) serait ignoré (ADR-0012 §7).
            loop.add_signal_handler(signum, task.cancel)
            handled.append(signum)
        except (NotImplementedError, RuntimeError, ValueError):
            pass  # pas dans le thread principal : pas de signaux gérés
    try:
        await task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
        outcome.reason = "interrupted"  # annulé avant que le noyau ait pu conclure
    finally:
        for signum in handled:
            loop.remove_signal_handler(signum)

    status, code = _STATUS[outcome.reason]
    if outcome.recording_failure and status == "ok":
        # Un run qui n'a pas pu s'enregistrer n'est pas un succès pour le script (ADR §7).
        status, code, outcome.detail = "error", FAILED, outcome.recording_failure
    if outcome.reason == "interrupted":
        outcome.detail = "Interrompu par un signal."
    # La réponse finale n'existe que pour le statut `ok` (ADR-0012 « Points confirmés »).
    answer = outcome.answer if status == "ok" else None
    if jsonl:
        emit(
            {
                "type": "result", "status": status, "reason": outcome.detail or None,
                "error_kind": outcome.error_kind, "answer": answer,
                "steps": outcome.steps, "tokens": session.cost.tokens,
                "cost_usd": session.cost.known_usd, "session": session_id,
            }
        )  # fmt: skip
    elif answer is not None:
        write_out(answer + "\n")
    log(session.cost.display())
    if status == "limit":
        log(
            f"{outcome.steps} étape(s) dans ce run."
            + (f" Reprenez avec --resume {session_id}." if session_id else "")
        )
    return code
