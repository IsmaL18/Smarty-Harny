"""Adaptateur LiteLLM : seul module qui importe `litellm` (ADR-0003, ADR-0004).

Notion : abstraction-multi-provider. Il traduit les exceptions du fournisseur en
`ProviderError` (messages en français) et calcule le coût, `None` si le prix est inconnu.
"""

import asyncio
import os
import urllib.error
import urllib.request
from typing import Any

import litellm
from litellm import exceptions as llm_errors

from harness.config import ModelProfile
from harness.models.base import ModelResponse, ProviderError

# Variable de clé par défaut selon le préfixe LiteLLM (hors serveur à `api_base`).
_DEFAULT_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
_CHECK_TIMEOUT_S = 5.0
# Serveur local sans clé (mlx_lm.server, Ollama) : le client OpenAI sous LiteLLM exige une
# valeur non vide, que le serveur ignore.
_NO_KEY_PLACEHOLDER = "sk-no-key-required"

litellm.suppress_debug_info = (
    True  # pas de bandeau « Give Feedback / Debug » sur les erreurs
)


class LiteLLMClient:
    def __init__(self, profile: ModelProfile):
        self._profile = profile

    def _key_env(self) -> str | None:
        if self._profile.api_key_env:
            return self._profile.api_key_env
        if self._profile.api_base:
            return None
        return _DEFAULT_KEY_ENV.get(self._profile.model.split("/", 1)[0])

    async def check(self) -> None:
        """Vérifie clé et joignabilité sans appel facturé (ADR-0003 §4)."""
        key_env = self._key_env()
        if key_env and not os.environ.get(key_env):
            raise ProviderError(
                "auth",
                f"La clé API {key_env} est absente de l'environnement. "
                f"Exportez-la (export {key_env}=...) puis relancez le harness.",
            )
        base = self._profile.api_base
        if base:
            url = base.rstrip("/") + "/models"
            try:
                await asyncio.to_thread(
                    urllib.request.urlopen, url, timeout=_CHECK_TIMEOUT_S
                )
            except urllib.error.HTTPError:
                pass  # le serveur répond : il est joignable
            except (urllib.error.URLError, OSError) as exc:
                cause = getattr(exc, "reason", exc)
                raise ProviderError(
                    "unreachable",
                    f"Le serveur {base} est injoignable ({cause}). "
                    f"Vérifiez qu'il est lancé et que l'adresse de la configuration est correcte.",
                ) from exc

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelResponse:
        profile = self._profile
        key_env = self._key_env()
        try:
            response: Any = await litellm.acompletion(
                model=profile.model,
                messages=messages,
                tools=tools,
                api_base=profile.api_base,
                api_key=(os.environ.get(key_env) if key_env else None)
                or (_NO_KEY_PLACEHOLDER if profile.api_base else None),
                max_tokens=profile.max_output_tokens,
                timeout=profile.request_timeout_s,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # traduit toute erreur du fournisseur
            raise _translate(exc) from exc

        try:
            choice = response.choices[0]
            message: dict = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in choice.message.tool_calls
                ]
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderError(
                "other", f"Réponse du fournisseur illisible ({type(exc).__name__})."
            ) from exc
        return ModelResponse(
            message, choice.finish_reason or "stop", usage, self._cost(response, usage)
        )

    def _cost(self, response, usage: dict) -> float | None:
        profile = self._profile
        if profile.api_base:
            # Même nom qu'un modèle payant connu de LiteLLM : on ne devine pas (ADR-0004 §2).
            if (
                profile.input_price_per_mtok is None
                or profile.output_price_per_mtok is None
            ):
                return None
            return (
                usage["prompt_tokens"] * profile.input_price_per_mtok
                + usage["completion_tokens"] * profile.output_price_per_mtok
            ) / 1_000_000
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:  # noqa: BLE001 - prix inconnu : None, jamais 0
            return None
        return float(cost) if cost else None


def _translate(exc: Exception) -> ProviderError:
    if isinstance(exc, llm_errors.ContextWindowExceededError):
        return ProviderError(
            "context_too_long",
            "La conversation dépasse la fenêtre de contexte du modèle (pas de compaction en v0). "
            "Quittez la session et recommencez.",
        )
    if isinstance(exc, llm_errors.AuthenticationError):
        return ProviderError("auth", f"Le fournisseur refuse la clé API : {exc}")
    # LiteLLM enveloppe parfois un « connection refused » en InternalServerError.
    wrapped_connection = (
        isinstance(exc, llm_errors.InternalServerError)
        and "connection error" in str(exc).lower()
    )
    if wrapped_connection or isinstance(
        exc,
        (
            llm_errors.APIConnectionError,
            llm_errors.Timeout,
            llm_errors.ServiceUnavailableError,
        ),
    ):
        return ProviderError(
            "unreachable",
            f"Fournisseur injoignable ou trop lent : {type(exc).__name__}.",
        )
    return ProviderError(
        "other", f"Erreur du fournisseur ({type(exc).__name__}) : {exc}"
    )
