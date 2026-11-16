---
title: "Mode headless d'un agent"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: technique
date: 2026-11-16
---

## Principe & cas d'usage

Le mode headless fait tourner l'agent sans humain devant : un prompt en argument, une réponse sur la sortie standard, un code de sortie. Il sert aux scripts, à la CI, aux pipes (`git diff | agent -p "Review"`), aux évaluations et à tout programme qui pilote l'agent comme un sous-processus. C'est le chemin le plus court vers l'automatisation, avant même une API serveur.

Les harness convergent sur le même schéma. Pi : `--print` (réponse finale seule), `--mode json` (flux JSONL d'événements), `--mode rpc` (commandes sur stdin). Codex : `codex exec`, avec une sortie humaine ou un flux JSONL, et un SDK qui lance le binaire et parse ce flux. Claude Code : `-p` avec formats texte, JSON et flux. Tous partagent la boucle et la gestion de session avec le mode interactif : le headless est une façade, pas un second agent.

Condition d'application : aucune question ne peut être posée. Toute action qui demanderait une approbation doit avoir une réponse par défaut décidée avant le lancement.

## Implémentation

### Le contrat est une interface publique

Trois éléments forment le contrat : ce qui sort sur stdout, ce qui sort sur stderr, le code de sortie. Un script s'appuie dessus. Les changer casse des utilisateurs, contrairement au format interne du journal de session.

Le mode texte écrit uniquement la réponse finale sur stdout. Tout le reste (progression, appels d'outils, avertissements) va sur stderr. Le mode flux écrit un objet JSON par ligne, vidé à chaque événement, pour qu'un lecteur voie la progression en direct et non en bloc à la fin.

### Codes de sortie

Un code distinct par famille de fin permet à un script de décider sans parser.

| Situation | Code |
|---|---|
| Tour terminé normalement | 0 |
| Erreur du fournisseur, échec d'enregistrement | 1 |
| Erreur d'usage ou d'environnement (option, config, clé, session introuvable ou occupée) | 2 |
| Limite atteinte (étapes, budget) | 3 |
| Interruption par signal | 130 |

Le 130 reprend la convention shell de SIGINT. Séparer 2 de 1 distingue « mal appelé, inutile de réessayer » de « échec à l'exécution, peut-être transitoire ». Séparer 3 de 1 distingue « l'agent n'a pas fini » de « ça a cassé ».

Un code non nul avec un stdout texte vide est plus sûr qu'une réponse partielle : un script qui teste seulement `$?` ou qui injecte stdout dans la suite d'un pipe ne prend pas un texte coupé pour un résultat. La réponse finale n'existe que pour le statut de succès.

### Flux JSONL

Les types de lignes qui suffisent : début de run (session, modèle, dossier, reprise ou non), appel d'outil (identifiant, nom, arguments), résultat d'outil (même identifiant, contenu, drapeau d'erreur), message de l'assistant, avertissement, résultat final. Ce dernier porte le statut, la raison d'arrêt, la réponse, le nombre d'étapes, les tokens, le coût cumulé et l'identifiant de session, pour permettre une reprise.

Deux détails qui comptent. L'identifiant d'appel doit exister sur l'événement de début et sur celui de fin, sinon un lecteur ne peut pas relier appel et résultat quand les outils s'exécutent en parallèle. Le premier objet porte un champ de version du schéma, entier, qui démarre à 1.

> [!tip] Un flux distinct du journal
> Ne pas exposer les lignes du journal de session comme flux. Le contrat public figerait le format interne (chaînage, usage, retraits), le journal n'a ni ligne de début ni ligne de fin, et le masquage des secrets y modifie ce que le script recevrait. Deux formats, une même source d'événements typés, aucune conversion de l'un en l'autre.

### Protéger stdout

Une bibliothèque qui imprime, un avertissement de dépendance, un `print` oublié : n'importe quoi peut corrompre un flux machine. La parade est de dupliquer le descripteur 1 d'origine au démarrage pour le seul protocole, puis de rediriger `sys.stdout` et le descripteur 1 vers stderr. Plus rien ne peut écrire sur la sortie de protocole par accident, y compris un sous-processus hérité.

### Signaux

SIGINT et SIGTERM annulent la tâche du tour. Le noyau ferme l'historique de façon cohérente (chaque appel a un résultat), l'état « interrompu » est écrit, le code est 130. Dans un conteneur, le processus est le PID 1, pour lequel le noyau Linux ne fournit aucun comportement par défaut sur SIGTERM : sans gestionnaire explicite, `docker stop` attend dix secondes puis tue. Le gestionnaire est donc obligatoire.

### Lanceur et conteneur

Un pseudo-terminal (`-t`) fusionne stdout et stderr et convertit les fins de ligne. Le lanceur ne doit l'activer que si stdin et stdout sont de vrais terminaux. Le code de sortie du conteneur doit traverser le lanceur tel quel.

## Pièges & limitations

> [!warning] Un mode sans humain ne pose jamais de question
> Le headless ne doit jamais appeler le chemin de reprise qui attend une réponse (approbation, choix). Sinon le script se bloque indéfiniment sur un stdin vide. La politique d'approbation doit être fixée à l'avance, et refuser par défaut ce qui demande confirmation.

- Un stdout qui mêle texte de progression et réponse force le script appelant à filtrer. Garder la réponse seule sur stdout.
- Sans valeur de sortie claire sur limite atteinte, un script traite une réponse inachevée comme un succès. Un code dédié et un statut explicite dans le flux l'évitent.
- Écrire dans un journal de session depuis un script lance des sessions en parallèle sur le même dossier : l'option « sans enregistrement » et un verrou par session sont nécessaires, sinon deux runs concurrents interfèrent.
- Les exécutions CI sont souvent coûteuses : le coût et les tokens doivent figurer dans le résultat final, pas seulement dans un tableau de bord.
- Tester l'isolation de stdout exige un vrai sous-processus. Un test qui appelle la fonction d'entrée avec des flux capturés ne voit pas l'impression d'une bibliothèque sur le descripteur 1.
- Un flux non vidé à chaque événement semble fonctionner en test (le programme se termine) et se bloque dans un pipe, où la sortie est bufferisée par blocs.
- L'arrêt par SIGTERM sans pseudo-terminal transmis par `docker run` doit se vérifier à la main : le comportement dépend de la façon dont le runtime relaie le signal.

## Variantes & tooling

| Outil | Texte | Flux | Autres |
|---|---|---|---|
| Pi | `--print`, composable en pipe | `--mode json` | `--mode rpc` (commandes JSONL sur stdin) |
| Codex | sortie humaine de `exec` | JSONL d'événements, `--output-schema` | SDK TypeScript et Python qui lancent `exec` |
| Claude Code | `-p` | formats JSON et flux | SDK, `session_id` dans le résultat pour reprendre |

Deux directions au-delà du simple sous-processus. Le mode RPC sur stdio (Pi) laisse un programme envoyer plusieurs commandes à un agent vivant. Le serveur applicatif (Codex `app-server`, JSON-RPC) sert plusieurs sessions et plusieurs clients. Un schéma de sortie imposé (`--output-schema`) transforme la réponse finale en donnée structurée validable.

## Retours terrain

Le premier défaut rencontré en pratique est la pollution de stdout, presque toujours par une dépendance et jamais par le code de l'agent. La redirection du descripteur au démarrage est ce qui le règle de façon fiable.

Le deuxième est le signal dans un conteneur : tout semble correct en local, et l'arrêt échoue seulement une fois l'agent lancé comme PID 1.

Les codes de sortie distincts sont rarement exploités au début, mais ils deviennent l'interface de la CI dès que l'agent tourne dans un pipeline : réessayer sur 1, corriger l'appel sur 2, augmenter le budget sur 3.

#### Ressources utiles :
- [Codex — mode non interactif](https://developers.openai.com/codex/noninteractive)
- [Pi monorepo (modes print, JSON, RPC)](https://github.com/badlogic/pi-mono)
- [Claude Code — tools reference](https://code.claude.com/docs/en/tools-reference)
