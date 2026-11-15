"""Affichage d'une modification réussie (spec 002 §4.9, CA-52 ; ADR-0010 §12).

Le format exact n'est pas un contrat : on vérifie seulement ce que la spec exige
de voir (fichier, nombre de remplacements, lignes modifiées en mode détaillé).
"""

import re

from support import (
    Console,
    ScriptedModel,
    call,
    edit,
    make_config,
    replace,
    run_repl,
    say,
    tools,
)


async def test_successful_edit_shows_a_title_then_the_diff_in_detailed_mode(workdir):
    """CA-52 : par défaut, fichier et nombre de remplacements sans les lignes
    modifiées ; avec `/detail`, les lignes modifiées sous forme de diff."""
    (workdir / "notes.txt").write_text("alpha\nANCIEN-UN\nbeta\nANCIEN-DEUX\n")
    script = []
    for _ in range(2):
        script += [
            tools(call("read_file", path="notes.txt")),
            tools(
                edit(
                    "notes.txt",
                    replace("ANCIEN-UN", "NOUVEAU-UN"),
                    replace("ANCIEN-DEUX", "NOUVEAU-DEUX"),
                )
            ),
            say("fait"),
        ]
    # Le second tour rejoue les mêmes remplacements : on remet le fichier à l'état initial.
    reset = lambda: (
        (workdir / "notes.txt").write_text("alpha\nANCIEN-UN\nbeta\nANCIEN-DEUX\n"),
        "/detail",
    )[1]
    console = Console("modifie", reset, "modifie encore")

    await run_repl(console, make_config(), {"scripted": ScriptedModel(script)}, workdir)

    titles = console.shown_before_read(1)
    detail = console.shown_before_read(3)
    assert "notes.txt" in titles
    assert re.search(r"(?<!\d)2(?!\d)", titles)
    assert "NOUVEAU-UN" not in titles and "ANCIEN-UN" not in titles
    assert re.search(r"(?m)^\s*-\s*ANCIEN-UN", detail)
    assert re.search(r"(?m)^\s*\+\s*NOUVEAU-UN", detail)
    assert re.search(r"(?m)^\s*-\s*ANCIEN-DEUX", detail)
    assert re.search(r"(?m)^\s*\+\s*NOUVEAU-DEUX", detail)
