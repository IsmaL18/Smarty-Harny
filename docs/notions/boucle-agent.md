---
title: "Boucle agent (agent loop)"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: concept
date: 2026-11-15
---

## Définition exacte & périmètre

La boucle agent est le code qui entoure un LLM pour transformer ses messages en actions : appeler le modèle, exécuter les outils qu'il demande, lui renvoyer les résultats, recommencer jusqu'à une réponse sans demande d'outil. Le modèle ne fait que produire du texte structuré. Il émet une demande d'outil (nom, arguments JSON). Le harness décide de l'exécuter, de la refuser ou de la renvoyer en erreur. Tout contrôle (permissions, validation, timeouts, limites de coût) s'accroche à ce point.

Vocabulaire à fixer, car les harness divergent. Une étape est un appel au modèle. Un tour va du message utilisateur à la réponse finale et compte plusieurs étapes. Certains harness (Claude Code) appellent « tour » ce que d'autres appellent « étape ».

Ce que ce n'est pas : un planificateur, un système multi-agents ou une gestion de contexte. Ces couches se branchent sur la boucle. Elles ne la définissent pas.

## Mécanismes

```
historique = [système, utilisateur]
tant que limites non atteintes :
    réponse = modèle(historique, schémas_outils)
    historique += réponse
    si pas d'appel d'outil : fin du tour
    pour chaque appel : historique += résultat(appel)
```

La condition d'arrêt naturelle est l'absence d'appel d'outil. Claude Code, Codex et Pi s'arrêtent ainsi. Codex y ajoute des entrées utilisateur en file (« steer »). Pi ajoute la file « follow-up » et un drapeau `terminate` par résultat d'outil, qui n'arrête la boucle que si tout le lot l'indique.

### Invariants d'historique

Un résultat par appel d'outil, toujours. Les API refusent un appel sans résultat. Donc une erreur d'outil (outil inconnu, JSON illisible, arguments invalides, exception) devient un résultat marqué en erreur, jamais une exception qui traverse la boucle. Pi renvoie « Operation aborted » pour chaque appel annulé afin de ne laisser aucun orphelin.

Historique en ajout seul et prompt système stable. Un préfixe identique d'un appel à l'autre est la condition du prompt caching. Hermes exige un système stable octet pour octet et interdit tout message utilisateur synthétique en cours de boucle. Les retraits d'historique doivent rester rares et documentés (par exemple retirer la demande restée sans réponse après une erreur fournisseur au premier appel).

Alternance des rôles respectée, format de message canonique unique en interne. Hermes convertit trois modes d'API vers le format chat OpenAI. Les messages assistant se réduisent à `role`, `content`, `tool_calls` pour ne pas porter de champs propres à un fournisseur.

### Limites et arrêt

Limites vérifiées avant chaque appel au modèle, jamais après : on ne paie pas un appel qu'on ne veut pas. Le dépassement possible est borné à un appel. Claude Code expose `max_turns` et `max_budget_usd` (le dépassement peut atteindre le coût d'une réponse). Hermes plafonne à 500 itérations et accorde un appel de grâce pour résumer. Pi n'a aucun plafond. Codex a des budgets séparés de la boucle.

Une limite atteinte ne doit pas détruire la session. Le motif d'arrêt est typé (fin naturelle, limite d'étapes, budget, interruption, erreur fournisseur). L'interface peut accorder une tranche supplémentaire et reprendre avec l'historique tel quel, qui se termine par des résultats d'outils et reste valide.

### Réponse coupée par la limite de tokens

Si `finish_reason` vaut `length` et que le message contient des appels d'outils, leurs arguments sont probablement tronqués. Ne pas les exécuter. Renvoyer au modèle une erreur par appel demandant un contenu plus court. Pi fait exactement cela. Un `write_file` exécuté avec un contenu tronqué est pire qu'une erreur.

### Outils parallèles

Les lectures peuvent s'exécuter en concurrence, les écritures et le shell doivent être sérialisés. Codex le résout avec un seul verrou lecteur/écrivain : les outils parallèles prennent le verrou en lecture, les autres en écriture. Hermes lance un pool de threads et réinsère les résultats dans l'ordre d'origine. Pi persiste les résultats dans l'ordre de la source, même si l'exécution est concurrente. Un seul outil séquentiel dans un lot force tout le lot en séquentiel. La version séquentielle simple suffit pour un premier harness.

### Interruption

L'annulation de la tâche asynchrone est le mécanisme naturel : elle traverse l'attente du modèle comme celle d'un sous-processus. Trois règles.

Fermer l'historique de façon valide. Un appel en cours reçoit un résultat « interrompu », les appels suivants du même message un résultat « non exécuté », pour que le modèle comprenne au tour suivant. Sans appel en cours (annulation pendant l'appel au modèle), aucun message assistant n'existe : ajouter un message utilisateur qui signale l'interruption, en conservant la demande d'origine.

Tuer le groupe de processus, pas seulement le processus. Lancer les commandes dans une nouvelle session de processus et envoyer le signal au groupe. Sinon les petits-enfants gardent le tube ouvert et la lecture ne se termine jamais.

Distinguer le timeout de l'interruption pour la sortie partielle. Au timeout, renvoyer la sortie déjà lue avec une marque `[TIMEOUT]` : le modèle peut diagnostiquer. À l'interruption volontaire, l'utilisateur sait ce qui s'est passé et Hermes jette toute réponse partielle. Informer suffit.

> [!warning] `uncancel()` avale les annulations externes
> Absorber `CancelledError` au niveau du tour est légitime, mais l'appel systématique à `Task.uncancel()` fait disparaître l'annulation pour un `asyncio.timeout` ou un `TaskGroup` englobant. Ne pas l'appeler : le compteur `cancelling()` reste visible de l'appelant. Le comportement dépend de la sémantique d'asyncio (Python 3.12) et doit être couvert par un test.

### Erreurs fournisseur

Séparer erreur d'outil (renvoyée au modèle) et erreur fournisseur (jamais dans l'historique). Classer en au moins : contexte trop long, authentification, injoignable ou trop lent, autre. Codex pilote ses retries par une politique par type d'erreur (jamais, délai dicté par le serveur, backoff, repli HTTP) avec 5 retries de flux et 4 de requête par défaut. Pi retente 3 fois en backoff exponentiel au niveau agent et laisse les retries fournisseur à 0, pour traiter lui-même les quotas. Hermes ajoute un classifieur d'erreurs et un repli sur une liste de fournisseurs.

Erreur au premier appel du tour : retirer la demande pour que l'utilisateur la renvoie. Erreur en milieu de tour : garder l'historique, des actions ont eu lieu.

## Implémentation & patterns

Noyau sans entrée-sortie. Le tour est un générateur asynchrone d'événements typés (appel d'outil démarré, terminé, message assistant, étape terminée, limite atteinte, erreur fournisseur, fin de tour avec motif). L'interface (CLI, TUI, API) consomme les événements. La question « continuer ? » est posée par l'interface, qui rappelle une méthode de reprise. Même noyau pour tous les fronts.

Point d'exécution unique des outils : un registre qui valide les arguments contre le schéma JSON, exécute, convertit toute exception en résultat d'erreur et garantit exactement un résultat par appel. Seule l'annulation le traverse.

Exception inattendue du client modèle : l'attraper à la frontière de la boucle et la convertir en erreur fournisseur typée. Un client qui lève une exception arbitraire ne doit pas tuer le REPL. Convertir aussi une réponse structurellement illisible (choix absents, usage manquant) en erreur typée.

Enveloppes d'erreurs : les bibliothèques d'abstraction de fournisseurs enveloppent parfois un « connection refused » dans une erreur serveur générique. Classer sur la cause, pas seulement sur le type de l'exception, et couvrir ce cas par un test contre un port fermé.

Serveurs locaux compatibles OpenAI (mlx_lm.server, Ollama) : le client sous-jacent exige une clé non vide que le serveur ignore. Envoyer une valeur factice quand une base d'URL est définie sans variable de clé. Dans un conteneur, le serveur de l'hôte se joint par `host.docker.internal`, et le serveur doit écouter sur une adresse accessible depuis le conteneur.

Modèles à raisonnement : prévoir une limite de tokens de sortie confortable. Un raisonnement long peut consommer la limite avant le premier token de contenu, d'où une réponse vide avec `finish_reason=length`.

Affichage : ne jamais tronquer la réponse du modèle, même dans un mode « lignes-titres ». Réserver les titres aux événements d'outils. Une réponse coupée à sa première ligne est inutilisable.

## Limites & anti-patterns

Compter sur un mock pour valider le contrat fournisseur. Un faux client prouve l'orchestration de la boucle, jamais la construction de la requête, la traduction des erreurs ni la lecture de la réponse. Garder au moins un test qui exerce le vrai client contre un faux serveur HTTP local.

Exécuter des appels d'outils issus d'une réponse tronquée. Laisser une exception d'outil traverser la boucle. Oublier le résultat d'un appel annulé. Muter le prompt système en cours de session. Vérifier les limites après l'appel.

Coût inconnu traité comme zéro. Si le prix d'un modèle est inconnu (serveur local, modèle non référencé), le budget ne peut pas s'appliquer : le dire explicitement plutôt que d'afficher 0 $. Ne pas deviner un prix à partir d'un nom qui coïncide avec un modèle payant connu.

Sans compaction, une erreur de contexte trop long termine la session utile. Sans streaming, l'utilisateur n'a aucun retour pendant l'appel. Sans retries, un incident réseau bref coûte un tour. Ce sont les extensions naturelles, dans cet ordre de rendement variable selon l'usage.

La complexité des harness matures (Hermes répartit sa boucle sur une quinzaine de modules) vient des garde-fous, pas de l'algorithme.

## État de l'art & références

Convergences : arrêt sur absence d'appel d'outil, historique canonique en ajout seul, événements typés, erreurs d'outil renvoyées au modèle, annulation propagée jusqu'aux outils (jeton d'annulation chez Codex, signal chez Pi, thread abandonné chez Hermes). Divergences : plafond de tours (Pi aucun, Hermes 500, Claude Code configurable), parallélisme des outils, politique de retry, steering en cours de tour.

Débats ouverts : plafonner ou non les étapes (Pi parie sur l'absence, au prix d'un contrôle humain) ; streamer les arguments d'outils pour afficher un diff avant la fin de l'appel ; hooks capables de bloquer l'arrêt et de relancer la boucle (Codex `Stop`) ; compaction décidée après chaque échantillonnage, seulement si la boucle continue (Codex), ou entre deux tours (Pi).

#### Ressources utiles :
- [Claude Agent SDK — agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop)
- [Pi coding agent — article de conception](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)
- [Pi monorepo (packages/agent/src/agent-loop.ts)](https://github.com/badlogic/pi-mono)
- [Codex (core/src/session/turn.rs)](https://github.com/openai/codex)
