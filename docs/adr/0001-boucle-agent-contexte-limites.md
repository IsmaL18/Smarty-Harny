# ADR-0001 — Boucle agent, contexte conversationnel et limites

Statut : proposé (à valider par l'utilisateur) ; §7 complété par ADR-0012 (retrait journalisé comme nouveau point de départ) · Spec : `specs/001-v0-boucle-agent.md` · Notion : `boucle-agent`

## Contexte

La v0 doit enchaîner des actions jusqu'à une réponse, s'arrêter à des limites (étapes par tour, budget de session), demander « continuer ? », survivre aux erreurs et à Ctrl+C. Les trajectoires prévues (headless, TUI, API serveur) exigent un noyau sans E/S terminal. La synthèse de veille (§1, §5) fixe : boucle simple, événements typés, historique en ajout seul.

## Décision

1. **Boucle `asyncio`**, écrite à la main. Un tour = `Session.run_turn(texte)`, un *générateur asynchrone d'événements typés* (`events.py`). Le noyau n'écrit jamais dans le terminal et ne pose aucune question.
2. **Algorithme d'un tour** : ajouter le message utilisateur ; puis répéter : vérifier les limites → appeler le modèle → ajouter sa réponse → si elle contient des appels d'outils, les exécuter **séquentiellement** (un résultat par appel, toujours) et recommencer ; sinon fin du tour. Le tour se termine par un `TurnEnded(reason)` où `reason ∈ {done, step_limit, budget_limit, interrupted, provider_error}`.
3. **Historique** : liste de messages au format OpenAI chat (format canonique de LiteLLM), propriété de `Session`, **en ajout seul**. Le message `system` (prompt court en sections nommées, `prompt.py`) est le premier et ne change jamais, y compris au changement de modèle. Les messages assistant sont réduits à `role`, `content`, `tool_calls` (pas de champs propres à un fournisseur : prépare l'it. 7). Pas de compaction (hors périmètre).
4. **Étape** = un appel au modèle, qu'il demande des outils ou non (confirme l'hypothèse de la spec §7 / question 2 : limite **par tour**, remise à zéro à chaque message utilisateur).
5. **Limites vérifiées avant chaque appel au modèle** (jamais après) :
   - étapes du tour ≥ allocation d'étapes → `LimitReached(step)` puis `TurnEnded(step_limit)` ;
   - coût connu cumulé ≥ plafond de budget → `LimitReached(budget)` puis `TurnEnded(budget_limit)`. Aucun appel n'est fait. L'appel qui franchit le plafond va jusqu'au bout (dépassement possible d'un appel, accepté).
   Le message de limite est construit par le harness : limite atteinte, nombre d'étapes faites, liste des dernières actions.
6. **« Continuer ? »** est posé par l'interface, pas par le noyau : après `TurnEnded(step_limit|budget_limit)`, l'interface appelle `Session.resume_turn(grant=True)`. Le noyau ajoute une tranche identique (étapes : `+max_steps_per_turn` ; budget : `+budget_usd` initial) puis reprend avec l'historique tel quel (il se termine par des résultats d'outils, état valide). « Non » : l'interface ne fait rien, la session reste ouverte. Ctrl+C ou Ctrl+D à la question valent « non » ; toute autre réponse que oui/non repose la question.
7. **Erreur du fournisseur** (voir ADR-0003) : `ProviderFailed` puis `TurnEnded(provider_error)`. Si l'échec survient au **premier appel du tour**, le message utilisateur non répondu est **retiré** de l'historique (seule exception à « ajout seul », en queue, sans effet sur le préfixe) et l'interface invite à renvoyer la demande. Si l'échec survient en milieu de tour, l'historique est conservé tel quel (les actions ont eu lieu) ; le message suivant de l'utilisateur continue la conversation.
8. **Interruption** : voir ADR-0005 (le noyau ferme proprement les appels d'outils ouverts).

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. `asyncio` + générateur d'événements** (retenue) | interruption par annulation de tâche, timeouts natifs, même flux pour CLI/TUI/API, tests simples (`async for`) | marche d'apprentissage `async` |
| B. Synchrone + callbacks | plus simple à lire | interruption/timeout par signaux et threads (le piège de Hermes) ; réécriture avant la TUI/API |
| C. Synchrone + générateur | lisible | même problème d'interruption ; appels bloquants |

Pour la forme de la sortie : un générateur (A) plutôt que des callbacks `on_event` — le consommateur garde le contrôle du rythme et le noyau reste sans E/S.

## Justification

Le coût principal de A est pédagogique, et c'est exactement la notion à apprendre ; B/C coûteraient une réécriture à l'itération 7 (interruption propre). La limite avant appel garantit CA-17 sans état intermédiaire. Laisser l'interface poser « continuer ? » garde le noyau pur et testable : un test pilote `run_turn` puis `resume_turn`.

## Conséquences

- Défauts tranchés (spec §9 q.1) : voir ADR-0007 (`max_steps_per_turn = 25`, `budget_usd = 1.00`).
- Pas de streaming des réponses en v0 (appel non streamé, plus simple ; l'utilisateur ne voit rien pendant l'appel). Revoir avec la TUI.
- Après une erreur « contexte trop grand » (pas de compaction), chaque nouvelle demande échouera : l'utilisateur doit quitter. Accepté en v0 ; message explicite.
- Outils exécutés séquentiellement ; le parallélisme est l'it. 7.
- L'invariant « historique valide » (chaque `tool_call` a exactement un résultat) est de la responsabilité du noyau, y compris en cas d'interruption.
