"""Mode headless (tranche 4) : contrat du run `-p`, flux JSONL et codes de sortie.

Spec 003 §4.8, CA-S31, CA-S33 à CA-S38 et cas limites §6 (budget déjà consommé à la
reprise, texte multiligne et non ASCII) ; ADR-0012 §6, §7, §8 et « Points confirmés »
(stdout du mode texte toujours vide si le code est non nul).

Seam : `cli.main.main(argv, client_factory=...)` (aide `headless`) avec un modèle
simulé et les vrais outils, flux capturés au niveau des descripteurs (`capfd`).
L'isolation réelle stdout/stderr, l'écriture au fil de l'eau et les signaux sont dans
`test_headless_process.py` (vrai sous-processus).

Hypothèses d'interface : les noms de lignes (`run_started`, `tool_call`,
`tool_result`, `assistant_message`, `result`), les champs `type`, `resumed`,
`schema`, `is_error` et les statuts `ok|error|limit|interrupted` viennent de
l'ADR ; les autres champs (session, modèle, dossier, réponse, étapes, tokens, coût,
raison) ne sont pas nommés : on vérifie que l'information figure dans la ligne
(`values`), pas le nom du champ.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from support import (
    ScriptedModel,
    call,
    has_amount,
    headless,
    journals,
    jsonl_lines,
    launch,
    saved_path_in,
    say,
    tool_outputs,
    tools,
    values,
)

from harness.models.base import ProviderError

JSONL = ["--output-format", "jsonl"]
LONG_COMMAND = 'for i in $(seq 1 3000); do echo "sortie $i"; done'


def _files(root: Path) -> dict[str, bytes]:
    """Contenu de tout ce qui est sous `.harness/` (journaux, verrous, sorties)."""
    base = root / ".harness"
    if not base.exists():
        return {}
    return {
        str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()
    }


def _only_session(workdir) -> str:
    found = journals(workdir)
    assert len(found) == 1, f"un journal de session attendu : {found}"
    return found[0].stem


def _repl_session(workdir, monkeypatch, capfd, request="demande d'avant") -> str:
    """Une session ordinaire ouverte puis fermée au REPL ; rend son identifiant."""
    known = set(journals(workdir))
    launch(
        [], [request, "/quit"], {"scripted": ScriptedModel([say("ok")])},
        workdir, monkeypatch, capfd,
    )  # fmt: skip
    (path,) = set(journals(workdir)) - known
    return path.stem


def _of_type(stream: list[dict], kind: str) -> list[dict]:
    return [line for line in stream if line["type"] == kind]


# --------------------------------------------------------------------------
# Flux JSONL
# --------------------------------------------------------------------------


def test_jsonl_stream_is_one_valid_object_per_line_from_run_started_to_result(
    workdir, monkeypatch, capfd
):
    """CA-S31 (et cas limite §6 texte multiligne, guillemets, non ASCII) : stdout
    ne contient que des objets JSON avec `type` ; la première ligne porte session,
    modèle, dossier et `resumed` ; les actions apparaissent ; la dernière porte
    statut, réponse finale (identique, retours à la ligne compris), étapes, tokens,
    coût cumulé et session."""
    (workdir / "notes.txt").write_text('ligne « une »\n"deux" — été\n')
    request = 'lis notes.txt\npuis réponds « vite » avec "guillemets"'
    answer = 'Résumé :\n« une » et "deux" — été ✓'
    read = call("read_file", path="notes.txt")
    model = ScriptedModel([tools(read, cost=0.01), say(answer, cost=0.02)])

    run = headless(
        ["-p", request, *JSONL], {"scripted": model}, workdir, monkeypatch, capfd
    )

    assert run.code == 0
    stream = jsonl_lines(run.out)  # aucune ligne de diagnostic humain sur stdout
    session_id = _only_session(workdir)
    first, last = stream[0], stream[-1]
    assert first["type"] == "run_started"
    assert session_id in values(first)
    assert any("scripted" in str(v) for v in values(first)), "modèle absent"
    assert str(workdir.resolve()) in values(first), "dossier de travail absent"
    assert first["resumed"] is False
    assert first["schema"] == 1
    assert model.saw_text("puis réponds « vite »", 0), "demande altérée"

    (started,) = _of_type(stream, "tool_call")
    (finished,) = _of_type(stream, "tool_result")
    assert stream.index(started) < stream.index(finished)
    assert "read_file" in values(started) and read["id"] in values(started)
    assert read["id"] in values(finished) and finished["is_error"] is False
    assert any("été" in str(v) for v in values(finished)), "résultat absent"
    assert _of_type(stream, "assistant_message"), "réponse du modèle non émise"

    assert last["type"] == "result"
    assert "ok" in values(last)
    assert answer in values(last), "réponse finale absente ou altérée"
    assert session_id in values(last)
    assert 2 in values(last), "nombre d'étapes absent"
    assert 240 in values(last) or {200, 40} <= set(values(last)), "tokens absents"
    assert has_amount(last, 0.03), "coût cumulé de la session absent"


def test_headless_run_creates_a_session_that_a_second_run_resumes_with_history_and_cost(
    workdir, monkeypatch, capfd
):
    """CA-S33 : un run headless crée une session ; un second run `--resume <id> -p`
    voit l'historique du premier et son coût cumulé inclut celui du premier."""
    first = headless(
        ["-p", "retiens le mot ananas", *JSONL],
        {"scripted": ScriptedModel([say("noté", cost=0.01)])},
        workdir, monkeypatch, capfd,
    )  # fmt: skip
    session_id = _only_session(workdir)
    assert first.code == 0 and session_id in values(jsonl_lines(first.out)[0])

    model = ScriptedModel([say("ananas", cost=0.02)])
    second = headless(
        ["--resume", session_id, "-p", "quel mot ?", *JSONL],
        {"scripted": model}, workdir, monkeypatch, capfd,
    )  # fmt: skip

    assert second.code == 0
    stream = jsonl_lines(second.out)
    assert stream[0]["resumed"] is True and session_id in values(stream[0])
    assert model.saw_text("retiens le mot ananas", 0), (
        "historique du premier run absent"
    )
    assert model.saw_text("noté", 0)
    assert has_amount(stream[-1], 0.03), "coût cumulé sans celui du premier run"
    assert journals(workdir) == [workdir / ".harness/sessions" / f"{session_id}.jsonl"]


def test_no_session_option_records_nothing_and_leaves_no_saved_output(
    workdir, monkeypatch, capfd
):
    """CA-S34 (et ADR-0012 §5) : avec `--no-session`, aucune session n'est créée,
    la liste des sessions est inchangée, et la sortie longue enregistrée pendant le
    run ne reste pas sous `.harness/outputs/`."""
    _repl_session(workdir, monkeypatch, capfd)
    listing_before = launch(["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capfd)  # fmt: skip
    journals_before = {p: p.read_bytes() for p in journals(workdir)}
    command = call("shell", command=LONG_COMMAND)
    model = ScriptedModel([tools(command), say("fini")])

    run = headless(
        ["-p", "lance la commande", "--no-session"], {"scripted": model},
        workdir, monkeypatch, capfd, extra_toml="[tools]\nmax_output_chars = 1000\n",
    )  # fmt: skip

    assert run.code == 0 and run.out.strip() == "fini"
    # Précondition : une sortie longue a bien été enregistrée pendant le run.
    saved_path_in(model.tool_output(command))
    listing_after = launch(["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capfd)  # fmt: skip
    assert {p: p.read_bytes() for p in journals(workdir)} == journals_before
    assert listing_after.out == listing_before.out
    outputs = workdir / ".harness" / "outputs"
    leftovers = (
        [p for p in outputs.rglob("*") if p.is_file()] if outputs.exists() else []
    )
    assert leftovers == [], (
        f"sortie enregistrée laissée par un run non enregistré : {leftovers}"
    )


# --------------------------------------------------------------------------
# Codes de sortie
# --------------------------------------------------------------------------


def test_action_error_followed_by_an_answer_exits_0_and_the_error_is_in_the_stream(
    workdir, monkeypatch, capfd
):
    """CA-S35 : une erreur d'action (fichier absent) suivie d'une réponse : code 0 ;
    l'erreur figure dans le flux JSONL, reliée à son appel."""
    read = call("read_file", path="absent.txt")
    model = ScriptedModel([tools(read), say("le fichier n'existe pas")])

    run = headless(
        ["-p", "lis absent.txt", *JSONL],
        {"scripted": model},
        workdir,
        monkeypatch,
        capfd,
    )

    assert run.code == 0
    stream = jsonl_lines(run.out)
    (result,) = [r for r in _of_type(stream, "tool_result") if read["id"] in values(r)]
    assert result["is_error"] is True
    assert "ok" in values(stream[-1])


def test_provider_lost_mid_run_exits_1_with_the_cause_and_the_session_is_resumable(
    workdir, monkeypatch, capfd
):
    """CA-S36 : fournisseur injoignable en cours de run : code 1 ; la ligne finale
    donne le statut `error` et la cause ; la session est enregistrée jusque-là et
    reprenable."""
    write = call("write_file", path="a.txt", content="contenu")
    lost = ProviderError("unreachable", "Serveur injoignable (cause-test-xyz).")
    model = ScriptedModel([tools(write), lost])

    run = headless(
        ["-p", "crée a.txt", *JSONL], {"scripted": model}, workdir, monkeypatch, capfd
    )

    assert run.code == 1
    last = jsonl_lines(run.out)[-1]
    assert last["type"] == "result" and "error" in values(last)
    assert re.search(
        r"cause-test-xyz|unreachable|injoignable", json.dumps(last, ensure_ascii=False)
    )
    session_id = _only_session(workdir)

    again = ScriptedModel([say("repris")])
    resumed = headless(
        ["--resume", session_id, "-p", "reprends"], {"scripted": again},
        workdir, monkeypatch, capfd,
    )  # fmt: skip
    assert resumed.code == 0 and resumed.out.strip() == "repris"
    seen = again.calls[0]
    assert again.saw_text("crée a.txt", 0)
    assert len(tool_outputs(seen, write["id"])) == 1, "résultat d'action non enregistré"


@pytest.mark.parametrize(("limit", "output"), [("étapes", "jsonl"), ("budget", "text")])
def test_limit_reached_exits_3_without_asking_and_the_session_is_resumable(
    workdir, monkeypatch, capfd, limit, output
):
    """CA-S37 : limite d'étapes ou budget atteint : aucune question, code 3, la
    limite et l'avancement sont indiqués (ligne finale en JSONL, stderr en texte,
    stdout texte vide), la session est reprenable. Cas limite §6 : reprise d'une
    session dont le budget est déjà dépassé : code 3 sans appel au modèle."""
    model = ScriptedModel(
        then=lambda: tools(call("shell", command="echo encore"), cost=0.03)
    )
    options = {"max_steps": 2} if limit == "étapes" else {"budget": 0.05}

    run = headless(
        ["-p", "boucle sans fin", "--output-format", output], {"scripted": model},
        workdir, monkeypatch, capfd, **options,
    )  # fmt: skip

    assert run.code == 3
    assert run.asked == [], f"question posée en headless : {run.asked}"
    assert len(model.calls) == 2, "le run ne s'est pas arrêté à la limite"
    cause = r"étape|step" if limit == "étapes" else r"budget"
    if output == "jsonl":
        last = jsonl_lines(run.out)[-1]
        assert last["type"] == "result" and "limit" in values(last)
        assert re.search(cause, json.dumps(last, ensure_ascii=False), re.IGNORECASE)
        assert 2 in values(last), "état d'avancement (étapes) absent"
    else:
        assert run.out == "", "stdout du mode texte non vide pour un code non nul"
        assert re.search(cause, run.err, re.IGNORECASE), (
            "limite non indiquée sur stderr"
        )
    session_id = _only_session(workdir)

    again = ScriptedModel([say("repris")])
    resumed = headless(
        ["--resume", session_id, "-p", "continue"], {"scripted": again},
        workdir, monkeypatch, capfd, **options,
    )  # fmt: skip
    if limit == "étapes":
        assert resumed.code == 0 and again.saw_text("boucle sans fin", 0)
    else:
        assert resumed.code == 3, "budget déjà dépassé : la reprise devait s'arrêter"
        assert again.calls == [], "appel au modèle malgré un budget déjà dépassé"
        assert resumed.asked == []


@pytest.mark.parametrize(
    "case",
    [
        "option-invalide",
        "prompt-absent",
        "config-invalide",
        "cle-manquante",
        "serveur-injoignable",
        "session-inconnue",
        "session-corrompue",
        "autre-dossier",
    ],
)
def test_unusable_start_exits_2_with_nothing_run_nor_recorded(
    workdir, tmp_path, monkeypatch, capfd, case
):
    """CA-S38 : option invalide, prompt absent, configuration invalide, clé manquante,
    serveur injoignable au lancement, session introuvable, corrompue ou d'un autre
    dossier : code 2, message sur stderr, rien sur stdout (pas même de ligne JSONL),
    aucun appel au modèle ni action, aucun journal créé ou modifié.
    (Session occupée : déjà couverte par T-0101.)"""
    folder = workdir
    argv = ["-p", "écris marqueur.txt", *JSONL]
    options: dict = {}
    model = ScriptedModel(
        [tools(call("write_file", path="marqueur.txt", content="x")), say("fait")]
    )
    needle: str | None = None
    if case == "option-invalide":
        argv = ["-p", "écris marqueur.txt", "--output-format", "xml"]
    elif case == "prompt-absent":
        argv = ["--no-session", *JSONL]
    elif case == "config-invalide":
        argv = ["-p", "écris marqueur.txt"]  # sortie texte : stdout doit rester vide
        options["extra_toml"] = "ceci n'est pas du toml ["
    elif case == "cle-manquante":
        model.check_error = ProviderError(
            "auth", "Clé CLE_ABSENTE_XYZ manquante (test)."
        )
        needle = "CLE_ABSENTE_XYZ"
    elif case == "serveur-injoignable":
        model.check_error = ProviderError(
            "unreachable", "Serveur absent-xyz injoignable."
        )
        needle = "absent-xyz"
    elif case == "session-inconnue":
        argv = ["--resume", "deadbeef", *argv]
        needle = "deadbeef"
    elif case == "session-corrompue":
        session_id = _repl_session(workdir, monkeypatch, capfd)
        (path,) = journals(workdir)
        lines = path.read_text().split("\n")
        lines[2] = '{"id": 2, "parentId": 1, "type": "mess'
        path.write_text("\n".join(lines))
        argv = ["--resume", session_id, *argv]
        needle = session_id
    else:  # dossier déplacé : la session appartient à l'ancien chemin
        session_id = _repl_session(workdir, monkeypatch, capfd)
        folder = tmp_path / "deplace"
        shutil.move(workdir, folder)
        argv = ["--resume", session_id, *argv]
        needle = str(workdir)
    before = _files(folder)

    run = headless(argv, {"scripted": model}, folder, monkeypatch, capfd, **options)

    assert run.code == 2
    assert run.out == "", f"stdout non vide malgré l'échec au démarrage : {run.out!r}"
    assert run.err.strip(), "aucun message d'erreur sur stderr"
    if needle is not None:
        assert needle in run.err, f"la cause ({needle}) n'est pas nommée"
    assert model.calls == [], "le modèle a été appelé"
    assert not (folder / "marqueur.txt").exists(), "une action a été exécutée"
    assert _files(folder) == before, "un journal a été créé ou modifié"
