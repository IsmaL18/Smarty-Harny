# ADR-0004 — Comptage du coût, prix inconnu compris

Statut : proposé · Spec : §4.3, §4.4, §6, CA-14, CA-17 · Question ouverte n°4 de la spec (tranchée ici)

## Contexte

Le coût cumulé est affiché et borne la session (budget). Il se cumule sur tous les tours et tous les modèles. Un modèle local, ou un serveur compatible OpenAI, n'a pas de prix connu : le coût ne doit jamais s'afficher comme 0 de façon trompeuse et ne doit pas consommer le budget.

## Décision

1. **Mesure par appel**, dans `LiteLLMClient` : `usage` (tokens entrée/sortie) toujours relevé ; `cost_usd` = `litellm.completion_cost(...)` si le prix est connu, sinon **`None`** (jamais 0). Toute exception de calcul de prix → `None`.
2. **Profil avec `api_base`** : coût `None` par défaut, **même si LiteLLM connaît un modèle de même nom** (un modèle local nommé comme un modèle payant serait mal facturé). Un profil peut déclarer ses prix (`input_price_per_mtok`, `output_price_per_mtok`, en USD) : le coût est alors calculé à partir des tokens. C'est le seul moyen de budgéter un serveur compatible OpenAI payant.
3. **`CostTracker`** (noyau, par session) : cumule `known_usd`, `unknown_calls`, `tokens` ; survit au changement de modèle.
4. **Budget** : ne compte que `known_usd` (ADR-0001 §5). Si tous les appels sont non estimés, le budget ne se déclenche jamais ; l'affichage le dit.
5. **Affichage** (en dollars, 4 décimales) :
   - tout connu : `coût : 0,0123 $` ;
   - mixte : `coût : 0,0123 $ + 2 appels non estimés` ;
   - rien de connu : `coût : non estimé (3 appels, 12 345 tokens)`.
   Visible à la fin de chaque tour (CA-14), à la sortie, et le budget restant au démarrage.

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. LiteLLM + `None` si inconnu + prix déclaratifs pour `api_base`** (retenue) | honnête, pas de faux 0, budget sûr pour les serveurs payants | un champ de config de plus |
| B. Table de prix maison | indépendante de LiteLLM | à maintenir ; contredit « périphérique par bibliothèque » |
| C. Coût inconnu = 0 | trivial | trompeur (interdit par la spec) |
| D. Budget aussi en tokens | borne même sans prix | deux unités de budget ; non demandé |

## Conséquences

- Un budget peut être contourné sans le savoir avec un serveur payant sans prix déclaré : le message de démarrage l'indique (« coût non estimé pour ce modèle, le budget ne s'applique pas »).
- La précision des prix dépend de la version de LiteLLM figée dans `uv.lock` ; le coût est une estimation.
- Dépassement du budget d'au plus un appel (ADR-0001).
- **Non vérifié** : que `completion_cost` lève bien une exception, plutôt que de renvoyer 0, pour un modèle inconnu avec `api_base` ; la règle n°2 rend la question sans effet pour les profils `api_base`, mais à confirmer pour un identifiant Anthropic récent absent de la table de prix.
