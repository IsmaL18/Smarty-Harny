"""Sessions durables, tranche 3 (2/3) : commande `/branch` du REPL.

Spec 003 §4.5 et §6, CA-S20 à CA-S24 ; ADR-0012 §2 (branches), §6.
Seam : `cli.main.main` avec un modèle simulé et les vrais outils, REPL piloté par
des saisies, puis lecture du journal (JSONL) et reprise par `--resume`.

Hypothèses d'interface (la spec et l'ADR ne les fixent pas) : `/branch` affiche la
liste numérotée des demandes (« 1. texte ») puis lit sur l'entrée suivante le
numéro choisi ; la saisie d'après est la nouvelle demande. L'avertissement contient
« restaur » ; le message au modèle est un message `user` distinct des demandes.
"""

import re

from support import (
    ScriptedModel,
    call,
    edit,
    journals,
    launch,
    money,
    read_journal,
    refused,
    replace,
    say,
    tools,
)


def _requests(model, call_index=-1) -> list[str]:
    return [m["content"] for m in model.calls[call_index] if m.get("role") == "user"]


def test_branch_lists_the_requests_and_restarts_from_before_the_chosen_one(
    workdir, monkeypatch, capsys
):
    """CA-S20 + CA-S21 : `/branch` liste les demandes numérotées ; en choisir une puis
    saisir une nouvelle demande envoie au modèle un historique sans la demande
    choisie ni les suivantes ; l'ancienne branche reste, octet pour octet, dans le journal."""
    model = ScriptedModel(
        [say("réponse-un"), say("réponse-deux"), say("réponse-trois")]
    )
    launch(
        [], ["demande-un", "demande-deux", "demande-trois", "/quit"],
        {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip
    (journal,) = journals(workdir)
    before = journal.read_bytes()

    model = ScriptedModel([say("réponse-bis")])
    result = launch(
        ["--resume", journal.stem],
        ["/branch", "2", "demande-bis", "/quit"],
        {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    listed = re.findall(r"(?m)^\s*(\d+)\W+.*?(demande-\w+)", result.out)
    assert listed[:3] == [
        ("1", "demande-un"),
        ("2", "demande-deux"),
        ("3", "demande-trois"),
    ]
    seen = " ".join(_requests(model))
    assert "demande-un" in seen and "demande-bis" in seen
    assert "demande-deux" not in seen and "demande-trois" not in seen
    assert not model.saw_text("réponse-deux") and not model.saw_text("réponse-trois")
    after = journal.read_bytes()
    assert after.startswith(before), "l'ancienne branche a été modifiée"
    assert b"demande-trois" in after and b"demande-bis" in after


def test_closing_and_resuming_after_a_branch_reopens_the_new_branch_with_the_total_cost(
    workdir, monkeypatch, capsys
):
    """CA-S23 + CA-S24 : après un changement de branche, le coût cumulé affiché inclut
    la branche abandonnée ; fermer puis reprendre rouvre la nouvelle branche."""
    model = ScriptedModel([say(f"réponse-{i}", cost=0.01) for i in (1, 2, 3)])
    launch(
        [], ["demande-un", "demande-deux", "demande-trois", "/branch", "2", "demande-bis", "/quit"],
        {"scripted": ScriptedModel([*model.script, say("réponse-bis", cost=0.01)])},
        workdir, monkeypatch, capsys,
    )  # fmt: skip
    (journal,) = journals(workdir)

    resumed = ScriptedModel([say("suite")])
    result = launch(
        ["--resume", journal.stem], ["suite-de-la-nouvelle-branche", "/quit"],
        {"scripted": resumed}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert money("0.04").search(result.out), "coût de la branche abandonnée non compté"
    assert "demande-bis" in result.out and "demande-trois" not in result.out
    seen = " ".join(_requests(resumed))
    assert "demande-bis" in seen and "suite-de-la-nouvelle-branche" in seen
    assert "demande-deux" not in seen and "demande-trois" not in seen


def test_after_a_branch_change_the_user_is_warned_the_model_is_told_and_files_must_be_reread(
    workdir, monkeypatch, capsys
):
    """CA-S22 : avertissement « fichiers non restaurés » ; message au modèle ; un
    fichier lu avant le changement ne peut plus être modifié tant qu'il n'est pas relu."""
    target = workdir / "a.txt"
    target.write_text("clé = 1\n")
    change = edit("a.txt", replace("clé = 1", "clé = 2"))
    refused_try = call("edit_file", **json_args(change))
    retry = call("edit_file", **json_args(change))
    model = ScriptedModel(
        [
            tools(call("read_file", path="a.txt")), say("lu"),
            say("seconde-réponse"),
            tools(refused_try),
            tools(call("read_file", path="a.txt")),
            tools(retry),
            say("fait"),
        ]
    )  # fmt: skip

    result = launch(
        [],
        ["lis a.txt", "demande-deux", "/branch", "2", "modifie a.txt", "/quit"],
        {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert re.search(r"restaur", result.out, re.IGNORECASE), "pas d'avertissement"
    assert re.search(
        r"restaur[^\n]*fichier|fichier[^\n]*restaur", result.out, re.IGNORECASE
    )
    first_try = next(
        c for c in model.calls if any("modifie a.txt" in str(m) for m in c)
    )
    notices = [
        m["content"] for m in first_try
        if m.get("role") == "user"
        and not re.search(r"lis a.txt|modifie a.txt|demande-deux", m["content"])
    ]  # fmt: skip
    assert notices and re.search(
        r"dossier|fichier|relis|folder|file", notices[-1], re.IGNORECASE
    )
    refusal = _output_of(model, refused_try)
    assert refused(refusal) and "read" in refusal.lower(), refusal
    assert "clé = 2" in target.read_text(), "la modification après relecture a échoué"
    assert not refused(_output_of(model, retry))


def test_branch_on_the_first_request_restarts_from_an_empty_history(
    workdir, monkeypatch, capsys
):
    """Spec §6 : branche choisie sur la première demande : l'historique d'avant est
    vide, la nouvelle branche repart de l'état initial."""
    model = ScriptedModel(
        [say("réponse-un"), say("réponse-deux"), say("réponse-neuve")]
    )
    launch(
        [], ["demande-un", "demande-deux", "/branch", "1", "demande-neuve", "/quit"],
        {"scripted": model}, workdir, monkeypatch, capsys,
    )  # fmt: skip

    seen = " ".join(_requests(model))
    assert "demande-neuve" in seen
    assert "demande-un" not in seen and "demande-deux" not in seen
    assert not model.saw_text("réponse-un") and not model.saw_text("réponse-deux")


def test_branch_with_no_request_says_so_without_error_and_the_session_goes_on(
    workdir, monkeypatch, capsys
):
    """Spec §6 : liste de demandes vide : la commande le dit sans erreur et
    n'empêche pas de saisir une demande ensuite."""
    model = ScriptedModel([say("bonjour à vous")])

    result = launch(
        [], ["/branch", "première-demande", "/quit"], {"scripted": model},
        workdir, monkeypatch, capsys,
    )  # fmt: skip

    assert result.code == 0
    assert "Traceback" not in result.out + result.err
    assert "première-demande" in " ".join(_requests(model))
    assert read_journal(journals(workdir)[0])[0]["type"] == "header"


def json_args(tool_call: dict) -> dict:
    import json

    return json.loads(tool_call["function"]["arguments"])


def _output_of(model, tool_call: dict) -> str:
    from support import tool_outputs

    for seen in reversed(model.calls):
        found = tool_outputs(seen, tool_call["id"])
        if found:
            return found[0]
    raise AssertionError("le modèle n'a jamais reçu ce résultat")
