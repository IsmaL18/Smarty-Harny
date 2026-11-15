# ADR-0005 — Interruption (Ctrl+C) et délai maximal des commandes

Statut : proposé ; §2 et §3 amendés après revue, amendement validé par l'utilisateur le 2026-11-15 · Spec : §4.1, §4.2, §6, CA-11, CA-18, CA-19 · Notion : `boucle-agent` (interruption propre approfondie à l'it. 7)

## Contexte

Ctrl+C pendant un tour doit tuer la commande en cours (ou abandonner l'appel au modèle), informer le modèle, garder la session ouverte et rendre l'invite. Ctrl+C à l'invite ne quitte pas. Une commande qui ne termine pas est arrêtée au délai maximal et le modèle reçoit la sortie partielle.

## Décision

1. **Annulation de tâche `asyncio`.** Pendant un tour, l'interface exécute le tour dans une tâche et installe `loop.add_signal_handler(SIGINT, task.cancel)` ; le gestionnaire est retiré à la fin du tour. À l'invite, `input()` reçoit `KeyboardInterrupt` : l'interface affiche une nouvelle ligne et réaffiche l'invite (CA-19). Ctrl+D (`EOFError`) à l'invite quitte (CA-3).
2. **Le noyau absorbe l'annulation au niveau du tour.** `run_turn` capte `CancelledError`, ferme l'historique de façon valide, émet `TurnEnded(interrupted)` et rend normalement. Il n'appelle **pas** `uncancel()` : le compteur d'annulation reste visible de l'appelant, de sorte qu'une annulation externe (`asyncio.timeout`, `TaskGroup`) n'est pas avalée silencieusement (amendé après revue) :
   - interruption pendant un outil : son résultat est `[INTERRUPTED by user]` ; les appels du même message non encore exécutés reçoivent `[NOT RUN: turn interrupted by user]` ; le modèle voit donc l'interruption au tour suivant (CA-18) ;
   - interruption pendant l'appel au modèle : aucun message assistant n'existe ; le noyau ajoute un message `user` : `[The user interrupted the previous request before you answered.]` (le message utilisateur d'origine est conservé : l'interruption est volontaire, contrairement à une erreur du fournisseur, ADR-0001 §7).
3. **Délai des commandes** : `command_timeout_s` (config, ADR-0007) appliqué par `LocalEnvironment.run`. Les commandes sont lancées dans un **nouveau groupe de processus** (`start_new_session=True`) ; au délai **comme** à l'annulation, le groupe entier est tué (`SIGKILL` sur le groupe : pas de petits-enfants orphelins gardant le tube ouvert), puis, **au délai seulement**, la sortie déjà lue est renvoyée avec `[TIMEOUT: killed after Ns]` (ADR-0002, CA-11). **À l'interruption**, le résultat est `[INTERRUPTED by user]` sans sortie partielle : la spec (CA-18) n'exige que d'informer le modèle (amendé après revue ; la sortie partielle à l'interruption est une idée de réserve).
4. **Appel au modèle** : annulable car non streamé ; en plus, un délai `request_timeout_s` par profil évite l'attente infinie (défaut 300 s : un modèle local lent doit pouvoir répondre). Dépassement = `ProviderError(unreachable)`.
5. **Ctrl+C pendant « continuer ? »** vaut « non ». Un second Ctrl+C rapide n'a pas de sens particulier en v0 (pas d'arrêt forcé).

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. Annulation de tâche + gestionnaire de signal + kill du groupe** (retenue) | traverse proprement attente modèle et sous-processus ; cohérent avec ADR-0001 | `CancelledError` à manipuler avec soin (ne pas l'avaler ailleurs qu'au tour) |
| B. `KeyboardInterrupt` standard dans `asyncio.run` | zéro installation de gestionnaire | arrêt de la boucle d'événements, état difficile à restaurer, session perdue |
| C. Boucle en thread séparé + drapeau d'arrêt | contrôle fin | complexité de threads que la veille déconseille (Hermes) |

## Conséquences

- Les tests d'interruption envoient un vrai `SIGINT` au processus de test (déclenché par un minuteur) pendant une commande longue ; Ctrl+C à l'invite se simule par une fonction de lecture qui lève `KeyboardInterrupt`.
- Le noyau ne tue qu'un groupe de processus ; sous Docker, c'est suffisant car tout vit dans le conteneur. Une commande qui se détache délibérément (`setsid`, démon) peut survivre au kill : accepté.
- L'interruption laisse les effets déjà produits (fichiers écrits) : pas de retour arrière (réserve d'idées).
- **Non vérifié** : le comportement de `uncancel()` et de l'état de la tâche sous Python 3.12 selon que l'annulation survient dans `await` du modèle ou du sous-processus ; à couvrir par les tests d'interruption.
