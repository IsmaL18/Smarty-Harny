"""Sessions durables, tranche 2 : liste, reprise robuste, anomalies du journal,
arrêt brutal et session occupée.

Spec 003 §4.2 à §4.6 et §6 ; CA-S2, S3, S6, S10 à S18, S25, S26 ; ADR-0012 §1 à §4, §6.
Seams : `cli.main.main` (options `--sessions`, `--resume`, `--model`, commande REPL
`/resume`) lancé avec un modèle simulé et les vrais outils ; fichiers du journal
(JSONL) lus ou fabriqués à partir d'un vrai journal ; vrai sous-processus tué par
SIGKILL (`child_session.py`). On ne vérifie que le contenu utile des messages
(identifiant, ligne, dossier cités), jamais leur texte exact.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from support import (
    ScriptedModel,
    Step,
    call,
    edit,
    journals,
    launch,
    money,
    read_journal,
    refused,
    replace,
    say,
    tool_outputs,
    tools,
)

from harness.models.base import ProviderError

CHILD = Path(__file__).parent / "child_session.py"


# --------------------------------------------------------------------------
# Aides locales
# --------------------------------------------------------------------------


def _open_session(workdir, monkeypatch, capsys, requests, script, **options):
    """Ouvre une vraie session (une ou plusieurs demandes puis /quit) ; rend (id, journal)."""
    known = set(journals(workdir))
    launch(
        options.pop("argv", []),
        [*requests, "/quit"],
        {"scripted": ScriptedModel(script)},
        workdir,
        monkeypatch,
        capsys,
        **options,
    )
    (path,) = set(journals(workdir)) - known
    return path.stem, path


def _snapshot(workdir) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in journals(workdir)}


def _assert_refused(workdir, monkeypatch, capsys, argv) -> str:
    """Lance une reprise qui doit être refusée : aucune demande traitée, aucun
    journal modifié ni créé. Rend le texte affiché (stdout + stderr)."""
    before = _snapshot(workdir)
    model = ScriptedModel([say("ne doit pas répondre")])
    result = launch(
        argv, ["ne doit pas être lue", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    assert model.calls == [], "une session s'est ouverte malgré le refus"
    assert _snapshot(workdir) == before, "le refus a modifié ou créé un journal"
    text = result.out + result.err
    assert text.strip(), "refus silencieux"
    return text


def _line_ref(number: int) -> re.Pattern[str]:
    return re.compile(rf"ligne\s*(?:n°\s*)?{number}(?!\d)", re.IGNORECASE)


def _date_forms(created: str) -> list[str]:
    day = date.fromisoformat(created[:10])
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return [
        day.isoformat(),
        day.strftime("%d/%m/%Y"),
        f"{day.day} {months[day.month - 1]} {day.year}",
    ]


def _wait_for(predicate, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition jamais atteinte avant le délai")


def _journal_text(workdir) -> str:
    return "".join(p.read_text() for p in journals(workdir))


def _spawn(workdir, mode: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(CHILD), str(workdir), mode],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _kill(proc: subprocess.Popen) -> None:
    """SIGKILL sur tout le groupe (processus + commande lancée), puis récolte
    le zombie : un pid de zombie existe encore pour `kill(pid, 0)`."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def _killed_in_mid_turn(workdir) -> str:
    """Un vrai harness est tué en plein tour (commande `sleep` en cours) ; rend l'id."""
    proc = _spawn(workdir, "sleep")
    try:
        _wait_for(lambda: "sleep 120" in _journal_text(workdir))
        time.sleep(0.5)  # laisse la commande démarrer vraiment
    finally:
        _kill(proc)
    (path,) = journals(workdir)
    return path.stem


# --------------------------------------------------------------------------
# Liste et sessions vides
# --------------------------------------------------------------------------


def test_repl_opened_and_closed_without_a_request_leaves_no_session(
    workdir, monkeypatch, capsys
):
    """CA-S3 : ouvrir le REPL puis quitter (/quit ou Ctrl+D) sans demande ne
    laisse aucune session."""
    launch([], ["/quit"], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys)
    launch([], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys)

    listing = launch(["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys)  # fmt: skip
    assert listing.code == 0
    assert journals(workdir) == []


def test_sessions_list_shows_each_session_of_the_folder_most_recent_first(
    workdir, tmp_path, monkeypatch, capsys
):
    """CA-S6 : par session du dossier courant, identifiant, début de la première
    demande, nombre de demandes, coût et modèle, de la plus récente à la plus
    ancienne ; une session d'un autre dossier n'y figure pas."""
    models = ("principal", "secondaire")

    def open_in(folder, default, requests, costs):
        known = set(journals(folder))
        script: list[Step] = [say("ok", cost=c) for c in costs]
        launch(
            [], [*requests, "/quit"],
            {name: ScriptedModel(script if name == default else []) for name in models},
            folder, monkeypatch, capsys, default=default,
        )  # fmt: skip
        (path,) = set(journals(folder)) - known
        return path

    older = open_in(
        workdir, "principal",
        ["alpha-ancienne-demande", "a2", "a3"], [0.01, 0.01, 0.01],
    )  # fmt: skip
    newer = open_in(workdir, "secondaire", ["beta-recente-demande", "b2"], [0.04, 0.04])
    other_folder = tmp_path / "autre"
    other_folder.mkdir()
    foreign = open_in(other_folder, "principal", ["gamma-ailleurs"], [0.02])
    hour_ago = time.time() - 3600
    os.utime(
        older, (hour_ago, hour_ago)
    )  # dernière activité = date du journal (ADR §5)

    result = launch(
        ["--sessions"], [], {m: ScriptedModel() for m in models},
        workdir, monkeypatch, capsys, default="principal",
    )  # fmt: skip

    out = result.out
    assert result.code == 0
    assert foreign.stem not in out and "gamma-ailleurs" not in out
    assert out.index(newer.stem) < out.index(older.stem), (
        "pas de la plus récente à la plus ancienne"
    )
    at_newer, at_older = out.index(newer.stem), out.index(older.stem)
    new_part = out[at_newer + len(newer.stem) : at_older]
    old_part = out[at_older + len(older.stem) :]
    assert "beta-recente-demande" in new_part and "secondaire" in new_part
    assert money("0.08").search(new_part)
    assert re.search(r"(?<![\d.,])2(?![\d.,])", new_part)
    assert "alpha-ancienne-demande" in old_part and "principal" in old_part
    assert money("0.03").search(old_part)
    assert re.search(r"(?<![\d.,])3(?![\d.,])", old_part)


# --------------------------------------------------------------------------
# Restauration à la reprise
# --------------------------------------------------------------------------


@pytest.mark.parametrize("changed_on_disk", [False, True], ids=["inchange", "modifie"])
def test_file_read_before_closing_stays_editable_unless_changed_on_disk(
    workdir, monkeypatch, capsys, changed_on_disk
):
    """CA-S10 : après reprise, un fichier lu avant la fermeture se modifie sans
    relecture ; s'il a changé sur le disque depuis, la modification est refusée
    avec le message de détection habituel (002) et le changement extérieur reste."""
    target = workdir / "a.txt"
    target.write_text("clé = 1\nautre = 1\n")
    session_id, _ = _open_session(
        workdir, monkeypatch, capsys, ["lis a.txt"],
        [tools(call("read_file", path="a.txt")), say("lu")],
    )  # fmt: skip
    if changed_on_disk:
        target.write_text("clé = 1\nautre = 99\najout extérieur\n")

    change = edit("a.txt", replace("clé = 1", "clé = 2"))
    model = ScriptedModel([tools(change), say("fait")])
    launch(
        ["--resume", session_id], ["modifie a.txt", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip

    output = model.tool_output(change)
    if changed_on_disk:
        assert refused(output) and "read" in output.lower()
        assert "changed" in output.lower(), (
            "refus pour « jamais lu » au lieu de « changé depuis »"
        )
        assert target.read_text() == "clé = 1\nautre = 99\najout extérieur\n"
    else:
        assert not output.startswith("error:"), output
        assert target.read_text() == "clé = 2\nautre = 1\n"


@pytest.mark.parametrize("detailed_at_close", [False, True], ids=["titres", "detaille"])
def test_resume_replays_the_conversation_after_a_header_in_the_closing_display_mode(
    workdir, monkeypatch, capsys, detailed_at_close
):
    """CA-S11 : à la reprise, en-tête (identifiant, date, modèle, coût cumulé)
    puis conversation rejouée dans le mode d'affichage de la fermeture : titres
    sans diff, ou détail avec les lignes modifiées."""
    (workdir / "notes.txt").write_text("alpha\nANCIEN-UN\nbeta\n")
    script = [
        tools(call("read_file", path="notes.txt"), cost=0.01),
        tools(edit("notes.txt", replace("ANCIEN-UN", "NOUVEAU-UN")), cost=0.01),
        say("modification terminée", cost=0.01),
    ]
    inputs = ["modifie notes.txt", *(["/detail"] if detailed_at_close else [])]
    session_id, path = _open_session(workdir, monkeypatch, capsys, inputs, script)
    created = read_journal(path)[0]["created"]

    model = ScriptedModel()
    result = launch(
        ["--resume", session_id], ["/quit"], {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    out = result.out
    assert result.code == 0
    assert session_id in out and "scripted" in out
    assert any(form in out for form in _date_forms(created)), "date de création absente"
    assert money("0.03").search(out), "coût cumulé absent de l'en-tête"
    assert "modifie notes.txt" in out and "modification terminée" in out
    assert "notes.txt" in out
    diff = re.search(r"(?m)^\s*\+\s*NOUVEAU-UN", out)
    assert bool(diff) == detailed_at_close, (
        "mode d'affichage de la fermeture non respecté"
    )
    assert bool(re.search(r"(?m)^\s*-\s*ANCIEN-UN", out)) == detailed_at_close


def test_resume_command_closes_the_current_session_and_opens_the_chosen_one(
    workdir, monkeypatch, capsys
):
    """CA-S12 : `/resume <id>` ferme la session courante (qui reste reprenable) et
    ouvre la session choisie avec ses restaurations (historique, rejeu)."""
    first_id, first_path = _open_session(
        workdir, monkeypatch, capsys, ["demande-de-la-session-A"], [say("réponse A")]
    )
    known = set(journals(workdir))
    model = ScriptedModel([say("réponse B"), say("suite de A")])

    result = launch(
        [], ["demande-de-la-session-B", f"/resume {first_id}", "suite-de-A", "/quit"],
        {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert result.code == 0
    (second_path,) = set(journals(workdir)) - known
    assert len(model.calls) == 2
    assert model.saw_text("demande-de-la-session-A", 1)
    assert model.saw_text("suite-de-A", 1)
    assert not model.saw_text("demande-de-la-session-B", 1), "les sessions se mélangent"
    assert "réponse A" in result.out, "pas de rejeu de la session ouverte"
    assert "suite-de-A" in first_path.read_text()
    assert "suite-de-A" not in second_path.read_text()

    # La session fermée par /resume reste reprenable.
    third = ScriptedModel([say("ok")])
    again = launch(
        ["--resume", second_path.stem], ["encore", "/quit"], {"scripted": third},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    assert again.code == 0 and third.saw_text("demande-de-la-session-B")


def test_a_unique_id_prefix_resumes_and_an_ambiguous_one_names_the_candidates(
    workdir, monkeypatch, capsys
):
    """CA-S13 : un préfixe non ambigu suffit ; un préfixe ambigu est refusé en
    nommant les candidates."""
    _, path = _open_session(
        workdir, monkeypatch, capsys, ["demande-d-origine"], [say("ok")]
    )
    lines = path.read_text().splitlines()
    path.unlink()
    for new_id in ("aaaa1111", "aaaa2222"):
        header = json.loads(lines[0]) | {"session": new_id}
        copy = [json.dumps(header), *lines[1:]]
        (path.parent / f"{new_id}.jsonl").write_text("\n".join(copy) + "\n")

    text = _assert_refused(workdir, monkeypatch, capsys, ["--resume", "aaaa"])
    assert "aaaa1111" in text and "aaaa2222" in text

    model = ScriptedModel([say("repris")])
    result = launch(
        ["--resume", "aaaa1"], ["suite", "/quit"], {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip
    assert result.code == 0 and model.saw_text("demande-d-origine")


# --------------------------------------------------------------------------
# Échecs de reprise
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", ["inconnu", "autre-dossier", "format-inconnu", "en-tete-illisible"]
)
def test_unusable_sessions_are_refused_with_the_cause_and_nothing_changes(
    workdir, tmp_path, monkeypatch, capsys, case
):
    """CA-S14 (et cas limite « dossier déplacé ») : identifiant inconnu, session
    d'un autre dossier (ici : le dossier a été déplacé), version de format inconnue,
    en-tête illisible : message qui nomme la cause, aucune session, journal inchangé."""
    session_id, path = _open_session(
        workdir, monkeypatch, capsys, ["demande"], [say("ok")]
    )
    folder = workdir
    argv = ["--resume", session_id]
    if case == "inconnu":
        argv = ["--resume", "deadbeef"]
    elif case == "autre-dossier":
        folder = tmp_path / "deplace"
        shutil.move(workdir, folder)
    elif case == "format-inconnu":
        lines = path.read_text().split("\n")
        lines[0] = json.dumps(json.loads(lines[0]) | {"format": 99})
        path.write_text("\n".join(lines))
    else:
        lines = path.read_text().split("\n")
        lines[0] = "ceci n'est pas un en-tête"
        path.write_text("\n".join(lines))

    text = _assert_refused(folder, monkeypatch, capsys, argv)

    if case == "inconnu":
        assert "deadbeef" in text and "sessions" in text.lower()
    elif case == "autre-dossier":
        assert str(workdir) in text, "le dossier d'origine n'est pas nommé"
        listing = launch(["--sessions"], [], {"scripted": ScriptedModel()}, folder, monkeypatch, capsys)  # fmt: skip
        assert session_id not in listing.out, "session d'un autre dossier listée"
    elif case == "format-inconnu":
        assert re.search(r"format|version", text, re.IGNORECASE)
    else:
        assert re.search(r"en-t[êe]te|header", text, re.IGNORECASE)


def test_truncated_last_line_is_skipped_with_a_warning_and_the_file_is_never_rewritten(
    workdir, monkeypatch, capsys
):
    """CA-S15 : dernière ligne tronquée : la reprise réussit avec ce qui est
    lisible, un avertissement nomme la ligne ignorée, le contenu d'avant est
    conservé octet pour octet, et la session se reprend encore ensuite."""
    session_id, path = _open_session(
        workdir, monkeypatch, capsys, ["demande-avant-le-crash"], [say("ok")]
    )
    skipped = len(path.read_text().splitlines()) + 1
    path.write_text(
        path.read_text()
        + '{"id": 99, "parentId": 3, "ts": "2026-11-16T10:00:00Z", "type": "mess'
    )
    before = path.read_bytes()

    model = ScriptedModel([say("repris")])
    result = launch(
        ["--resume", session_id], ["suite", "/quit"], {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert result.code == 0
    assert _line_ref(skipped).search(result.out + result.err), (
        "ligne ignorée non nommée"
    )
    assert model.saw_text("demande-avant-le-crash"), "historique lisible perdu"
    after = path.read_bytes()
    assert after.startswith(before), "le journal a été réécrit"
    assert after[len(before) :].startswith(b"\n"), (
        "la ligne tronquée n'est pas fermée avant l'ajout"
    )
    readable = []
    for line in path.read_text().splitlines():
        try:
            readable.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # la ligne tronquée, conservée telle quelle
    marks = [
        e
        for e in readable
        if e.get("type") == "state" and e.get("kind") == "skipped_line"
    ]
    assert [m["line"] for m in marks] == [skipped]

    # Le journal réparé se reprend une seconde fois sans refus.
    again = ScriptedModel([say("encore")])
    second = launch(
        ["--resume", session_id], ["et ensuite", "/quit"], {"scripted": again},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    assert second.code == 0 and again.saw_text("suite")


@pytest.mark.parametrize("damage", ["ligne-invalide", "parent-inexistant"])
def test_invalid_line_in_the_middle_or_broken_link_is_refused_naming_the_line(
    workdir, monkeypatch, capsys, damage
):
    """CA-S16 : ligne invalide au milieu, ou entrée dont le parent n'existe pas :
    refus qui nomme la ligne (ici la 3), journal inchangé, aucune session."""
    session_id, path = _open_session(
        workdir, monkeypatch, capsys, ["demande"], [say("ok")]
    )
    lines = path.read_text().split("\n")
    assert len(lines) >= 5, "précondition : l'invalide doit être au milieu du journal"
    if damage == "ligne-invalide":
        lines[2] = '{"id": 2, "parentId": 1, "type": "mess'
    else:
        lines[2] = json.dumps(json.loads(lines[2]) | {"parentId": 9999})
    path.write_text("\n".join(lines))

    text = _assert_refused(workdir, monkeypatch, capsys, ["--resume", session_id])

    assert _line_ref(3).search(text), f"ligne fautive non nommée : {text!r}"


def test_call_without_result_gets_an_error_result_appended_and_the_model_is_told(
    workdir, monkeypatch, capsys
):
    """CA-S17 : appel d'action sans résultat : la reprise réussit, un résultat
    d'erreur « action interrompue, état inconnu » est ajouté à la fin du journal,
    et le modèle reçoit un historique où chaque appel a un résultat."""
    session_id, path = _open_session(
        workdir, monkeypatch, capsys, ["lance la commande"],
        [tools(call("shell", command="echo orphelin")), say("terminé")],
    )  # fmt: skip
    lines = path.read_text().splitlines()
    cut = next(
        i for i, line in enumerate(lines[1:], 1)
        if '"role": "tool"' in json.dumps(json.loads(line))
    )  # fmt: skip
    path.write_text("\n".join(lines[:cut]) + "\n")  # arrêt brutal avant le résultat
    before = path.read_bytes()

    model = ScriptedModel([say("je tiens compte de l'interruption")])
    result = launch(
        ["--resume", session_id], ["que s'est-il passé ?", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert result.code == 0
    seen = model.calls[0]
    call_ids = [c["id"] for m in seen for c in m.get("tool_calls") or []]
    assert len(call_ids) == 1
    results = tool_outputs(seen, call_ids[0])
    assert len(results) == 1, "chaque appel doit avoir exactement un résultat"
    assert "interrompue" in results[0]
    after = path.read_bytes()
    assert after.startswith(before)
    added = [
        e
        for e in read_journal(path)
        if "interrompue" in json.dumps(e, ensure_ascii=False)
    ]
    assert len(added) == 1 and added[0]["type"] == "message"


def test_resume_with_an_unreachable_model_fails_like_launch_and_changes_nothing(
    workdir, monkeypatch, capsys
):
    """CA-S18 : modèle injoignable ou clé absente à la reprise : le message du
    lancement, aucune session ouverte, journal inchangé."""
    session_id, _ = _open_session(
        workdir, monkeypatch, capsys, ["demande"], [say("ok")]
    )
    before = _snapshot(workdir)
    model = ScriptedModel(
        check_error=ProviderError("auth", "Clé CLE_DE_TEST_ABSENTE manquante (test).")
    )

    result = launch(
        ["--resume", session_id], ["ne doit pas être lue", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert "CLE_DE_TEST_ABSENTE" in result.out + result.err
    assert model.calls == []
    assert _snapshot(workdir) == before


# --------------------------------------------------------------------------
# Cas limites : journaux vides, identifiants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("content", ["en-tete-seul", "vide"])
def test_empty_or_header_only_journal_is_not_listed_and_resume_is_refused(
    workdir, monkeypatch, capsys, content
):
    """Spec §6 : journal vide ou en-tête seul : ni listé, refus clair à la reprise."""
    session_id, path = _open_session(
        workdir, monkeypatch, capsys, ["demande"], [say("ok")]
    )
    path.write_text(
        path.read_text().splitlines()[0] + "\n" if content == "en-tete-seul" else ""
    )

    listing = launch(["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys)  # fmt: skip
    text = _assert_refused(workdir, monkeypatch, capsys, ["--resume", session_id])

    assert session_id not in listing.out
    assert session_id in text, "le refus ne nomme pas la session"


def test_sessions_opened_back_to_back_get_distinct_ids(workdir, monkeypatch, capsys):
    """Spec §6 : plusieurs sessions démarrées dans la même seconde : identifiants distincts."""
    ids = {
        _open_session(workdir, monkeypatch, capsys, [f"demande {n}"], [say("ok")])[0]
        for n in range(3)
    }

    assert len(ids) == 3 and len(journals(workdir)) == 3


# --------------------------------------------------------------------------
# Arrêt brutal et session occupée (vrais sous-processus)
# --------------------------------------------------------------------------


def test_sigkill_in_mid_turn_keeps_everything_before_the_current_entry(
    workdir, monkeypatch, capsys
):
    """CA-S2 : processus tué (SIGKILL) en plein tour : tout ce qui précède l'entrée
    en cours est dans le journal, qui reste lisible, et la session est reprenable
    avec cet historique."""
    session_id = _killed_in_mid_turn(workdir)

    (path,) = journals(workdir)
    text = path.read_text()
    complete = text.split("\n")[:-1]  # la dernière ligne a pu être coupée
    entries = [json.loads(line) for line in complete]
    dumped = json.dumps(entries, ensure_ascii=False)
    assert entries[0]["type"] == "header"
    assert "lance la tâche" in dumped, "demande absente"
    assert "avant" in dumped, "résultat du premier outil absent"
    assert "sleep 120" in dumped, "appel en cours absent (écrit avant l'exécution)"

    model = ScriptedModel([say("repris après l'arrêt")])
    result = launch(
        ["--resume", session_id], ["et maintenant ?", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    assert result.code == 0
    assert model.saw_text("lance la tâche", 0) and model.saw_text("avant", 0)


def test_session_left_busy_by_a_killed_process_is_resumable_without_manual_step(
    workdir, monkeypatch, capsys
):
    """CA-S26 : après SIGKILL du processus qui tenait la session, la reprise
    réussit sans intervention manuelle (verrou périmé), puis se referme proprement."""
    session_id = _killed_in_mid_turn(workdir)

    model = ScriptedModel([say("repris")])
    first = launch(
        ["--resume", session_id], ["suite", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    again = ScriptedModel([say("repris encore")])
    second = launch(
        ["--resume", session_id], ["et encore", "/quit"], {"scripted": again},
        workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert first.code == 0 and model.calls, "reprise refusée après un arrêt brutal"
    assert not re.search(r"occup", first.out + first.err, re.IGNORECASE)
    assert second.code == 0 and again.calls, "le verrou n'a pas été libéré à la sortie"


def test_session_open_in_another_process_cannot_be_resumed_and_nothing_is_written(
    workdir, monkeypatch, capsys
):
    """CA-S25 : une session ouverte dans un REPL ne peut pas être reprise par un
    second processus (REPL ou headless) : message qui nomme la session occupée,
    rien n'est écrit dans le journal."""
    proc = _spawn(workdir, "hold")
    try:
        _wait_for(lambda: "session ouverte" in _journal_text(workdir))
        (path,) = journals(workdir)
        session_id = path.stem
        before = path.read_bytes()

        repl_text = _assert_refused(
            workdir, monkeypatch, capsys, ["--resume", session_id]
        )
        headless = launch(
            ["--resume", session_id, "--prompt", "bonjour"], [], {"scripted": ScriptedModel([say("non")])},
            workdir, monkeypatch, capsys,
        )  # fmt: skip
        listing = launch(["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys)  # fmt: skip

        assert session_id in repl_text
        assert headless.code == 2 and session_id in headless.err
        assert path.read_bytes() == before
        assert session_id in listing.out
    finally:
        _kill(proc)
