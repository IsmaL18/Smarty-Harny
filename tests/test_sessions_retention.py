"""Sessions durables, tranche 3 (3/3) : suppression d'une session et purge à N jours.

Spec 003 §4.7, CA-S27 et CA-S28 ; ADR-0012 §3.5, §5, §6 ; config `[sessions] retention_days`.
Seams : `cli.main.main` (`--delete`, lancement normal avec purge, `--sessions`) avec un
modèle simulé et les vrais outils ; fichiers sous `.harness/` ; vrai sous-processus
pour la session occupée. La date de dernière activité est la date de modification du
journal (ADR-0012 §5), que les tests reculent avec `os.utime`.

Hypothèses d'interface (la spec et l'ADR ne les fixent pas) : la confirmation de
`--delete` est lue sur l'entrée standard comme n'importe quelle saisie (« oui » ou
« non ») et nomme la session ; le message de purge est affiché sur stdout ou stderr,
contient « purg » ou « supprim » et le nombre de sessions purgées.
"""

import os
import re
import time

from support import (
    ScriptedModel,
    Step,
    call,
    journals,
    kill_process_group,
    launch,
    say,
    spawn_open_session,
    tools,
)

LONG_COMMAND = 'for i in $(seq 1 3000); do echo "sortie $i"; done'
SMALL_OUTPUTS = "[tools]\nmax_output_chars = 1000\n"
RETENTION_7_DAYS = SMALL_OUTPUTS + "[sessions]\nretention_days = 7\n"


def _open_session(workdir, monkeypatch, capsys, request, *, saved_output=True):
    """Ouvre puis ferme une vraie session ; rend (id, dossier de ses sorties)."""
    known = set(journals(workdir))
    script: list[Step] = [tools(call("shell", command=LONG_COMMAND)), say("fini")]
    launch(
        [], [request, "/quit"],
        {"scripted": ScriptedModel(script if saved_output else [say("ok")])},
        workdir, monkeypatch, capsys, extra_toml=SMALL_OUTPUTS,
    )  # fmt: skip
    (path,) = set(journals(workdir)) - known
    return path.stem, workdir / ".harness" / "outputs" / path.stem


def _age(workdir, session_id, days):
    old = time.time() - days * 86400
    path = workdir / ".harness" / "sessions" / f"{session_id}.jsonl"
    os.utime(path, (old, old))


def _delete(workdir, monkeypatch, capsys, session_id, answer):
    return launch(
        ["--delete", session_id], [answer], {"scripted": ScriptedModel()},
        workdir, monkeypatch, capsys,
    )  # fmt: skip


def _listing(workdir, monkeypatch, capsys) -> str:
    return launch(
        ["--sessions"], [], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys
    ).out


def test_delete_asks_confirmation_then_removes_journal_and_saved_outputs(
    workdir, monkeypatch, capsys
):
    """CA-S27 : sans confirmation rien n'est supprimé ; après confirmation le journal
    et les sorties enregistrées disparaissent et la session sort de la liste."""
    doomed, doomed_outputs = _open_session(
        workdir, monkeypatch, capsys, "demande-a-supprimer"
    )
    kept, _ = _open_session(
        workdir, monkeypatch, capsys, "demande-a-garder", saved_output=False
    )
    journal = workdir / ".harness" / "sessions" / f"{doomed}.jsonl"
    assert doomed_outputs.is_dir(), (
        "précondition : la session possède des sorties enregistrées"
    )

    declined = _delete(workdir, monkeypatch, capsys, doomed, "non")
    assert doomed in declined.out + declined.err, (
        "la confirmation ne nomme pas la session"
    )
    assert journal.is_file() and doomed_outputs.is_dir(), "supprimé sans confirmation"

    confirmed = _delete(workdir, monkeypatch, capsys, doomed, "oui")

    assert confirmed.code == 0
    assert not journal.exists() and not doomed_outputs.exists()
    listing = _listing(workdir, monkeypatch, capsys)
    assert doomed not in listing and kept in listing


def test_delete_is_refused_on_a_session_open_in_another_process(
    workdir, monkeypatch, capsys
):
    """CA-S27 : la suppression d'une session occupée est refusée (rien n'est supprimé)
    et le message nomme la session."""
    proc = spawn_open_session(workdir)
    try:
        (journal,) = journals(workdir)
        before = journal.read_bytes()

        result = _delete(workdir, monkeypatch, capsys, journal.stem, "oui")

        assert journal.read_bytes() == before, "session occupée supprimée ou modifiée"
        assert journal.stem in result.out + result.err
    finally:
        kill_process_group(proc)


def test_launch_purges_sessions_idle_longer_than_retention_days_except_recent_or_busy(
    workdir, monkeypatch, capsys
):
    """CA-S28 : au lancement, les sessions inactives depuis plus de `retention_days`
    sont supprimées avec leurs sorties enregistrées et un message donne leur nombre ;
    une session récente ou occupée (même ancienne) reste."""
    old_one, old_one_outputs = _open_session(workdir, monkeypatch, capsys, "vieille-un")
    old_two, old_two_outputs = _open_session(
        workdir, monkeypatch, capsys, "vieille-deux"
    )
    recent, recent_outputs = _open_session(workdir, monkeypatch, capsys, "recente")
    proc = spawn_open_session(workdir)
    try:
        (busy,) = {p.stem for p in journals(workdir)} - {old_one, old_two, recent}
        for session_id in (old_one, old_two, busy):
            _age(workdir, session_id, 10)
        _age(workdir, recent, 3)

        result = launch(
            [], ["/quit"], {"scripted": ScriptedModel()}, workdir, monkeypatch, capsys,
            extra_toml=RETENTION_7_DAYS,
        )  # fmt: skip

        remaining = {p.stem for p in journals(workdir)}
        assert remaining == {recent, busy}, (
            f"sessions restantes inattendues : {remaining}"
        )
        assert not old_one_outputs.exists() and not old_two_outputs.exists()
        assert recent_outputs.is_dir()
        text = result.out + result.err
        message = [
            line
            for line in text.splitlines()
            if re.search(r"purg|supprim", line, re.IGNORECASE)
        ]
        assert any(re.search(r"(?<![\d.])2(?!\d)", line) for line in message), (
            f"aucun message ne donne le nombre de sessions purgées (2) : {text!r}"
        )
    finally:
        kill_process_group(proc)
