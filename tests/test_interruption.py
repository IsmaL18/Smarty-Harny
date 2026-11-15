"""Ctrl+C pendant un tour : vrai SIGINT envoyé au processus de test.

Spec 001 §4.1, §6, CA-18 ; ADR-0005. Notion : boucle-agent.
Le minuteur est armé au moment où l'utilisateur « tape » sa demande. Si le
harness n'installe pas son propre gestionnaire, le SIGINT est seulement noté
par la fixture `sigint` (voir conftest) et le test échoue proprement.
"""

import time

from support import (
    Console,
    Hang,
    ScriptedModel,
    call,
    make_config,
    run_repl,
    say,
    tools,
)


async def test_ctrl_c_during_a_long_command_kills_it_and_next_request_sees_the_interruption(
    workdir, sigint
):
    """CA-18 : la commande est tuée, l'invite revient, la session reste ouverte et
    la demande suivante part avec un modèle informé (`[INTERRUPTED by user]`)."""
    long_command = call("shell", command="echo commence; sleep 30; echo jamais")
    model = ScriptedModel([tools(long_command), say("J'ai vu l'interruption.")])

    def type_request() -> str:
        sigint.after(1.0)
        return "lance la commande longue"

    console = Console(type_request, "et maintenant ?")

    started = time.monotonic()
    # Délai de commande à 10 s : seul Ctrl+C peut l'arrêter avant.
    await run_repl(console, make_config(timeout=10.0), {"scripted": model}, workdir)
    elapsed = time.monotonic() - started

    assert sigint.unhandled == 0, "le SIGINT n'a pas été pris en charge par le harness"
    assert elapsed < 8, f"la commande n'a pas été tuée par Ctrl+C ({elapsed:.1f} s)"
    assert len(model.calls) == 2
    assert model.saw_text("et maintenant ?", 1)
    assert "[INTERRUPTED by user]" in model.tool_output(long_command)
    assert len(console.reads) >= 3, "l'invite n'est pas revenue après l'interruption"


async def test_ctrl_c_during_the_model_call_interrupts_the_turn_and_keeps_the_session(
    workdir, sigint
):
    """Spec §6 / ADR-0005 §2 : Ctrl+C pendant l'appel au modèle interrompt le
    tour proprement ; la session reste ouverte et la demande d'origine est
    conservée dans l'historique."""
    model = ScriptedModel([Hang(60), say("D'accord.")])

    def type_request() -> str:
        sigint.after(0.5)
        return "première demande"

    console = Console(type_request, "seconde demande")

    started = time.monotonic()
    await run_repl(console, make_config(), {"scripted": model}, workdir)
    elapsed = time.monotonic() - started

    assert sigint.unhandled == 0, "le SIGINT n'a pas été pris en charge par le harness"
    assert elapsed < 8, f"l'appel au modèle n'a pas été interrompu ({elapsed:.1f} s)"
    assert len(model.calls) == 2
    assert model.saw_text("première demande", 1)
    assert model.saw_text("seconde demande", 1)
