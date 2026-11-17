"""Lecture par plage, coupe au milieu et sorties de commande enregistrées.

Spec 002 §4.4 et §4.5, CA-40 à CA-45 (CA-8 de la 001 remplacé) ; ADR-0011.
Les budgets viennent de la configuration (`max_read_chars`, `max_output_chars`).
Le format exact de l'en-tête n'est pas un contrat, seuls le marqueur
`[TRUNCATED`, la mention de `read_file`/`offset` et le chemin du fichier de
sortie sous `.harness/` le sont (ADR-0011 §2, §9).
"""

import os
import re
import time

from support import (
    Console,
    ScriptedModel,
    call,
    config_from_toml,
    ended_with,
    make_config,
    one_turn,
    run_repl,
    saved_path_in,
    say,
    tools,
)


def _numbered(count: int, prefix: str = "ligne") -> str:
    return "".join(f"{prefix} {i:04d}\n" for i in range(1, count + 1))


def _saved_files(workdir):
    root = workdir / ".harness"
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.name != ".gitignore"]


# --- Lecture ---------------------------------------------------------------


async def test_range_read_returns_exactly_those_lines_and_the_total(workdir):
    """CA-40 : ligne de départ (à partir de 1) et nombre de lignes ; le nombre
    total de lignes du fichier est indiqué."""
    (workdir / "a.txt").write_text(_numbered(30))
    read = call("read_file", path="a.txt", offset=5, limit=3)

    model, _ = await one_turn(workdir, tools(read), say("lu"))

    output = model.tool_output(read)
    for wanted in ("ligne 0005", "ligne 0006", "ligne 0007"):
        assert wanted in output
    for unwanted in ("ligne 0004", "ligne 0008"):
        assert unwanted not in output
    assert re.search(r"(?<!\d)30(?!\d)", output)


async def test_range_outside_the_file_is_an_error_giving_the_total_line_count(workdir):
    """CA-40 : plage hors du fichier → erreur claire avec le nombre total de lignes."""
    (workdir / "a.txt").write_text(_numbered(30))
    read = call("read_file", path="a.txt", offset=500, limit=10)

    model, events = await one_turn(workdir, tools(read), say("vu"))

    output = model.tool_output(read)
    assert ended_with(events) == "done"
    assert output.startswith("error:")
    assert re.search(r"(?<!\d)30(?!\d)", output)


async def test_long_file_is_cut_in_the_middle_and_the_omitted_zone_is_readable_by_range(
    workdir,
):
    """CA-41 : début et fin présents, milieu absent, en-tête qui dit ce qui est
    omis et invite à lire par plage ; la plage de la zone omise renvoie son contenu."""
    (workdir / "long.txt").write_text(_numbered(2000))
    read = call("read_file", path="long.txt")
    middle = call("read_file", path="long.txt", offset=1000, limit=2)

    model, _ = await one_turn(
        workdir,
        tools(read),
        tools(middle),
        say("vu"),
        config=make_config(max_read=2000),
    )

    output = model.tool_output(read)
    assert "ligne 0001" in output
    assert "ligne 2000" in output
    assert "ligne 1000" not in output
    assert "[TRUNCATED" in output
    assert "read_file" in output and "offset" in output
    assert len(output) < 2 * 2000, "la sortie doit rester de l'ordre du budget"
    assert "ligne 1000" in model.tool_output(middle)
    assert "ligne 1001" in model.tool_output(middle)


async def test_a_single_giant_line_is_cut_by_characters_with_a_header(workdir):
    """ADR-0011 §3 : fichier minifié, une seule ligne plus grande que le budget."""
    (workdir / "min.js").write_text("x" * 10000)
    read = call("read_file", path="min.js")

    model, _ = await one_turn(
        workdir, tools(read), say("vu"), config=make_config(max_read=500)
    )

    output = model.tool_output(read)
    assert "[TRUNCATED" in output
    assert len(output) < 2000


# --- Sortie de commande ------------------------------------------------------

_LONG_FAILING_COMMAND = (
    'for i in $(seq 1 3000); do echo "sortie $i"; done; echo ERREUR-FINALE >&2; exit 3'
)


async def test_long_failing_command_keeps_its_start_its_end_and_the_exit_code(workdir):
    """CA-42 : début, fin (donc le message final), en-tête et code de sortie ; le milieu est omis."""
    shell = call("shell", command=_LONG_FAILING_COMMAND)

    model, events = await one_turn(
        workdir, tools(shell), say("vu"), config=make_config(max_output=1000)
    )

    output = model.tool_output(shell)
    assert ended_with(events) == "done"
    assert "sortie 1\n" in output
    assert "ERREUR-FINALE" in output
    assert "[exit code: 3]" in output
    assert "[TRUNCATED" in output
    assert "sortie 1500\n" not in output
    assert len(output) < 3000


async def test_the_header_gives_a_file_in_the_workdir_holding_the_full_output(workdir):
    """CA-43 : le chemin de l'en-tête est dans le dossier de travail ; l'agent
    lit ce fichier, y compris par plage, et y retrouve la partie omise.
    ADR-0011 §10 : le dossier est exclu de Git par son propre `.gitignore`."""
    shell = call("shell", command=_LONG_FAILING_COMMAND)

    def read_saved_by_range(messages: list[dict]):
        shown = next(
            m["content"] for m in messages if m.get("tool_call_id") == shell["id"]
        )
        return tools(call("read_file", path=saved_path_in(shown), offset=1500, limit=2))

    model, _ = await one_turn(
        workdir,
        tools(shell),
        read_saved_by_range,
        say("vu"),
        config=make_config(max_output=1000),
    )

    saved = saved_path_in(model.tool_output(shell))
    resolved = (workdir / saved).resolve()
    assert workdir.resolve() in resolved.parents
    assert "sortie 3000" in resolved.read_text()
    last_read = [m for m in model.last_seen if m.get("role") == "tool"][-1]
    assert "sortie 1500" in str(last_read["content"])
    assert (workdir / ".harness" / ".gitignore").read_text().strip() == "*"


async def test_short_command_leaves_nothing_on_disk(workdir):
    """ADR-0011 §6 : l'écriture ne commence que si le budget est dépassé."""
    shell = call("shell", command="echo court")

    await one_turn(workdir, tools(shell), say("vu"))

    assert _saved_files(workdir) == []


async def test_command_timeout_with_long_output_keeps_timeout_info_and_cuts_the_middle(
    workdir,
):
    """CA-45 : délai dépassé avec une sortie plus longue que le budget :
    comportements de CA-11 (mention du dépassement, sortie partielle) et coupe au milieu."""
    shell = call(
        "shell",
        command='for i in $(seq 1 3000); do echo "sortie $i"; done; sleep 30; echo jamais',
    )
    started = time.monotonic()

    model, events = await one_turn(
        workdir,
        tools(shell),
        say("vu"),
        config=make_config(max_output=1000, timeout=2.0),
    )

    output = model.tool_output(shell)
    assert time.monotonic() - started < 15
    assert ended_with(events) == "done"
    assert "[TIMEOUT" in output
    assert "sortie 1\n" in output
    assert "sortie 3000" in output
    assert "[TRUNCATED" in output
    assert "jamais" not in output


async def test_saved_output_stops_at_the_disk_cap_while_the_tail_stays_the_real_end(
    workdir,
):
    """ADR-0011 §7 : plafond `max_saved_output_mb` ; au-delà le fichier est
    arrêté, mais la fin renvoyée au modèle reste la vraie fin de la commande."""
    shell = call(
        "shell",
        command='yes "ligne de remplissage assez longue" | head -n 120000; echo FIN-REELLE',
    )

    model, _ = await one_turn(
        workdir,
        tools(shell),
        say("vu"),
        config=config_from_toml(max_saved_output_mb=1, max_output=1000, timeout=20.0),
    )

    assert "FIN-REELLE" in model.tool_output(shell)
    files = _saved_files(workdir)
    assert len(files) == 1
    assert files[0].stat().st_size <= 1.2 * 1024 * 1024


# --- Cycle de vie des sorties enregistrées -------------------------------------


async def test_stale_session_folders_are_purged_at_launch_but_recent_ones_are_kept(
    workdir,
):
    """ADR-0011 §12 : les restes d'un arrêt brutal (plus de 24 h) sont supprimés
    au lancement ; la session concurrente récente n'est pas touchée."""
    outputs = workdir / ".harness" / "outputs"
    old, recent = outputs / "ancienne", outputs / "concurrente"
    for folder in (old, recent):
        folder.mkdir(parents=True)
        (folder / "cmd-1.txt").write_text("reste\n")
    two_days_ago = time.time() - 48 * 3600
    os.utime(old / "cmd-1.txt", (two_days_ago, two_days_ago))
    os.utime(old, (two_days_ago, two_days_ago))

    await run_repl(
        Console("/quit"), make_config(), {"scripted": ScriptedModel()}, workdir
    )

    assert not old.exists()
    assert (recent / "cmd-1.txt").read_text() == "reste\n"
