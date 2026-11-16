"""Session : historique, limites et boucle d'un tour (ADR-0001, ADR-0004, ADR-0005).

Notion : boucle-agent (docs/notions/boucle-agent.md).

Le noyau n'écrit jamais dans le terminal et ne pose aucune question : un tour est un
générateur asynchrone d'événements typés, que l'interface (CLI aujourd'hui, TUI ou API
demain) consomme. « Continuer ? » est posé par l'interface, qui appelle `resume_turn`.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from harness.config import Config
from harness.cost import CostTracker, format_usd
from harness.events import (
    AssistantMessage,
    LimitKind,
    LimitReached,
    ProviderFailed,
    RecordingFailed,
    StepCompleted,
    ToolCallFinished,
    ToolCallStarted,
    TurnEnded,
)
from harness.models.base import ModelClient, ProviderError
from harness.prompt import SYSTEM_PROMPT
from harness.tools.base import ToolRegistry, ToolResult
from harness.tools.edit_file import EditFile
from harness.tools.environment import Environment
from harness.tools.filestate import FileTracker
from harness.tools.outputs import OutputStore
from harness.tools.read_file import ReadFile
from harness.tools.shell import Shell
from harness.tools.toolsets import TOOLSETS
from harness.tools.write_file import WriteFile

Event = (
    ToolCallStarted
    | ToolCallFinished
    | AssistantMessage
    | StepCompleted
    | LimitReached
    | ProviderFailed
    | RecordingFailed
    | TurnEnded
)


class StoreError(Exception):
    """Le magasin n'a pas pu enregistrer : le noyau désactive l'enregistrement."""


class SessionStore(Protocol):
    """Enregistrement durable de la session, défini côté noyau (ADR-0012 §Conséquences).

    Le noyau ne sait pas où ni comment c'est écrit ; l'adaptateur vit dans `sessions/`.
    """

    @property
    def session_id(self) -> str: ...
    def message(self, message: dict, display: dict | None = None) -> None: ...
    def usage(self, usage: dict, cost_usd: float | None) -> None: ...
    def retract(self) -> None: ...
    def file_seen(self, path: str, digest: str) -> None: ...
    def branch(self, request: int) -> None: ...
    def interrupted(self) -> None: ...
    def granted(self, kind: str) -> None: ...


@dataclass(frozen=True)
class RestoredState:
    """Ce qu'une session reprise rend au noyau, reconstruit depuis son journal."""

    messages: list[dict]  # historique de la branche active, sans le message système
    usages: list[tuple[dict, float | None]]  # tous les appels, toutes branches
    model: str  # alias du modèle actif à la fermeture
    files: dict[str, str]  # fichiers déjà lus (chemin → empreinte), branche active
    detail: bool  # mode d'affichage à la fermeture
    display: dict[str, dict]  # titre/diff des résultats d'action, par tool_call_id
    budget_grants: int = (
        0  # tranches de budget accordées, toutes branches (ADR-0012 §2)
    )


INTERRUPTED = "[INTERRUPTED by user]"
NOT_RUN = "[NOT RUN: turn interrupted by user]"
INTERRUPTED_BEFORE_ANSWER = (
    "[The user interrupted the previous request before you answered.]"
)
# Message au modèle après un changement de branche (spec §4.5, ADR-0012 §2).
BRANCH_NOTICE = (
    "[The conversation was moved back to an earlier request. The files in the working "
    "folder were NOT restored and may differ from what this branch saw: read a file "
    "again before modifying it.]"
)
# Messages `user` qui ne sont pas des demandes de l'utilisateur.
NOT_REQUESTS = frozenset({INTERRUPTED_BEFORE_ANSWER, BRANCH_NOTICE})
CUT_OFF = (
    "error: your message was cut off by the output limit; retry with smaller content"
)


class Session:
    def __init__(
        self,
        config: Config,
        client: ModelClient,
        environment: Environment,
        store: SessionStore | None = None,
        restored: RestoredState | None = None,
        secrets_: tuple[str, ...] = (),
    ):
        self._config = config
        self._client = client
        self._store = store
        self._recording = store is not None  # faux dès le premier échec du magasin
        self._failure: str | None = None  # échec à signaler à l'interface
        # État de session partagé par les outils, injecté à leur construction (ADR-0009 §4).
        self._tracker = tracker = FileTracker(self._file_seen if store else None)
        # Une session enregistrée garde ses sorties tant qu'elle existe (ADR-0012 §5).
        self._outputs = OutputStore(
            environment.workdir,
            config.tools.max_saved_output_mb,
            (lambda: store.session_id) if store else None,
            secrets_,
        )
        catalog = [
            ReadFile(config.tools.max_read_chars, tracker),
            WriteFile(tracker),
            EditFile(tracker),
            Shell(config.tools.command_timeout_s, tracker, self._outputs),
        ]
        # Le modèle ne voit et ne peut appeler que l'ensemble actif (ADR-0009 §3).
        active = TOOLSETS[config.tools.toolset]
        self._registry = ToolRegistry(
            [tool for tool in catalog if tool.name in active], environment
        )
        self.cost = CostTracker()
        # Historique au format OpenAI chat, en ajout seul (sauf le retrait documenté
        # d'une demande restée sans réponse, ADR-0001 §7). Le système ne change jamais.
        self._history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._step_allowance = config.limits.max_steps_per_turn
        self._budget_ceiling = config.limits.budget_usd
        self._steps = 0
        self._last_limit: LimitKind | None = None
        self._unanswered: list[
            dict
        ] = []  # appels d'outils sans résultat (invariant d'historique)
        self._actions: list[str] = []
        self._user_index = -1
        if restored is not None:
            # Restauré sans réécrire : ces messages sont déjà dans le journal.
            self._history.extend(restored.messages)
            for usage, cost_usd in restored.usages:
                self.cost.add(cost_usd, usage)
            tracker.restore(restored.files)
            self._budget_ceiling += restored.budget_grants * config.limits.budget_usd

    def close(self) -> None:
        """Fin de session : seul un run non enregistré supprime ses sorties (ADR-0012 §5)."""
        if self._store is None:
            self._outputs.cleanup()

    def requests(self) -> list[str]:
        """Demandes de l'utilisateur de la branche active, dans l'ordre (spec §4.5)."""
        return [str(m["content"]) for m in self._history if _is_request(m)]

    def branch(self, request: int) -> None:
        """Repart d'avant la demande n° `request` (0 = la première) : l'historique s'arrête
        là. Les fichiers du dossier ne sont pas restaurés : on le dit au modèle."""
        index = [i for i, m in enumerate(self._history) if _is_request(m)][request]
        self._record("branch", request)
        del self._history[index:]
        self._unanswered = []
        self._tracker.reset()
        self._append({"role": "user", "content": BRANCH_NOTICE})

    def set_client(self, client: ModelClient) -> None:
        """Changement de modèle : l'historique et le coût cumulé sont conservés."""
        self._client = client

    async def run_turn(self, text: str) -> AsyncIterator[Event]:
        self._steps = 0
        self._step_allowance = self._config.limits.max_steps_per_turn
        self._actions = []
        self._last_limit = None
        self._append({"role": "user", "content": text})
        self._user_index = len(self._history) - 1
        async for event in self._stream():
            yield event

    async def _stream(self) -> AsyncIterator[Event]:
        """La boucle, plus l'avertissement d'enregistrement dès qu'il est connu."""
        async for event in self._loop():
            if (failure := self.take_recording_failure()) is not None:
                yield RecordingFailed(failure)
            yield event

    def take_recording_failure(self) -> str | None:
        """Échec d'enregistrement pas encore signalé (une seule fois par session)."""
        failure, self._failure = self._failure, None
        return failure

    def _record(self, operation: str, *args) -> None:
        """Seule porte vers le magasin : une erreur le désactive, la conversation reste."""
        if not self._recording or self._store is None:
            return
        try:
            getattr(self._store, operation)(*args)
        except StoreError as failure:
            self._recording = False
            self._failure = str(failure)

    def _file_seen(self, path: str, digest: str) -> None:
        self._record("file_seen", path, digest)

    async def resume_turn(self, grant: bool) -> AsyncIterator[Event]:
        """Reprend après une limite : une tranche identique est accordée (ADR-0001 §6)."""
        if not grant or self._last_limit is None:
            return
        if self._last_limit == "step":
            self._step_allowance += self._config.limits.max_steps_per_turn
        else:
            self._budget_ceiling += self._config.limits.budget_usd
        self._record("granted", self._last_limit)
        self._last_limit = None
        async for event in self._stream():
            yield event

    # ------------------------------------------------------------------ boucle

    async def _loop(self) -> AsyncIterator[Event]:
        try:
            while True:
                # Les limites sont vérifiées *avant* chaque appel au modèle (ADR-0001 §5).
                limit = self._check_limits()
                if limit is not None:
                    kind, summary = limit
                    self._last_limit = kind
                    yield LimitReached(kind, summary)
                    yield TurnEnded("step_limit" if kind == "step" else "budget_limit")
                    return

                try:
                    response = await self._client.complete(
                        self._history, self._registry.specs()
                    )
                except ProviderError as error:
                    if len(self._history) - 1 == self._user_index:
                        self._retract()  # demande sans réponse : retirée (ADR-0001 §7)
                    yield ProviderFailed(error)
                    yield TurnEnded("provider_error")
                    return
                except Exception as exc:  # noqa: BLE001 - un client défaillant ne tue pas le REPL
                    if len(self._history) - 1 == self._user_index:
                        self._retract()
                    yield ProviderFailed(
                        ProviderError(
                            "other", f"Erreur inattendue ({type(exc).__name__}) : {exc}"
                        )
                    )
                    yield TurnEnded("provider_error")
                    return

                self._steps += 1
                self.cost.add(response.cost_usd, response.usage)
                message = _clean_assistant_message(response.message)
                self._record("usage", response.usage, response.cost_usd)
                self._append(message)
                yield StepCompleted(response.usage, response.cost_usd)

                tool_calls = message.get("tool_calls") or []
                if message.get("content"):
                    yield AssistantMessage(message["content"])
                if not tool_calls:
                    yield TurnEnded("done")
                    return

                self._unanswered = list(tool_calls)
                for tool_call in tool_calls:
                    name = tool_call["function"]["name"]
                    yield ToolCallStarted(
                        name, _parse_arguments(tool_call), tool_call["id"]
                    )
                    if response.finish_reason == "length":
                        # Arguments probablement tronqués : on n'exécute pas (ADR-0002 §4).
                        result = ToolResult(CUT_OFF, True)
                    else:
                        self._actions.append(_describe(tool_call))
                        result = await self._registry.execute(tool_call)
                    self._answer(tool_call, result)
                    yield ToolCallFinished(name, result, tool_call["id"])
        except asyncio.CancelledError:
            # Ctrl+C : le noyau absorbe l'annulation au niveau du tour (ADR-0005 §2) et
            # referme l'historique de façon valide : un résultat par appel d'outil.
            # Pas de `uncancel()` : le compteur d'annulation reste visible de l'appelant,
            # qui peut ainsi distinguer une annulation externe (asyncio.timeout, TaskGroup).
            finished = []
            if self._unanswered:
                for index, tool_call in enumerate(list(self._unanswered)):
                    result = ToolResult(INTERRUPTED if index == 0 else NOT_RUN, True)
                    self._answer(tool_call, result)
                    finished.append(
                        ToolCallFinished(
                            tool_call["function"]["name"], result, tool_call["id"]
                        )
                    )
            else:
                self._append({"role": "user", "content": INTERRUPTED_BEFORE_ANSWER})
            self._record("interrupted")  # état enregistré : visible dans le journal
            for event in finished:
                yield event
            yield TurnEnded("interrupted")

    def _append(self, message: dict, display: dict | None = None) -> None:
        """Point unique d'ajout à l'historique : la mémoire et le journal restent d'accord."""
        self._history.append(message)
        self._record("message", message, display)

    def _retract(self) -> None:
        self._history.pop()
        self._record("retract")

    def _answer(self, tool_call: dict, result: ToolResult) -> None:
        # Ce que le modèle ne voit pas (titre, diff) suit le message, pour le rejeu.
        self._append(
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result.content,
            },
            {
                "is_error": result.is_error,
                "title": result.title,
                "detail": result.detail,
            },
        )
        self._unanswered = [c for c in self._unanswered if c["id"] != tool_call["id"]]

    def _check_limits(self) -> tuple[LimitKind, str] | None:
        recent = ", ".join(self._actions[-5:]) or "aucune"
        if self._steps >= self._step_allowance:
            return (
                "step",
                (
                    f"Limite d'étapes atteinte : {self._steps} étapes dans ce tour. "
                    f"Dernières actions : {recent}."
                ),
            )
        if self.cost.known_usd >= self._budget_ceiling:
            return (
                "budget",
                (
                    f"Budget atteint : {format_usd(self.cost.known_usd)} dépensés "
                    f"sur {format_usd(self._budget_ceiling)}. Dernières actions : {recent}."
                ),
            )
        return None


def _is_request(message: dict) -> bool:
    return message.get("role") == "user" and message.get("content") not in NOT_REQUESTS


def _clean_assistant_message(message: dict) -> dict:
    """Réduit le message à role/content/tool_calls : pas de champ propre à un fournisseur."""
    cleaned: dict = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        cleaned["tool_calls"] = message["tool_calls"]
    return cleaned


def _parse_arguments(tool_call: dict) -> dict:
    raw = tool_call["function"].get("arguments") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}


def _describe(tool_call: dict) -> str:
    args = _parse_arguments(tool_call)
    target = args.get("path") or args.get("command") or ""
    return f"{tool_call['function']['name']}({str(target)[:60]})"
