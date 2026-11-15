# Journal 001 — v0 : la boucle agent

Branche `feat/it1-v0-boucle-agent`, commit `33d6f15`. Fiche de notion associée : [`docs/notions/boucle-agent.md`](../notions/boucle-agent.md) (générique, sans référence au projet). Spec : `specs/001-v0-boucle-agent.md`. ADR : `docs/adr/0001` à `0008`. Tests : `TESTS.md` (T-0001 à T-0039).

## Ce qui a été construit

Un REPL dans le terminal, une boucle `asyncio` à événements typés (`Session.run_turn`), trois outils (`read_file`, `write_file`, `shell`), un adaptateur LiteLLM (Anthropic et serveurs compatibles OpenAI), des limites (25 étapes par tour, budget 1 $) avec « continuer ? », Ctrl+C, une configuration TOML et un lanceur Docker (`bin/harness`). Vérifié contre un modèle local (`mlx_lm.server`, LFM2.5-24B) par l'utilisateur : le tour complet avec appels `shell` fonctionne.

## Décisions et leurs raisons

- **Noyau sans E/S** (ADR-0001, ADR-0008) : le tour est un générateur d'événements ; « continuer ? » est posé par le REPL via `resume_turn`. Prépare TUI et API.
- **Séquentiel** pour les outils : un résultat par appel garanti plus simple à prouver ; parallélisme repoussé (modèle Codex à étudier).
- **Sortie partielle** (ADR-0005 §3, amendé et validé le 2026-11-15) : rendue au timeout seulement (CA-11) ; à l'interruption, seulement `[INTERRUPTED by user]` (CA-18 exige d'informer, pas de rendre la sortie).
- **Pas de `uncancel()`** (ADR-0005 §2, amendé) : voir pièges.
- **Réponse du modèle jamais tronquée** (CA-12 amendé, T-0039) : décidé après usage réel ; seuls les événements d'outils restent en lignes-titres.
- **Coût inconnu ≠ 0** (ADR-0004) : profil `api_base` sans prix ⇒ « coût non estimé », budget inactif. Prix à 0.0 acceptés pour un serveur local gratuit.

## Pièges rencontrés

| Piège | Découvert par | Correctif / test |
|---|---|---|
| Profil `api_base` sans clé ⇒ « Missing credentials » à chaque appel | revue (bloquant) ; le vrai `complete()` n'avait jamais été exercé | clé factice ; T-0027 (faux serveur HTTP local) |
| `uncancel()` inconditionnel avalait `asyncio.timeout` | revue | suppression ; T-0038 |
| Connexion refusée enveloppée par LiteLLM en `InternalServerError` ⇒ classée « other » | T-0032 (test-writer) | reclassement en « unreachable » (détection sur le texte du message, fragile) |
| Exception inattendue du client ⇒ plantage du REPL | revue | capture à la frontière de la boucle ; T-0036 |
| Prix et `max_output_tokens` non validés | revue | T-0033, T-0034 |
| `OPENAI_API_KEY` non transmise par `bin/harness` | revue | variable ajoutée (pas de test : le lanceur n'est pas couvert) |
| Réponse affichée tronquée à sa première ligne | usage réel | CA-12 amendé ; T-0039 |

## Process : ce que l'itération a montré

- La séparation test-writer a trouvé un vrai défaut de production (T-0032) que l'implémentation seule n'aurait pas vu.
- Un mock ne valide pas un contrat externe : le bloquant de la revue venait d'un chemin jamais exécuté pour de vrai.
- Les mineurs cités par numéro de ligne (`repl.py:161`, `session.py:101`, `environment.py:75`) n'ont pas pu être identifiés après modifications : citer le symbole plutôt que la ligne.

## Grill de fin d'itération (2026-11-15)

Huit questions à choix : 7 justes sur 8. Lacune : la raison de vérifier les limites **avant** l'appel au modèle (on ne paie pas un appel qu'on ne veut plus ; un appel parti ne s'annule pas sans être facturé). Acquis : invariant « un résultat par appel », `finish_reason=length` ⇒ ne pas exécuter, le harness exécute et le modèle ne fait que demander, erreurs d'arguments renvoyées au modèle, prompt système stable (cache + cohérence), frontière du conteneur (fichiers hôte oui, clé API non), kill du groupe de processus. Le grill n'a pas couvert retries, parallélisme, streaming ni compaction (hors v0).

## Non vérifié

- `bin/harness` n'a pas de test automatisé ; CA-25 validé à la main par l'utilisateur sur un modèle local, pas sur Anthropic.
- Détection « connection error » par texte : peut casser à une mise à jour de LiteLLM.
- T-0038 dépend de la sémantique d'`asyncio` en Python 3.12.
- Le profil sans clé n'a été vu fonctionner que sur `mlx_lm.server`, pas sur Ollama.
- Fiches `tool-calling`, `prompt-systeme`, `conteneur-frontiere` (notions de la feuille de route pour l'itération 1) pas encore écrites ; `boucle-agent` n'en couvre qu'une.

## Suite

Itération 2 (feuille de route) : conception des outils, édition de fichiers, troncature des sorties. Piste à reprendre : sortie partielle à l'interruption, sur une idée de réserve.
