"""Écarts relevés en revue entre la spec/l'ADR-0012 et le comportement observable.

Spec 003 §4.1, §4.8, CA-S4, CA-S30 ; ADR-0012 §2 (échec d'écriture, cumuls et
tranches, secrets), §3 (perte du verrou), §7 (réponse finale).

Seam : `cli.main.main(argv, client_factory=...)` avec un modèle simulé et les vrais
outils (aides `launch` et `headless`). Les pannes sont provoquées depuis une étape
dynamique du modèle simulé (effet de bord pendant l'appel au modèle), jamais en
touchant au code du harness.
"""

import json
import re
import time
from pathlib import Path

import pytest
from support import (
    ScriptedModel,
    call,
    headless,
    journals,
    jsonl_lines,
    launch,
    read_journal,
    say,
    tools,
    values,
)

from harness.models.base import ModelResponse

JSONL = ["--output-format", "jsonl"]


def _break_journal(workdir: Path, response: ModelResponse):
    """Étape de modèle qui rend le journal inscriptible-impossible (le fichier devient
    un dossier : l'ouverture en écriture échoue, même pour root) avant de répondre."""

    def step(_messages: list[dict]) -> ModelResponse:
        (journal,) = journals(workdir)
        journal.rename(journal.with_suffix(".bak"))
        journal.mkdir()
        return response

    return step


def test_journal_write_failure_makes_headless_exit_1_with_an_error_result(
    workdir, monkeypatch, capfd
):
    """ADR-0012 §2 « Échec d'écriture » + §7 (RecordingFailed -> `error`, code 1) :
    écriture impossible en cours de run -> aucune exception jusqu'à `main`, code 1,
    ligne `warning`, ligne finale `result` de statut d'erreur."""
    model = ScriptedModel([_break_journal(workdir, say("réponse"))])

    run = headless(
        ["-p", "fais la tâche", *JSONL],
        {"scripted": model},
        workdir,
        monkeypatch,
        capfd,
    )

    assert run.code == 1
    stream = jsonl_lines(run.out)
    assert any(line["type"] == "warning" for line in stream), "aucun avertissement"
    assert stream[-1]["type"] == "result"
    assert "error" in values(stream[-1])


def test_journal_write_failure_in_the_repl_warns_and_the_conversation_goes_on(
    workdir, monkeypatch, capfd
):
    """ADR-0012 §2 « Échec d'écriture » : l'interface avertit, la conversation reste
    en mémoire (le tour suivant est répondu, avec l'historique) et le REPL sort
    proprement."""
    model = ScriptedModel([_break_journal(workdir, say("un")), say("deux")])

    result = launch(
        [], ["première demande", "seconde demande", "/quit"], {"scripted": model},
        workdir, monkeypatch, capfd,
    )  # fmt: skip

    assert result.code == 0
    assert re.search(r"enregistr|journal", result.out + result.err, re.IGNORECASE), (
        "aucun avertissement d'enregistrement désactivé"
    )
    assert len(model.calls) == 2, "le tour suivant n'a pas été répondu"
    assert model.saw_text("première demande", 1), "conversation perdue en mémoire"
    assert "deux" in result.out


@pytest.mark.parametrize("output_format", [[], JSONL], ids=["text", "jsonl"])
def test_headless_empty_final_message_does_not_promote_intermediate_text_to_answer(
    workdir, monkeypatch, capfd, output_format
):
    """CA-S30 + ADR-0012 §7 : la réponse finale est le texte du message qui termine
    le tour (sans appel d'outil). Ce message est vide : le texte du message
    intermédiaire (avec appel d'outil) n'est jamais présenté comme réponse finale ;
    le tour est terminé normalement (code 0)."""
    intermediate = "je vais d'abord lire le fichier"
    step = call("shell", command="echo bonjour")
    announcing = ModelResponse(
        message={
            "role": "assistant",
            "content": intermediate,
            "tool_calls": [step],
        },
        finish_reason="tool_calls",
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        cost_usd=0.0,
    )
    model = ScriptedModel([announcing, say("")])

    run = headless(
        ["-p", "fais la tâche", *output_format], {"scripted": model}, workdir,
        monkeypatch, capfd,
    )  # fmt: skip

    assert run.code == 0
    if output_format:
        result = jsonl_lines(run.out)[-1]
        assert result["type"] == "result" and "ok" in values(result)
        assert intermediate not in values(result), "texte intermédiaire en réponse"
    else:
        assert run.out.strip() == "", "stdout doit rester vide : réponse finale vide"


def test_budget_slice_granted_in_the_repl_is_restored_when_the_session_is_resumed(
    workdir, monkeypatch, capsys
):
    """Spec §4.1 + ADR-0012 §2 « Cumuls et état de session » : la tranche accordée à
    « continuer ? » est consignée ; à la reprise, la limite est budget + tranches.
    Coût 0,18 < 0,10 + 0,10 : la demande suivante est traitée sans nouvelle question."""
    shell = call("shell", command="true")
    first = ScriptedModel(
        [tools(shell, cost=0.06), tools(shell, cost=0.06), say("fini", cost=0.06)]
    )
    started = launch(
        [], ["travaille", "oui", "/quit"], {"scripted": first},
        workdir, monkeypatch, capsys, budget=0.10,
    )  # fmt: skip
    assert started.out.lower().count("continuer") >= 1, "précondition : limite atteinte"
    assert len(first.calls) == 3, "précondition : la tranche a été accordée"
    session_id = read_journal(journals(workdir)[0])[0]["session"]

    resumed = ScriptedModel([say("suite")])
    result = launch(
        ["--resume", session_id], ["encore", "/quit"], {"scripted": resumed},
        workdir, monkeypatch, capsys, budget=0.10,
    )  # fmt: skip

    assert result.code == 0
    assert "continuer" not in result.out.lower(), "tranche accordée oubliée"
    assert resumed.calls, "la demande n'a pas atteint le modèle"


def test_process_that_lost_its_session_lock_no_longer_writes_to_the_journal(
    workdir, monkeypatch, capfd
):
    """ADR-0012 §3.2 : si le verrou a été pris par un autre (bail expiré, verrou
    repris), le détenteur d'origine désactive l'écriture comme pour un `JournalError` :
    le journal n'est plus modifié, le verrou de l'autre n'est pas supprimé, le run
    sort en code 1."""
    other = {"token": "autre-processus", "hostname": "autre-conteneur", "pid": 1}
    seen: dict[str, bytes] = {}

    def lose_the_lock(_messages: list[dict]) -> ModelResponse:
        (journal,) = journals(workdir)
        lock = journal.with_suffix(".lock")
        lock.write_text(json.dumps(other))  # un autre processus a repris le verrou
        time.sleep(1.5)  # plusieurs battements (bail réglé à 1,5 s : battement 0,5 s)
        seen["journal"] = journal.read_bytes()
        return say("réponse")

    model = ScriptedModel([lose_the_lock])
    run = headless(
        ["-p", "fais la tâche", *JSONL], {"scripted": model}, workdir, monkeypatch,
        capfd, extra_toml="[sessions]\nlock_stale_s = 1.5\n",
    )  # fmt: skip

    (journal,) = journals(workdir)
    assert journal.read_bytes() == seen["journal"], "écriture après perte du verrou"
    assert json.loads(journal.with_suffix(".lock").read_text()) == other
    assert run.code == 1
    assert "error" in values(jsonl_lines(run.out)[-1])


@pytest.mark.parametrize("secret", ['"', "\\", "n", "1"])
def test_very_short_secret_never_makes_a_journal_line_unreadable(
    workdir, monkeypatch, capsys, secret
):
    """CA-S4 + ADR-0012 §2 (masquage) : une clé d'un caractère, présente dans le
    contenu, est masquée sans casser le JSON des lignes : chaque ligne reste un JSON
    valide et la session se reprend avec son historique."""
    monkeypatch.setenv("TEST_HARNESS_KEY", secret)
    echo = call("shell", command='echo "a 1 \\ n \\"quoted\\""')
    launch(
        [], ["lance la commande", "/quit"],
        {"scripted": ScriptedModel([tools(echo), say("terminé")])},
        workdir, monkeypatch, capsys,
        profile_extra='api_key_env = "TEST_HARNESS_KEY"\n',
    )  # fmt: skip

    (journal,) = journals(workdir)
    for number, line in enumerate(journal.read_text().splitlines(), 1):
        try:
            json.loads(line)
        except json.JSONDecodeError:
            pytest.fail(f"ligne {number} du journal illisible : {line!r}")

    resumed = ScriptedModel([say("suite")])
    result = launch(
        ["--resume", journal.stem], ["et ensuite", "/quit"], {"scripted": resumed},
        workdir, monkeypatch, capsys,
        profile_extra='api_key_env = "TEST_HARNESS_KEY"\n',
    )  # fmt: skip

    assert result.code == 0, result.err
    roles = [m["role"] for m in resumed.calls[0]]
    assert roles.count("user") >= 2 and "tool" in roles, "historique perdu"
