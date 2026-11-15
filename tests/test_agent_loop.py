"""Boucle d'agent vue depuis `Session` : enchaînement, historique, budget.

Spec 001 §4.1, §4.2, §4.4, §7 ; ADR-0001, ADR-0004. Notion : boucle-agent.
Les tests pilotent la vraie session avec les vrais outils et un modèle simulé,
et vérifient ce que voit le modèle et ce qui change sur le disque de l'hôte.
"""

from support import (
    ScriptedModel,
    call,
    collect,
    ended_with,
    make_config,
    make_session,
    one_turn,
    say,
    tools,
)

from harness.events import AssistantMessage, LimitReached, ToolCallStarted


async def test_agent_chains_read_write_shell_in_one_turn_with_paths_relative_to_workdir(
    workdir, tmp_path, monkeypatch
):
    """CA-5 (enchaînement de trois actions avant la réponse) et CA-4 (partie
    testable, ADR-0002 §Conséquences : les chemins relatifs partent du dossier
    de travail, pas du dossier courant du processus)."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    (workdir / "source.txt").write_text("valeur=42\n")

    read = call("read_file", path="source.txt")
    write = call("write_file", path="copie/out.txt", content="valeur=42 copiée\n")
    shell = call("shell", command="cat copie/out.txt")
    model, events = await one_turn(
        workdir,
        tools(read),
        tools(write),
        tools(shell),
        say("Fichier copié et vérifié."),
        text="copie source.txt dans copie/out.txt puis affiche-le",
    )

    assert ended_with(events) == "done"
    assert [e.name for e in events if isinstance(e, ToolCallStarted)] == [
        "read_file",
        "write_file",
        "shell",
    ]
    assert any(isinstance(e, AssistantMessage) for e in events)
    assert len(model.calls) == 4
    assert "valeur=42" in model.tool_output(read)
    assert "valeur=42 copiée" in model.tool_output(shell)
    # Le fichier écrit existe réellement dans le dossier de travail de l'hôte...
    assert (workdir / "copie" / "out.txt").read_text() == "valeur=42 copiée\n"
    # ... et rien n'a été écrit dans le dossier courant du processus.
    assert list(elsewhere.iterdir()) == []


async def test_history_is_kept_across_turns_of_a_session(workdir):
    """CA-2 : une seconde demande qui fait référence à la première est comprise,
    car le modèle reçoit tout l'historique de la session."""
    first_write = call("write_file", path="notes.txt", content="version 1\n")
    model = ScriptedModel(
        [
            tools(first_write),
            say("J'ai créé notes.txt."),
            tools(call("write_file", path="notes.txt", content="version 2\n")),
            say("J'ai modifié notes.txt."),
        ]
    )
    session = make_session(make_config(), workdir, model)

    assert (
        ended_with(await collect(session.run_turn("crée un fichier notes.txt")))
        == "done"
    )
    assert ended_with(await collect(session.run_turn("modifie ce fichier"))) == "done"

    first_call_of_second_turn = 2
    assert model.saw_text("crée un fichier notes.txt", first_call_of_second_turn)
    assert model.saw_text("J'ai créé notes.txt.", first_call_of_second_turn)
    assert model.saw_text(first_write["id"], first_call_of_second_turn)
    assert model.saw_text("modifie ce fichier", first_call_of_second_turn)
    assert (workdir / "notes.txt").read_text() == "version 2\n"


async def test_budget_reached_blocks_model_calls_until_granted_an_identical_slice(
    workdir,
):
    """CA-17 : coût cumulé ≥ budget → aucun nouvel appel au modèle avant la
    réponse à « continuer ? » ; « oui » accorde un budget égal à celui de départ.

    Budget 0,10 $, 0,06 $ par appel : arrêt après 2 appels (0,12 $) ;
    après « oui », plafond 0,20 $ : 2 appels de plus (0,24 $) puis nouvel arrêt.
    """
    model = ScriptedModel(then=lambda: tools(call("shell", command="true"), cost=0.06))
    session = make_session(make_config(budget=0.10), workdir, model)

    events = await collect(session.run_turn("travaille longtemps"))
    assert ended_with(events) == "budget_limit"
    assert [e.kind for e in events if isinstance(e, LimitReached)] == ["budget"]
    assert len(model.calls) == 2

    events = await collect(session.resume_turn(grant=True))
    assert ended_with(events) == "budget_limit"
    assert len(model.calls) == 4
