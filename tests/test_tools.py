"""Les outils de base et le retour de leurs erreurs au modèle.

Spec 001 §4.2, CA-6 à CA-7 et CA-9 à CA-11 (CA-8 remplacé par la 002, voir test_long_outputs.py), §6 ; ADR-0002 (les marqueurs entre crochets du
tableau §3 sont le contrat vérifié ici) ; ADR-0005 §3 (délai des commandes).
Notion : tool-calling.

Chaque test joue un tour réel : le modèle simulé demande l'action, le vrai
outil s'exécute sur un vrai dossier, et on inspecte ce que le modèle reçoit au
tour de boucle suivant. Une erreur d'action ne doit jamais terminer le tour
autrement que par la réponse du modèle (`done`).
"""

import time

from support import call, ended_with, make_config, one_turn, say, tools


async def test_reading_a_missing_file_returns_the_error_to_the_model(workdir):
    """CA-6 : le modèle reçoit l'erreur et la boucle continue jusqu'à sa réponse."""
    missing = call("read_file", path="absent.txt")
    retry = call("write_file", path="absent.txt", content="créé après l'erreur\n")
    model, events = await one_turn(
        workdir, tools(missing), tools(retry), say("Le fichier manquait, je l'ai créé.")
    )

    assert ended_with(events) == "done"
    assert model.tool_output(missing).startswith("error:")
    assert len(model.calls) == 3
    assert (workdir / "absent.txt").exists()


async def test_reading_a_binary_file_is_refused_explicitly(workdir):
    """CA-7 : refus explicite, jamais le contenu brut."""
    (workdir / "image.bin").write_bytes(b"BINAIRE-ENTETE\x00\x01\x02\xff\xfe")
    read = call("read_file", path="image.bin")
    model, events = await one_turn(workdir, tools(read), say("C'est un binaire."))

    output = model.tool_output(read)
    assert ended_with(events) == "done"
    assert "error: binary file, not read" in output
    assert "BINAIRE-ENTETE" not in output


async def test_write_creates_missing_folders_and_overwrites_existing_files(workdir):
    """CA-9 : dossier inexistant créé ; fichier existant écrasé sans question."""
    (workdir / "existant.txt").write_text("ancien contenu\n")
    _, events = await one_turn(
        workdir,
        tools(
            call("write_file", path="a/b/c/nouveau.txt", content="nouveau\n"),
            call("write_file", path="existant.txt", content="remplacé\n"),
        ),
        say("Écrit."),
    )

    assert ended_with(events) == "done"
    assert (workdir / "a" / "b" / "c" / "nouveau.txt").read_text() == "nouveau\n"
    assert (workdir / "existant.txt").read_text() == "remplacé\n"


async def test_failing_command_returns_exit_code_and_output_and_the_turn_continues(
    workdir,
):
    """CA-10 : code de sortie et sortie (stdout et stderr) renvoyés ; la session continue."""
    failing = call(
        "shell", command="echo sortie-standard; echo sortie-erreur >&2; exit 3"
    )
    model, events = await one_turn(
        workdir, tools(failing), say("La commande a échoué.")
    )

    output = model.tool_output(failing)
    assert ended_with(events) == "done"
    assert "sortie-standard" in output
    assert "sortie-erreur" in output
    assert "[exit code: 3]" in output
    assert len(model.calls) == 2


async def test_command_exceeding_the_timeout_is_killed_and_partial_output_is_returned(
    workdir,
):
    """CA-11 : arrêt au délai maximal, `[TIMEOUT`, sortie partielle ; la session continue."""
    slow = call("shell", command="echo debut-partiel; sleep 30; echo jamais-atteint")
    config = make_config(timeout=1.0)

    started = time.monotonic()
    model, events = await one_turn(
        workdir, tools(slow), say("Trop long."), config=config
    )
    elapsed = time.monotonic() - started

    output = model.tool_output(slow)
    assert ended_with(events) == "done"
    assert "[TIMEOUT" in output
    assert "debut-partiel" in output
    assert "jamais-atteint" not in output
    assert elapsed < 10, (
        f"la commande aurait dû être tuée vers 1 s, pas après {elapsed:.1f} s"
    )


async def test_unknown_tool_and_invalid_arguments_are_returned_as_errors(workdir):
    """Spec §6 / ADR-0002 §2 : outil inconnu et arguments invalides sont des
    erreurs renvoyées au modèle ; chaque appel reçoit exactement un résultat."""
    unknown = call("delete_everything", target="/")
    invalid = call("read_file")  # `path` manquant
    model, events = await one_turn(
        workdir, tools(unknown, invalid), say("Je me corrige.")
    )

    assert ended_with(events) == "done"
    assert "error: unknown tool" in model.tool_output(unknown)
    assert "error: invalid arguments" in model.tool_output(invalid)
