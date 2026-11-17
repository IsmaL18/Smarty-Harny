"""Sessions durables : journal en ajout seul et reprise par identifiant.

Spec 003 §5 (CA-S1, CA-S5, CA-S7, CA-S8, CA-S9) ; ADR-0012 §1, §2, §6.
Le point d'entrée `cli.main.main` est lancé (deux fois pour une reprise) avec
un modèle simulé et les vrais outils ; on ne vérifie que ce que voient
l'utilisateur, le modèle et le fichier du journal (JSONL : champs `type`,
`id`, `parentId`, en-tête).
"""

from support import (
    ScriptedModel,
    call,
    journals,
    launch,
    money,
    read_journal,
    say,
    tools,
)


def _only_journal(workdir):
    found = journals(workdir)
    assert len(found) == 1, f"un journal attendu sous .harness/sessions/ : {found}"
    return found[0]


def test_journal_records_header_request_reply_action_result_and_usage(
    workdir, monkeypatch, capsys
):
    """CA-S1 : après une demande qui déclenche une action, le journal (dans le
    dossier de travail) contient en-tête, demande, réponse, appel, résultat tel
    que reçu par le modèle, usage/coût."""
    (workdir / "notes.txt").write_text("contenu-unique-xyz\n")
    read = call("read_file", path="notes.txt")
    model = ScriptedModel([tools(read, cost=0.0123), say("voilà", cost=0.0045)])

    result = launch(
        [],
        ["lis notes.txt", "/quit"],
        {"scripted": model},
        workdir,
        monkeypatch,
        capsys,
    )

    assert result.code == 0
    path = _only_journal(workdir)
    header, *entries = read_journal(path)
    assert header["type"] == "header"
    assert header["format"] == 1
    assert header["session"] == path.stem
    assert header["model"] == "scripted"
    assert header["workdir"] and header["created"]
    text = path.read_text()
    assert "lis notes.txt" in text  # la demande
    assert "read_file" in text  # l'appel d'action
    assert "voilà" in text  # la réponse du modèle
    received = model.tool_output(read)
    assert "contenu-unique-xyz" in received
    tool_entries = [
        e for e in entries if e["type"] == "message" and "contenu-unique-xyz" in str(e)
    ]
    assert tool_entries, "le résultat de l'outil n'est pas dans le journal"
    usages = [e for e in entries if e["type"] == "usage"]
    assert sorted(u["cost_usd"] for u in usages) == [0.0045, 0.0123]
    assert [e["id"] for e in entries] == sorted(e["id"] for e in entries)
    assert entries[0]["parentId"] is None


def test_resume_only_appends_to_the_journal(workdir, monkeypatch, capsys):
    """CA-S5 : reprendre une session ne modifie aucun octet existant du journal."""
    launch(
        [], ["première demande", "/quit"],
        {"scripted": ScriptedModel([say("ok")])}, workdir, monkeypatch, capsys,
    )  # fmt: skip
    path = _only_journal(workdir)
    before = path.read_bytes()
    session_id = read_journal(path)[0]["session"]

    launch(
        ["--resume", session_id], ["seconde demande", "/quit"],
        {"scripted": ScriptedModel([say("encore ok")])}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    after = path.read_bytes()
    assert after.startswith(before), "le contenu d'avant a été modifié"
    assert len(after) > len(before), "la reprise n'a rien ajouté"
    assert journals(workdir) == [path], "la reprise a créé une autre session"


def test_resumed_session_remembers_the_file_it_created(workdir, monkeypatch, capsys):
    """CA-S7 : fichier créé, session fermée par /quit, reprise par identifiant :
    « modifie ce fichier » est compris, l'historique est restauré."""
    write = call("write_file", path="rapport.txt", content="version un\n")
    launch(
        [], ["crée rapport.txt", "/quit"],
        {"scripted": ScriptedModel([tools(write), say("créé")])},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    session_id = read_journal(_only_journal(workdir))[0]["session"]

    second = ScriptedModel([say("modifié")])
    result = launch(
        ["--resume", session_id], ["modifie ce fichier", "/quit"],
        {"scripted": second}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert result.code == 0
    assert second.saw_text("crée rapport.txt"), (
        "demande d'avant absente de l'historique"
    )
    assert second.saw_text("rapport.txt")
    assert second.saw_text("modifie ce fichier")
    roles = [m["role"] for m in second.calls[0]]
    assert roles.count("user") >= 2 and "tool" in roles


def test_resumed_session_keeps_cumulative_cost_and_partly_spent_budget(
    workdir, monkeypatch, capsys
):
    """CA-S8 : le coût cumulé reprend au total d'avant ; un budget déjà en partie
    consommé ne repart pas de zéro (limite atteinte plus tôt, « continuer ? »)."""
    launch(
        [], ["première demande", "/quit"],
        {"scripted": ScriptedModel([say("ok", cost=0.06)])},
        workdir, monkeypatch, capsys, budget=0.10,
    )  # fmt: skip
    session_id = read_journal(_only_journal(workdir))[0]["session"]

    step = call("shell", command="echo bonjour")
    resumed = ScriptedModel([tools(step, cost=0.06), say("fini")])
    result = launch(
        ["--resume", session_id], ["seconde demande", "non", "/quit"],
        {"scripted": resumed}, workdir, monkeypatch, capsys, budget=0.10,
    )  # fmt: skip

    # 0,06 (avant) + 0,06 (maintenant) = 0,12 > 0,10 : le budget est atteint.
    assert "continuer" in result.out.lower(), "budget déjà consommé ignoré à la reprise"
    assert money("0.12").search(result.out), "coût cumulé non restauré"


def test_resume_restores_active_model_and_model_option_overrides_and_records_it(
    workdir, monkeypatch, capsys
):
    """CA-S9 : le modèle actif est restauré à la reprise ; avec --model, le
    modèle demandé est actif et enregistré."""
    first_a = ScriptedModel([say("ok")])
    first_b = ScriptedModel()
    launch(
        [], ["/model secondaire", "première demande", "/quit"],
        {"principal": first_a, "secondaire": first_b},
        workdir, monkeypatch, capsys, default="principal",
    )  # fmt: skip
    path = _only_journal(workdir)
    session_id = read_journal(path)[0]["session"]
    assert first_b.calls, "précondition : /model a bien basculé sur le secondaire"

    # Reprise sans option : le modèle de la fin de session (secondaire) répond.
    a, b = ScriptedModel([say("a")]), ScriptedModel([say("b")])
    launch(
        ["--resume", session_id], ["suite", "/quit"],
        {"principal": a, "secondaire": b}, workdir, monkeypatch, capsys,
        default="principal",
    )  # fmt: skip
    assert b.calls and not a.calls, "le modèle de la fin de session n'est pas restauré"

    # Reprise avec --model : le modèle demandé répond et reste le modèle de la session.
    a2, b2 = ScriptedModel([say("a")]), ScriptedModel([say("b")])
    launch(
        ["--resume", session_id, "--model", "principal"], ["encore", "/quit"],
        {"principal": a2, "secondaire": b2}, workdir, monkeypatch, capsys,
        default="principal",
    )  # fmt: skip
    assert a2.calls and not b2.calls, "--model n'est pas respecté à la reprise"

    a3, b3 = ScriptedModel([say("a")]), ScriptedModel([say("b")])
    launch(
        ["--resume", session_id], ["toujours", "/quit"],
        {"principal": a3, "secondaire": b3}, workdir, monkeypatch, capsys,
        default="principal",
    )  # fmt: skip
    assert a3.calls and not b3.calls, "le modèle demandé n'a pas été enregistré"
