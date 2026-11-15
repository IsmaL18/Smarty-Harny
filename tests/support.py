"""Aides de test partagées : modèle simulé, constructeurs de réponses, console simulée.

Ces aides appartiennent au rôle test-writer (ADR-0008 §3). Elles ne pilotent le
harness que par ses points d'entrée publics : `Session`, `cli.repl.run`, le
protocole `ModelClient`. Aucune ne dépend de l'organisation interne du code.
"""

from __future__ import annotations

import asyncio
import copy
import itertools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from harness.config import Config, Limits, ModelProfile, ToolsConfig
from harness.models.base import ModelResponse, ProviderError
from harness.tools.environment import LocalEnvironment

_ids = itertools.count(1)


# --------------------------------------------------------------------------
# Constructeurs de réponses du modèle (format OpenAI chat, ADR-0001 §3)
# --------------------------------------------------------------------------


def call(name: str, **arguments) -> dict:
    """Un appel d'outil tel que le modèle le demande (identifiant unique)."""
    return {
        "id": f"call_{next(_ids)}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def tools(*calls: dict, cost: float | None = 0.0) -> ModelResponse:
    """Réponse du modèle qui demande un ou plusieurs appels d'outils."""
    return ModelResponse(
        message={"role": "assistant", "content": None, "tool_calls": list(calls)},
        finish_reason="tool_calls",
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        cost_usd=cost,
    )


def say(text: str, cost: float | None = 0.0) -> ModelResponse:
    """Réponse finale du modèle, sans appel d'outil."""
    return ModelResponse(
        message={"role": "assistant", "content": text},
        finish_reason="stop",
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        cost_usd=cost,
    )


@dataclass(frozen=True)
class Hang:
    """Étape de script : l'appel au modèle ne répond pas (pour Ctrl+C pendant l'appel)."""

    seconds: float = 60.0


Step = ModelResponse | ProviderError | Hang


# --------------------------------------------------------------------------
# Modèle simulé
# --------------------------------------------------------------------------


@dataclass
class ScriptedModel:
    """Implémente `ModelClient` avec des réponses prédéfinies.

    - `script` : réponses rendues dans l'ordre ; une `ProviderError` est levée ;
      un `Hang` fait attendre l'appel.
    - `then` : fabrique appelée quand le script est épuisé (p. ex. « toujours un
      appel d'outil » pour atteindre une limite). Sans elle, le modèle répond
      « fin du script ».
    - `check_error` : levée par `check()` (vérification au démarrage / `/model`).
    - `calls` : copie des messages reçus à chaque appel, pour que les tests
      inspectent ce que le modèle a vu.
    """

    script: list[Step] = field(default_factory=list)
    then: Callable[[], ModelResponse] | None = None
    check_error: ProviderError | None = None
    calls: list[list[dict]] = field(default_factory=list)
    tools_seen: list[list[dict]] = field(default_factory=list)

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelResponse:
        self.calls.append(copy.deepcopy(messages))
        self.tools_seen.append(copy.deepcopy(tools))
        if self.script:
            step = self.script.pop(0)
        elif self.then is not None:
            step = self.then()
        else:
            step = say("fin du script")
        if isinstance(step, ProviderError):
            raise step
        if isinstance(step, Hang):
            await asyncio.sleep(step.seconds)
            return say("réponse arrivée après l'attente")
        return step

    async def check(self) -> None:
        if self.check_error is not None:
            raise self.check_error

    # --- lecture de ce que le modèle a vu ---

    @property
    def last_seen(self) -> list[dict]:
        assert self.calls, "le modèle n'a jamais été appelé"
        return self.calls[-1]

    def tool_output(self, tool_call: dict) -> str:
        """Contenu du résultat d'outil reçu par le modèle pour cet appel."""
        outputs = tool_outputs(self.last_seen, tool_call["id"])
        assert len(outputs) == 1, (
            f"l'appel {tool_call['id']} devrait avoir exactement un résultat, "
            f"trouvé {len(outputs)}"
        )
        return outputs[0]

    def saw_text(self, needle: str, call_index: int = -1) -> bool:
        """Le texte apparaît-il dans un message reçu lors de l'appel donné ?"""
        return any(needle in _text_of(m) for m in self.calls[call_index])


def tool_outputs(messages: list[dict], call_id: str) -> list[str]:
    return [
        _text_of(m)
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id") == call_id
    ]


def _text_of(message: dict) -> str:
    """Texte d'un message, que `content` soit une chaîne ou une liste de blocs."""
    content = message.get("content")
    if content is None:
        text = ""
    elif isinstance(content, str):
        text = content
    else:
        text = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    if message.get("tool_calls"):
        text += " " + json.dumps(message["tool_calls"])
    return text


# --------------------------------------------------------------------------
# Configuration et environnement
# --------------------------------------------------------------------------


def make_config(
    *,
    max_steps: int = 25,
    budget: float = 1.0,
    max_read: int = 40000,
    max_output: int = 20000,
    timeout: float = 5.0,
    models: dict[str, ModelProfile] | None = None,
    default: str = "scripted",
) -> Config:
    """Configuration de test : délais courts, un profil simulé par défaut."""
    if models is None:
        models = {"scripted": ModelProfile(model="openai/scripted-model")}
    return Config(
        default_model=default,
        models=models,
        limits=Limits(max_steps_per_turn=max_steps, budget_usd=budget),
        tools=ToolsConfig(
            max_read_chars=max_read,
            max_output_chars=max_output,
            command_timeout_s=timeout,
        ),
    )


def make_environment(config: Config, workdir: Path) -> LocalEnvironment:
    """Le vrai environnement local, réglé comme la configuration."""
    return LocalEnvironment(
        workdir=workdir, max_output_chars=config.tools.max_output_chars
    )


async def collect(events, timeout: float = 30.0) -> list:
    """Consomme un tour (`run_turn` / `resume_turn`) et rend ses événements.

    Borné dans le temps : un tour bloqué fait échouer le test au lieu de le figer.
    """

    async def consume() -> list:
        return [event async for event in events]

    return await asyncio.wait_for(consume(), timeout)


def make_session(config: Config, workdir: Path, model: ScriptedModel):
    """Une session réelle (vrais outils, vrai environnement) pilotée par le modèle simulé."""
    from harness.session import Session

    return Session(config, model, make_environment(config, workdir))


async def one_turn(
    workdir: Path,
    *script: Step,
    text: str = "fais la tâche",
    config: Config | None = None,
) -> tuple[ScriptedModel, list]:
    """Joue un tour complet avec le script donné ; rend le modèle et les événements."""
    model = ScriptedModel(list(script))
    session = make_session(config or make_config(), workdir, model)
    events = await collect(session.run_turn(text))
    return model, events


def ended_with(events: list) -> str:
    """Raison de fin du tour (`TurnEnded.reason`)."""
    from harness.events import TurnEnded

    ends = [e for e in events if isinstance(e, TurnEnded)]
    assert len(ends) == 1, (
        f"un tour doit se terminer par un seul TurnEnded : {events!r}"
    )
    assert events[-1] is ends[0], "TurnEnded doit être le dernier événement du tour"
    return ends[0].reason


# --------------------------------------------------------------------------
# Console simulée pour le REPL
# --------------------------------------------------------------------------

Entry = str | BaseException | Callable[[], str]


class Console:
    """Simule le terminal : `read_line` rend les entrées prévues, `write` capture.

    Une entrée peut être une ligne, une exception à lever (`KeyboardInterrupt`
    pour Ctrl+C, `EOFError` pour Ctrl+D) ou une fonction appelée au moment de
    la lecture (pour déclencher un minuteur). Script épuisé : Ctrl+D.
    """

    def __init__(self, *entries: Entry, probe: Callable[[], object] | None = None):
        self.entries: list[Entry] = list(entries)
        self.output: list[str] = []
        # `probe` est appelée à chaque lecture (p. ex. nombre d'appels au modèle à cet instant).
        self.probe = probe
        self.probes: list[object] = []
        # Pour chaque lecture : (texte affiché depuis la lecture précédente + invite, réponse).
        self.reads: list[tuple[str, str]] = []
        self._mark = 0

    def write(self, text: str) -> None:
        self.output.append(str(text))

    def read_line(self, prompt: str = "") -> str:
        shown = "".join(self.output[self._mark :]) + str(prompt)
        self._mark = len(self.output)
        if self.probe is not None:
            self.probes.append(self.probe())
        entry: Entry = self.entries.pop(0) if self.entries else EOFError()
        if isinstance(entry, BaseException):
            self.reads.append((shown, f"<{type(entry).__name__}>"))
            raise entry
        if callable(entry):
            entry = entry()
        self.reads.append((shown, entry))
        return entry

    @property
    def text(self) -> str:
        return "".join(self.output)

    @property
    def after_last_read(self) -> str:
        """Texte affiché après la dernière lecture (p. ex. à la sortie)."""
        return "".join(self.output[self._mark :])

    def shown_before_read(self, index: int) -> str:
        """Texte affiché (et invite) juste avant la lecture n° `index`."""
        return self.reads[index][0]

    def questions_continue(self) -> int:
        """Nombre de fois où « continuer ? » a été demandé."""
        return sum(
            1
            for shown, _ in self.reads
            if re.search(r"continuer", shown, re.IGNORECASE)
        )


async def run_repl(
    console: Console,
    config: Config,
    models: dict[str, ScriptedModel],
    workdir: Path | None = None,
    *,
    model_override: str | None = None,
    timeout: float = 30.0,
) -> None:
    """Lance le REPL complet avec la console simulée.

    `models` associe chaque alias de la configuration au modèle simulé que
    `client_factory` rendra pour ce profil. Sans `workdir`, le REPL utilise son
    environnement par défaut (dossier courant du processus).
    """
    from harness.cli import repl

    by_profile = {config.models[alias].model: model for alias, model in models.items()}

    def client_factory(profile: ModelProfile) -> ScriptedModel:
        return by_profile[profile.model]

    environment = make_environment(config, workdir) if workdir is not None else None
    await asyncio.wait_for(
        repl.run(
            config,
            client_factory,
            console.read_line,
            console.write,
            model_override=model_override,
            environment=environment,
        ),
        timeout,
    )


def money(amount: str) -> re.Pattern[str]:
    """Montant en dollars, virgule ou point décimal, zéros finaux facultatifs
    (« 0,0300 », « 0.03 »), non collé à d'autres chiffres."""
    integer, decimals = amount.split(".")
    decimals = decimals.rstrip("0") or "0"
    return re.compile(rf"(?<![\d.,]){integer}[.,]{decimals}0*(?!\d)")
