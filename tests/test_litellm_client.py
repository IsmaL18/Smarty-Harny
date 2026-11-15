"""Le vrai `LiteLLMClient.complete()` contre un faux serveur HTTP local compatible OpenAI.

ADR-0003 §5 et §Conséquences, ADR-0004 §1-2 : un modèle simulé ne valide jamais
un contrat externe. Ici la vraie bibliothèque LiteLLM construit la requête, parle
HTTP à un serveur local (aucun réseau externe, aucun appel facturé) et traduit la
réponse ou l'erreur.
"""

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.config import ModelProfile
from harness.models.base import ProviderError
from harness.models.litellm_client import LiteLLMClient


class FakeOpenAIServer:
    """Serveur `/v1/chat/completions` minimal : enregistre les requêtes reçues et
    rend la réponse (statut, corps JSON) prévue par le test."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.status = 200
        self.body: dict = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append(json.loads(self.rfile.read(length) or b"{}"))
                payload = json.dumps(outer.body).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def answer(self, message: dict, finish_reason: str = "stop", **usage) -> None:
        self.status = 200
        self.body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "modele-local",
            "choices": [
                {"index": 0, "message": message, "finish_reason": finish_reason}
            ],
            "usage": {
                "prompt_tokens": usage.get("prompt", 1_000_000),
                "completion_tokens": usage.get("completion", 500_000),
                "total_tokens": 0,
            },
        }

    def fail(self, status: int, message: str, code: str | None = None) -> None:
        self.status = status
        self.body = {"error": {"message": message, "type": "error", "code": code}}


@pytest.fixture
def server():
    fake = FakeOpenAIServer()
    yield fake
    fake.close()


def _profile(server: FakeOpenAIServer, **overrides) -> ModelProfile:
    return ModelProfile(
        model="openai/modele-local",
        api_base=server.url,
        request_timeout_s=10,
        **overrides,
    )


_MESSAGES = [
    {"role": "system", "content": "tu es un agent"},
    {"role": "user", "content": "bonjour"},
]
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "lit un fichier",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]


async def test_profile_with_api_base_and_no_key_completes_and_sends_a_well_formed_request(
    server,
):
    """Profil `api_base` sans clé (serveur local) : l'appel aboutit ; la requête
    porte le modèle sans préfixe, les messages, les outils et `max_output_tokens`."""
    server.answer({"role": "assistant", "content": "salut"})
    client = LiteLLMClient(_profile(server, max_output_tokens=777))

    response = await client.complete(_MESSAGES, _TOOLS)

    assert response.message["content"] == "salut"
    assert response.finish_reason == "stop"
    assert response.usage["prompt_tokens"] == 1_000_000
    assert response.usage["completion_tokens"] == 500_000
    (request,) = server.requests
    assert request["model"] == "modele-local"
    assert request["messages"] == _MESSAGES
    assert request["tools"] == _TOOLS
    assert request["max_tokens"] == 777


async def test_tool_calls_in_the_response_are_translated_to_openai_chat_format(server):
    """La réponse avec `tool_calls` rend un message assistant au format OpenAI
    (id, nom, arguments JSON) et `finish_reason = tool_calls`."""
    server.answer(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "a.txt"}),
                    },
                }
            ],
        },
        finish_reason="tool_calls",
    )

    response = await LiteLLMClient(_profile(server)).complete(_MESSAGES, _TOOLS)

    assert response.finish_reason == "tool_calls"
    (tool_call,) = response.message["tool_calls"]
    assert tool_call["id"] == "call_abc"
    assert tool_call["function"]["name"] == "read_file"
    assert json.loads(tool_call["function"]["arguments"]) == {"path": "a.txt"}


async def test_cost_is_computed_from_declared_prices_and_none_when_prices_are_absent(
    server,
):
    """ADR-0004 §1-2 : avec `api_base` et prix déclarés, coût = tokens × prix ;
    sans prix, `None` (jamais 0), même si le nom du modèle existe dans LiteLLM."""
    server.answer({"role": "assistant", "content": "ok"})  # 1 M entrée, 0,5 M sortie

    priced = _profile(server, input_price_per_mtok=3.0, output_price_per_mtok=15.0)
    free = ModelProfile(
        model="openai/gpt-4o", api_base=server.url, request_timeout_s=10
    )

    with_prices = await LiteLLMClient(priced).complete(_MESSAGES, [])
    without_prices = await LiteLLMClient(free).complete(_MESSAGES, [])

    assert with_prices.cost_usd == pytest.approx(3.0 + 7.5)
    assert without_prices.cost_usd is None


async def test_zero_declared_prices_give_a_known_zero_cost(server):
    """Prix déclarés à 0 (serveur gratuit mais budgété) : coût connu 0, pas `None`."""
    server.answer({"role": "assistant", "content": "ok"})
    profile = _profile(server, input_price_per_mtok=0, output_price_per_mtok=0)

    response = await LiteLLMClient(profile).complete(_MESSAGES, [])

    assert response.cost_usd == 0


@pytest.mark.parametrize(
    ("status", "message", "code", "kind"),
    [
        (401, "clé invalide", "invalid_api_key", "auth"),
        (
            400,
            ("This model's maximum context length is 10 tokens. Reduce the messages."),
            "context_length_exceeded",
            "context_too_long",
        ),
        (500, "panne interne", None, "other"),
    ],
    ids=["auth", "context_too_long", "other"],
)
async def test_http_errors_are_translated_to_provider_error_with_the_right_kind(
    server, status, message, code, kind
):
    """ADR-0003 §5 : les erreurs HTTP du fournisseur sortent en `ProviderError`
    typée, avec un message en français non vide ; aucune exception LiteLLM ne fuit."""
    server.fail(status, message, code)

    with pytest.raises(ProviderError) as raised:
        await LiteLLMClient(_profile(server)).complete(_MESSAGES, [])

    assert raised.value.kind == kind
    assert raised.value.message_fr.strip()


async def test_unreachable_server_is_translated_to_provider_error_unreachable():
    """Serveur injoignable pendant un appel (port fermé) → `kind = unreachable`."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    client = LiteLLMClient(
        ModelProfile(
            model="openai/modele-local",
            api_base=f"http://127.0.0.1:{port}/v1",
            request_timeout_s=3,
        )
    )

    with pytest.raises(ProviderError) as raised:
        await asyncio.wait_for(client.complete(_MESSAGES, []), 30)

    assert raised.value.kind == "unreachable"
