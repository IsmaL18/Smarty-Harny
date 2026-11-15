"""Fournisseurs et modèles : vérification au démarrage, erreur en cours de
session, choix du modèle au lancement et en session.

Spec 001 §4.5, CA-20 à CA-24 ; ADR-0003, ADR-0008 §5-6.
CA-20 et CA-21 exercent le vrai `LiteLLMClient` sans réseau ni appel facturé
(ADR-0003 §Conséquences : un modèle simulé ne valide jamais un contrat externe) :
variable de clé retirée, serveur sur un port local fermé.
"""

import socket

import pytest
from support import Console, ScriptedModel, make_config, run_repl, say

from harness.cli import repl
from harness.config import ModelProfile
from harness.models.base import ProviderError


async def _start_with_real_client(console: Console, profile: ModelProfile) -> None:
    """Démarre le REPL avec le vrai adaptateur LiteLLM ; « aucune session ne
    s'ouvre » peut se traduire par un retour ou par SystemExit."""
    import asyncio

    from harness.models.litellm_client import LiteLLMClient

    config = make_config(models={"cible": profile}, default="cible")
    try:
        await asyncio.wait_for(
            repl.run(config, LiteLLMClient, console.read_line, console.write), 20
        )
    except SystemExit:
        pass


async def test_startup_with_missing_api_key_names_the_key_and_opens_no_session(
    monkeypatch,
):
    """CA-20 : clé absente → message qui nomme la variable ; aucune invite."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    console = Console("ne doit jamais être lu")

    await _start_with_real_client(
        console, ModelProfile(model="anthropic/claude-sonnet-5-5")
    )

    assert "ANTHROPIC_API_KEY" in console.text
    assert console.reads == [], "une session s'est ouverte malgré la clé absente"


async def test_startup_with_unreachable_openai_compatible_server_names_it_and_opens_no_session():
    """CA-21 : serveur compatible OpenAI injoignable → message qui nomme le
    serveur ; aucune invite."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # port fermé dès la sortie du bloc
    console = Console("ne doit jamais être lu")

    await _start_with_real_client(
        console,
        ModelProfile(
            model="openai/modele-local",
            api_base=f"http://127.0.0.1:{port}/v1",
            request_timeout_s=3,
        ),
    )

    assert f"127.0.0.1:{port}" in console.text
    assert console.reads == [], (
        "une session s'est ouverte malgré le serveur injoignable"
    )


async def test_provider_unreachable_mid_session_shows_message_keeps_conversation_and_retries(
    workdir,
):
    """CA-22 : message clair ; conversation conservée ; le message suivant réessaie."""
    model = ScriptedModel(
        [
            say("bonjour à toi"),
            ProviderError("unreachable", "Fournisseur injoignable (cause de test)."),
            say("je reprends"),
        ]
    )
    console = Console("bonjour", "demande B", "demande B, nouvel essai")

    await run_repl(console, make_config(), {"scripted": model}, workdir)

    assert "Fournisseur injoignable (cause de test)." in console.shown_before_read(2)
    assert len(model.calls) == 3
    assert model.saw_text("bonjour à toi", 2)
    assert model.saw_text("demande B, nouvel essai", 2)
    assert len(console.reads) == 4, "la session ne doit pas se fermer sur l'erreur"


def _two_models_config():
    return make_config(
        models={
            "principal": ModelProfile(model="openai/principal"),
            "secondaire": ModelProfile(model="openai/secondaire"),
        },
        default="principal",
    )


@pytest.mark.parametrize(
    ("override", "expected"),
    [(None, "principal"), ("secondaire", "secondaire")],
    ids=["config", "option-de-lancement"],
)
async def test_launch_option_overrides_the_configured_model(
    workdir, override, expected
):
    """CA-23 : l'option de lancement remplace le modèle de la configuration ;
    sans elle, le modèle de la configuration est utilisé."""
    models = {
        "principal": ScriptedModel([say("p")]),
        "secondaire": ScriptedModel([say("s")]),
    }

    await run_repl(
        Console("bonjour"),
        _two_models_config(),
        models,
        workdir,
        model_override=override,
    )

    assert models[expected].saw_text("bonjour", 0)
    other = next(alias for alias in models if alias != expected)
    assert models[other].calls == []


async def test_model_command_switches_the_active_model_and_keeps_history(workdir):
    """CA-24 (succès) : `/model <alias>` bascule ; les tours suivants l'utilisent ;
    l'historique est conservé."""
    models = {
        "principal": ScriptedModel([say("réponse du principal")]),
        "secondaire": ScriptedModel([say("réponse du secondaire")]),
    }
    console = Console("premier", "/model secondaire", "second")

    await run_repl(console, _two_models_config(), models, workdir)

    assert len(models["principal"].calls) == 1
    assert len(models["secondaire"].calls) == 1
    assert models["secondaire"].saw_text("premier", 0)
    assert models["secondaire"].saw_text("réponse du principal", 0)
    assert models["secondaire"].saw_text("second", 0)


async def test_failed_model_switch_shows_a_message_and_keeps_the_previous_model(
    workdir,
):
    """CA-24 (échec) : vérification du nouveau modèle en échec, ou alias inconnu
    → message clair, l'ancien modèle reste actif. Test distinct du succès :
    le risque (perdre le modèle actif sur un échec) est différent."""
    config = make_config(
        models={
            "principal": ModelProfile(model="openai/principal"),
            "casse": ModelProfile(model="openai/casse"),
        },
        default="principal",
    )
    models = {
        "principal": ScriptedModel([say("toujours le principal")]),
        "casse": ScriptedModel(
            check_error=ProviderError(
                "auth", "Clé CLE_DE_TEST_ABSENTE manquante (test)."
            )
        ),
    }
    console = Console("/model casse", "/model fantome", "bonjour")

    await run_repl(console, config, models, workdir)

    assert "CLE_DE_TEST_ABSENTE" in console.shown_before_read(1)
    assert "fantome" in console.shown_before_read(2)
    assert models["principal"].saw_text("bonjour", 0)
    assert models["casse"].calls == []
