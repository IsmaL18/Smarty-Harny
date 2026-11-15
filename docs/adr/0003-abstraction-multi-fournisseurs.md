# ADR-0003 — Abstraction multi-fournisseurs et changement de modèle

Statut : proposé · Spec : §4.5, CA-20 à CA-24 · Notion : `abstraction-multi-provider` (approfondie à l'it. 7)

## Contexte

Anthropic, tout serveur compatible OpenAI (dont `mlx_lm.server`, Ollama), changement de modèle en session. CLAUDE.md impose LiteLLM pour les appels. Il faut aussi pouvoir tester la boucle avec un modèle simulé, et valider au démarrage la clé et la joignabilité.

## Décision

1. **Deux niveaux** :
   - un **protocole `ModelClient`** défini par le noyau : `async complete(messages, tools) -> ModelResponse` et `async check() -> None` (lève `ProviderError`) ;
   - une **implémentation `LiteLLMClient`** (seule à importer `litellm`) qui appelle `litellm.acompletion` en mode non streamé.
   `ModelResponse` = `message` (dict OpenAI), `finish_reason`, `usage` (tokens), `cost_usd: float | None` (ADR-0004). Un modèle simulé de test implémente ce protocole : c'est le point d'injection de la spec §5.
2. **Profils de modèle nommés** dans la configuration (ADR-0007) : `[models.<alias>]` avec `model` (identifiant LiteLLM : `anthropic/...`, `openai/...`), `api_base` optionnel (serveur compatible OpenAI), `api_key_env` optionnel (défaut : `ANTHROPIC_API_KEY` pour `anthropic/`, aucune clé pour un `api_base`), `max_output_tokens`, `request_timeout_s`. L'adresse du serveur vit donc dans le profil, pas dans une option séparée.
3. **Sélection** : `default_model = "<alias>"` dans la config ; `--model <alias>` au lancement (CA-23) ; `/model <alias>` en session (CA-24). On ne désigne que des alias (pas d'identifiant LiteLLM brut) : une seule source de vérité, un alias inconnu est détecté avant tout appel.
4. **Vérification (`check`) au démarrage et au changement de modèle**, sans appel facturé :
   - clé requise absente de l'environnement → erreur nommant la variable et la correction (CA-20) ;
   - profil avec `api_base` : `GET {api_base}/models` avec un court délai ; échec de connexion → erreur nommant le serveur et la cause (CA-21).
   - un identifiant de modèle Anthropic faux n'est détecté qu'au premier appel (erreur fournisseur affichée, conversation conservée) : accepté pour éviter un appel facturé.
   Au démarrage, échec = pas de session. Au `/model`, échec = message et **l'ancien client reste actif** : le nouveau client n'est installé qu'après `check` réussi.
5. **Erreurs d'appel** : `LiteLLMClient` traduit les exceptions LiteLLM en `ProviderError(kind, message_fr)` avec `kind ∈ {auth, unreachable, context_too_long, other}` (les noms exacts des exceptions LiteLLM sont à confirmer à l'implémentation). Pas de retry en v0 (it. 7) : l'utilisateur renvoie sa demande (ADR-0001 §7).
6. **Historique indépendant du fournisseur** : format OpenAI chat, converti par LiteLLM. Le changement de modèle conserve donc l'historique tel quel (CA-24) et le coût cumulé (ADR-0004).

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. Protocole maison + adaptateur LiteLLM + profils nommés** (retenue) | noyau sans dépendance fournisseur, modèle simulé trivial, changement de modèle = changer d'objet | une couche de plus |
| B. Appeler `litellm` directement dans la boucle | moins de code | boucle couplée à la lib ; tests par patch ; fuite d'exceptions fournisseur |
| C. Un SDK par fournisseur, conversion maison | contrôle total | contredit CLAUDE.md, beaucoup de code périphérique |
| D. Identifiants LiteLLM bruts à la place des alias | zéro config de profils | `api_base` à passer à part ; pas de défaut par modèle ; erreurs de frappe tardives |

## Conséquences

- Un test de l'adaptateur doit exercer la **vraie** validation du client (construction de la requête, traduction d'erreurs) sans réseau — p. ex. `mock_response` de LiteLLM, un port local fermé pour CA-21, la variable de clé retirée pour CA-20 — car un modèle simulé ne valide jamais un contrat externe.
- **Non vérifié** : le comportement de LiteLLM/Anthropic avec deux messages `user` consécutifs (ADR-0005) et avec un historique produit par un autre fournisseur. À valider lors de la session réelle (preuve humaine).
- **Non vérifié** : le joignable-depuis-le-conteneur de `mlx_lm.server` (adresse `host.docker.internal`, écoute sur `0.0.0.0`) — voir ADR-0006.
- Pas de table de capacités par modèle ni de `cache_control` en v0.
