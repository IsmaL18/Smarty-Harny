"""Normalisation des arguments et ensembles d'outils.

Spec 002 §4.6 et §4.8, CA-46 à CA-51 ; ADR-0009. Les erreurs sont renvoyées au
modèle (la session continue) ; l'ensemble « lecture seule » est une restriction
de ce que le modèle voit, pas une sécurité (spec §6).
"""

import pytest
from support import (
    Console,
    ScriptedModel,
    call,
    config_from_toml,
    edit,
    ended_with,
    one_turn,
    refused,
    replace,
    run_repl,
    say,
    tools,
)

from harness.config import ConfigError, load_config

_ALL_TOOLS = {"read_file", "write_file", "edit_file", "shell"}


def _names(specs: list[dict]) -> set[str]:
    return {spec["function"]["name"] for spec in specs}


@pytest.mark.parametrize(
    "form", ["nombres-en-texte", "remplacement-seul", "liste-en-texte"]
)
async def test_wrong_but_unambiguous_argument_shapes_work_as_the_right_shape(
    workdir, form
):
    """CA-46 : nombre en texte, remplacement sans liste, liste en texte JSON
    valide : l'action réussit comme avec la forme correcte."""
    (workdir / "a.txt").write_text("un\ndeux\ntrois\n")
    read = call("read_file", path="a.txt")
    if form == "nombres-en-texte":
        action = call("read_file", path="a.txt", offset="2", limit="1")
    elif form == "remplacement-seul":
        action = call(
            "edit_file", path="a.txt", edits={"old_text": "un", "new_text": "UN"}
        )
    else:
        action = call(
            "edit_file",
            path="a.txt",
            edits='[{"old_text": "un", "new_text": "UN"}]',
        )

    model, events = await one_turn(workdir, tools(read), tools(action), say("fait"))

    output = model.tool_output(action)
    assert ended_with(events) == "done"
    assert not output.startswith("error:")
    if form == "nombres-en-texte":
        assert "deux" in output and "trois" not in output
    else:
        assert (workdir / "a.txt").read_text() == "UN\ndeux\ntrois\n"


@pytest.mark.parametrize(
    ("action", "argument"),
    [
        (call("edit_file", edits=[{"old_text": "a", "new_text": "b"}]), "path"),
        (call("read_file", path="a.txt", bogus=1), "bogus"),
        (call("edit_file", path="a.txt", edits='[{"old_text": '), "edits"),
    ],
    ids=["manquant", "inconnu", "json-invalide"],
)
async def test_unusable_arguments_fail_naming_the_argument_and_the_session_continues(
    workdir, action, argument
):
    """CA-47 : l'erreur nomme l'argument fautif ; le tour va jusqu'à la réponse du modèle."""
    (workdir / "a.txt").write_text("contenu\n")

    model, events = await one_turn(workdir, tools(action), say("je corrige"))

    output = model.tool_output(action)
    assert ended_with(events) == "done"
    assert refused(output)
    assert argument in output
    assert (workdir / "a.txt").read_text() == "contenu\n"


async def test_a_number_that_is_not_convertible_says_the_expected_form(workdir):
    """CA-47 / ADR-0009 §7 : le message donne aussi la forme attendue."""
    (workdir / "a.txt").write_text("contenu\n")
    bad = call("read_file", path="a.txt", limit="beaucoup")

    model, _ = await one_turn(workdir, tools(bad), say("vu"))

    output = model.tool_output(bad)
    assert output.startswith("error:")
    assert "limit" in output
    assert "integer" in output


async def test_default_toolset_gives_the_model_the_four_tools(workdir):
    """CA-48."""
    model, _ = await one_turn(workdir, say("rien à faire"))

    assert _names(model.tools_seen[0]) == _ALL_TOOLS


async def test_read_only_toolset_hides_the_other_tools_and_refuses_calls_to_them(
    workdir,
):
    """CA-49 : le modèle ne voit que la lecture ; un appel à un autre outil
    renvoie une erreur qui nomme l'outil et liste les outils disponibles, sans
    effet (aucun fichier écrit, aucune commande lancée) ; la session continue."""
    (workdir / "a.txt").write_text("contenu\n")
    write = call("write_file", path="nouveau.txt", content="x\n")
    shell = call("shell", command="touch commande-lancee")
    change = edit("a.txt", replace("contenu", "autre"))
    read = call("read_file", path="a.txt")

    model, events = await one_turn(
        workdir,
        tools(write, shell, change),
        tools(read),
        say("lecture seule"),
        config=config_from_toml(toolset="read_only"),
    )

    assert ended_with(events) == "done"
    assert _names(model.tools_seen[0]) == {"read_file"}
    for attempt, name in (
        (write, "write_file"),
        (shell, "shell"),
        (change, "edit_file"),
    ):
        output = model.tool_output(attempt)
        assert output.startswith("error:")
        assert name in output
        assert "read_file" in output
    assert "contenu" in model.tool_output(read)
    assert not (workdir / "nouveau.txt").exists()
    assert not (workdir / "commande-lancee").exists()
    assert (workdir / "a.txt").read_text() == "contenu\n"


def test_unknown_toolset_is_refused_naming_it_and_listing_the_existing_ones():
    """CA-50 : message en français qui nomme l'ensemble et liste les ensembles
    existants ; la configuration n'est pas construite, donc aucune session ne s'ouvre."""
    with pytest.raises(ConfigError) as error:
        config_from_toml(toolset="tout-puissant")

    message = str(error.value)
    assert "tout-puissant" in message
    assert "full" in message
    assert "read_only" in message


def test_known_toolsets_are_accepted():
    """CA-50 (complément) : les deux ensembles nommés par la configuration se chargent."""
    for name in ("full", "read_only"):
        assert load_config(
            'default_model = "m"\n[models.m]\nmodel = "openai/x"\n'
            f'[tools]\ntoolset = "{name}"\n'
        )


@pytest.mark.parametrize("toolset", ["full", "read_only"])
async def test_launch_shows_the_active_toolset(workdir, toolset):
    """CA-51 : au lancement, l'ensemble actif est affiché avec le dossier, le modèle et les limites."""
    console = Console()

    await run_repl(
        console,
        config_from_toml(toolset=toolset),
        {"scripted": ScriptedModel()},
        workdir,
    )

    startup = console.shown_before_read(0)
    assert toolset in startup
    assert str(workdir.resolve()) in startup or str(workdir) in startup
