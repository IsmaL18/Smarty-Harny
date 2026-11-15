"""Session en terminal vue par l'utilisateur : démarrage, sortie, affichage,
coût, limites et « continuer ? », Ctrl+C à l'invite.

Spec 001 §4.1, §4.3, §4.4, §6 ; ADR-0001 §6, ADR-0004 §5, ADR-0005 §1, ADR-0008.
Le REPL complet est lancé avec une console simulée (lignes tapées, texte
affiché) et le modèle simulé. Le format exact des lignes n'est pas un contrat
(ADR-0008 §Conséquences) : on ne vérifie que la présence ou l'absence des
informations que la spec exige.
"""

import re

import pytest
from support import (
    Console,
    ScriptedModel,
    call,
    make_config,
    money,
    run_repl,
    say,
    tools,
)

from harness.config import ModelProfile


async def test_startup_shows_workdir_active_model_and_limits_then_a_prompt(
    workdir, monkeypatch
):
    """CA-1 : lancé depuis un dossier (dossier courant du processus), le harness
    affiche ce dossier, le modèle actif et les limites, puis une invite."""
    monkeypatch.chdir(workdir)
    config = make_config(
        max_steps=37,
        budget=0.42,
        models={"principal": ModelProfile(model="openai/modele-principal")},
        default="principal",
    )
    console = Console()

    await run_repl(console, config, {"principal": ScriptedModel()})

    assert console.reads, "aucune invite n'a été affichée"
    startup = console.shown_before_read(0)
    assert str(workdir) in startup or str(workdir.resolve()) in startup
    assert "principal" in startup
    limits = startup.replace(str(workdir.resolve()), "").replace(str(workdir), "")
    assert re.search(r"(?<!\d)37(?!\d)", limits), "nombre maximal d'étapes non affiché"
    assert money("0.42").search(limits), "budget non affiché"


@pytest.mark.parametrize("ending", ["/quit", EOFError()], ids=["quit", "ctrl-d"])
async def test_quit_command_and_ctrl_d_end_the_session_showing_total_cost(
    workdir, ending
):
    """CA-3 : `/quit` ou Ctrl+D termine la session et affiche le coût total."""
    console = Console("bonjour", ending)

    await run_repl(
        console,
        make_config(),
        {"scripted": ScriptedModel([say("salut", cost=0.0123)])},
        workdir,
    )

    assert len(console.reads) == 2, "la session a continué à lire après la sortie"
    assert money("0.0123").search(console.after_last_read), (
        "coût total absent à la sortie"
    )


async def test_events_show_as_titles_by_default_and_in_full_after_toggling_detail(
    workdir,
):
    """CA-12 et CA-13 : par défaut une ligne-titre par événement, sans arguments
    ni résultat complets ; `/detail` affiche le détail complet ; un second
    `/detail` revient aux titres."""
    read_result = "resultat-integral-" + "r" * 80
    (workdir / "source.txt").write_text(read_result)

    def content(turn: int) -> str:
        return f"argument-integral-tour{turn}-" + "z" * 80

    script = []
    for turn in (1, 2, 3):
        script += [
            tools(call("read_file", path="source.txt")),
            tools(call("write_file", path=f"notes{turn}.txt", content=content(turn))),
            say(f"réponse {turn}"),
        ]
    console = Console("tour 1", "/detail", "tour 2", "/detail", "tour 3")

    await run_repl(console, make_config(), {"scripted": ScriptedModel(script)}, workdir)

    titles_1, detail_2, titles_3 = (console.shown_before_read(i) for i in (1, 3, 5))
    # Mode titre : l'événement est visible, mais ni l'argument ni le résultat complets.
    assert "notes1.txt" in titles_1
    assert content(1) not in titles_1
    assert read_result not in titles_1
    # Mode détaillé : arguments et résultat complets.
    assert content(2) in detail_2
    assert read_result in detail_2
    # Retour aux titres.
    assert content(3) not in titles_3
    assert read_result not in titles_3


async def test_model_reply_is_shown_in_full_in_title_mode_even_when_long_and_multiline(
    workdir,
):
    """CA-12 (amendé) : la réponse du modèle s'affiche toujours en entier, y
    compris en mode titre, multi-lignes et de plusieurs centaines de caractères."""
    reply = "\n".join(f"ligne {i} de la réponse : " + "mot " * 12 for i in range(1, 9))
    assert len(reply) > 300
    console = Console("explique")

    await run_repl(
        console, make_config(), {"scripted": ScriptedModel([say(reply)])}, workdir
    )

    assert reply in console.shown_before_read(1)


async def test_cumulative_cost_is_shown_after_each_turn_and_at_exit(workdir):
    """CA-14 : coût cumulé visible à la fin de chaque tour et à la sortie."""
    model = ScriptedModel([say("a", cost=0.01), say("b", cost=0.02)])
    console = Console("premier", "second")

    await run_repl(console, make_config(), {"scripted": model}, workdir)

    assert money("0.01").search(console.shown_before_read(1))
    assert money("0.03").search(console.shown_before_read(2))
    assert money("0.03").search(console.after_last_read)


async def test_unknown_cost_is_shown_as_not_estimated_and_does_not_trigger_the_budget(
    workdir,
):
    """Spec §6 / ADR-0004 : coût inconnu jamais affiché comme 0, et il ne
    consomme pas le budget (même minuscule : pas de « continuer ? »)."""
    model = ScriptedModel(
        [
            *(tools(call("shell", command="true"), cost=None) for _ in range(3)),
            say("terminé", cost=None),
        ]
    )
    console = Console("travaille")

    await run_repl(console, make_config(budget=0.0001), {"scripted": model}, workdir)

    turn_output = console.shown_before_read(1)
    assert len(model.calls) == 4
    assert console.questions_continue() == 0
    assert re.search(r"non estim", turn_output, re.IGNORECASE)
    assert not re.search(
        r"(?<![\d.,])0[.,]0+(?!\d)\s*\$|\$\s*0[.,]0+(?!\d)", turn_output
    )


def _always_acting() -> ScriptedModel:
    """Un modèle qui demande toujours une action : il ne s'arrête qu'aux limites."""
    model = ScriptedModel()
    model.then = lambda: tools(call("shell", command="true"))
    return model


async def test_step_limit_stops_the_agent_names_the_limit_and_asks_to_continue(workdir):
    """CA-15 : limite d'étapes atteinte en milieu de tour → arrêt, message qui
    nomme la limite, puis « continuer ? »."""
    model = _always_acting()
    console = Console("travaille sans fin", "non", probe=lambda: len(model.calls))

    await run_repl(console, make_config(max_steps=2), {"scripted": model}, workdir)

    question = console.shown_before_read(1)
    assert console.probes[1] == 2, (
        "le modèle a été appelé au-delà de la limite d'étapes"
    )
    assert re.search(r"[ée]tape", question, re.IGNORECASE), (
        "le message ne nomme pas la limite"
    )
    assert re.search(r"continuer", question, re.IGNORECASE)
    assert len(model.calls) == 2


async def test_continue_yes_grants_an_identical_slice_no_returns_to_prompt_other_reasks(
    workdir,
):
    """CA-16 et spec §6 : une réponse ni oui ni non repose la question ; « oui »
    reprend pour exactement le même nombre d'étapes ; « non » rend la main et
    la session reste ouverte (la demande suivante est traitée)."""
    model = _always_acting()
    console = Console(
        "travaille",
        "peut-être",
        "oui",
        "non",
        "autre chose",
        probe=lambda: len(model.calls),
    )

    await run_repl(console, make_config(max_steps=2), {"scripted": model}, workdir)

    # Appels au modèle constatés à chaque lecture :
    # invite, question, question reposée, question après « oui », invite après « non »,
    # question après la nouvelle demande.
    assert console.probes[:6] == [0, 2, 2, 4, 4, 6]
    for i in (1, 2, 3):
        assert re.search(r"continuer", console.shown_before_read(i), re.IGNORECASE)
    assert not re.search(r"continuer", console.shown_before_read(4), re.IGNORECASE)
    assert model.saw_text("autre chose", 4)


async def test_ctrl_c_at_the_prompt_does_not_quit(workdir):
    """CA-19 : Ctrl+C à l'invite, sans rien en cours, ne quitte pas la session."""
    model = ScriptedModel([say("salut")])
    console = Console(KeyboardInterrupt(), "bonjour")

    await run_repl(console, make_config(), {"scripted": model}, workdir)

    assert model.saw_text("bonjour", 0)
    assert len(console.reads) >= 3
