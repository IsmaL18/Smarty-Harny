"""Résilience du tour : échec fournisseur en milieu de tour, exception inattendue,
message coupé par `length`, annulation externe.

Spec 001 §6 ; ADR-0001 §7, ADR-0002 §4, ADR-0005 §2 (amendé).
"""

import asyncio

import pytest
from support import (
    Console,
    Hang,
    ScriptedModel,
    call,
    collect,
    ended_with,
    make_config,
    make_session,
    one_turn,
    run_repl,
    say,
    tools,
)

from harness.models.base import ModelResponse, ProviderError


def assert_history_is_valid(messages: list[dict]) -> None:
    """Contrat du format OpenAI chat : chaque `tool_call` de l'assistant a un
    résultat `tool` et un seul ; aucun résultat n'est orphelin."""
    asked = [c["id"] for m in messages for c in (m.get("tool_calls") or [])]
    answered = [m["tool_call_id"] for m in messages if m.get("role") == "tool"]
    assert sorted(asked) == sorted(answered), (
        f"historique invalide : appels {asked}, résultats {answered}"
    )


async def test_provider_failure_after_a_successful_tool_call_keeps_session_usable_and_history_valid(
    workdir,
):
    """ADR-0001 §7 : l'échec survient après un outil réussi ; la session reste
    ouverte, l'historique envoyé ensuite est valide et garde le résultat de l'outil."""
    read = call("write_file", path="trace.txt", content="écrit avant la panne")
    model = ScriptedModel(
        [
            tools(read),
            ProviderError("other", "Panne du fournisseur (test)."),
            say("je reprends"),
        ]
    )
    console = Console(
        "fais le fichier",
        "réessaie",
    )

    await run_repl(console, make_config(), {"scripted": model}, workdir)

    assert (workdir / "trace.txt").read_text() == "écrit avant la panne"
    assert "Panne du fournisseur (test)." in console.shown_before_read(1)
    assert len(console.reads) == 3, "la session ne doit pas se fermer sur l'erreur"
    assert len(model.calls) == 3
    assert_history_is_valid(model.last_seen)
    assert model.saw_text("réessaie")
    assert model.saw_text("trace.txt")


class _ExplodingClient:
    """Client dont le premier appel lève une exception qui n'est pas une `ProviderError`."""

    def __init__(self, then: ScriptedModel) -> None:
        self.then = then
        self.exploded = False

    async def complete(self, messages, tools):
        if not self.exploded:
            self.exploded = True
            raise RuntimeError("bug inattendu du client (test)")
        return await self.then.complete(messages, tools)

    async def check(self) -> None:
        return None


async def test_unexpected_client_exception_does_not_crash_the_repl(workdir):
    """Une exception non prévue du client ne ferme pas le REPL : un message
    s'affiche et la demande suivante est traitée."""
    follow_up = ScriptedModel([say("toujours là")])
    client = _ExplodingClient(follow_up)
    console = Console("première", "seconde")
    config = make_config()

    from support import make_environment

    from harness.cli import repl

    await asyncio.wait_for(
        repl.run(
            config,
            lambda profile: client,
            console.read_line,
            console.write,
            environment=make_environment(config, workdir),
        ),
        30,
    )

    assert len(console.reads) == 3, "le REPL a planté ou s'est fermé sur l'exception"
    assert follow_up.saw_text("seconde", 0)
    assert "toujours là" in console.after_last_read + console.text


async def test_cut_off_message_with_tool_calls_runs_nothing_and_informs_the_model(
    workdir,
):
    """ADR-0002 §4 : `finish_reason = length` avec appels d'outils : aucun n'est
    exécuté (arguments probablement tronqués) ; le modèle reçoit une erreur par appel."""
    cut = call("write_file", path="tronque.txt", content="début seulement")
    cut_response = ModelResponse(
        message={"role": "assistant", "content": None, "tool_calls": [cut]},
        finish_reason="length",
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        cost_usd=0.0,
    )

    model, events = await one_turn(workdir, cut_response, say("je réessaie plus court"))

    assert not (workdir / "tronque.txt").exists(), "un appel tronqué a été exécuté"
    assert "cut off" in model.tool_output(cut)
    assert_history_is_valid(model.last_seen)
    assert ended_with(events) == "done"


async def test_external_timeout_around_a_turn_is_not_swallowed_silently(workdir):
    """ADR-0005 §2 (amendé) : le tour absorbe l'annulation (il se termine
    `interrupted`, historique valide) mais ne l'efface pas : une annulation externe
    (`asyncio.timeout`) reste observable par l'appelant."""
    model = ScriptedModel([Hang(60)])
    session = make_session(make_config(), workdir, model)
    seen: dict = {}

    async with asyncio.timeout(0.5) as scope:
        events = await collect(session.run_turn("demande lente"))
        seen["reason"] = ended_with(events)
        seen["cancelling"] = (
            asyncio.current_task() or pytest.fail("pas de tâche")
        ).cancelling()

    assert seen["reason"] == "interrupted"
    assert scope.expired(), "le délai externe n'a pas été pris en compte"
    assert seen["cancelling"] > 0, "l'annulation externe a été effacée par le tour"
