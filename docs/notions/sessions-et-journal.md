---
title: "Sessions durables et journal en ajout seul"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: concept
date: 2026-11-16
---

## Définition exacte & périmètre

Une session durable fait survivre la conversation d'un agent au processus qui la porte. Le support est un journal : un fichier où chaque message, résultat d'outil et changement d'état est ajouté comme une entrée, sans jamais réécrire ce qui précède. L'historique envoyé au modèle n'est plus l'état : c'est une projection du journal.

Trois objets à ne pas confondre.

- L'historique vivant est la liste de messages en mémoire, présentée au modèle. Il peut être tronqué, compacté, retouché.
- Le journal est la source de vérité sur disque. Il garde la sortie complète, l'usage, les changements de modèle.
- L'état de session est tout le reste qu'une reprise doit retrouver : coût cumulé, budgets accordés, fichiers déjà lus, mode d'affichage.

Ce que ce n'est pas : une mémoire à long terme (notes que l'agent se réserve entre sessions), ni une compaction (qui réduit l'historique pour tenir dans la fenêtre). Le journal alimente la reprise, l'audit et le rejeu, pas la sélection de ce qui entre dans le contexte.

## Mécanismes

### Journal en ajout seul

Le format dominant est JSON Lines : une entrée par ligne, UTF-8, un en-tête en première ligne (version du format, dossier d'origine, date, modèle). Pi, Codex et Claude Code convergent là-dessus. L'ajout seul donne trois propriétés utiles.

- Un arrêt brutal ne perd que la dernière ligne en cours d'écriture.
- Le fichier se lit avec n'importe quel outil (`jq`, `grep`, `tail -f`).
- Les branches et les réparations deviennent des entrées, pas des modifications.

SQLite est l'alternative sérieuse (requêtes, transactions). Codex l'utilise en index à côté du JSONL, pas à la place. Un fichier JSON réécrit à chaque tour est à écarter : une coupure pendant la réécriture peut tout corrompre.

### Chaînage `id` / `parentId` et branches

Chaque entrée porte un `id` et un `parentId` désignant l'entrée précédente de sa branche. La branche active se reconstruit en partant de la dernière entrée écrite et en remontant jusqu'à la racine. L'historique du modèle est la liste des messages de cette chaîne, dans l'ordre.

Changer de branche n'efface rien. On écrit une entrée dont le parent est le point de reprise choisi, et les entrées suivantes s'y accrochent. Les anciennes branches restent dans le fichier, inertes. Le retrait d'une demande restée sans réponse suit la même mécanique : un nouveau point de départ, pas une suppression.

Avec un seul auteur à la fois, un entier croissant suffit comme `id`. Des identifiants aléatoires (Pi utilise 8 caractères hexadécimaux) ne se justifient que si plusieurs auteurs peuvent écrire ou si des journaux doivent fusionner.

### Ce que le journal enregistre

Les messages au format présenté au modèle, avec leurs appels d'outils et leurs résultats. L'usage et le coût de chaque appel, avec une valeur absente (`null`) quand le coût n'est pas estimable, jamais zéro. Les empreintes des fichiers lus ou écrits, pour restaurer la règle « relire avant d'éditer ». Les changements d'état : modèle, mode d'affichage, interruption, octroi de budget, changement de branche.

Les cumuls (coût, budgets) se calculent sur tout le journal, branches abandonnées comprises : ce qui a été dépensé l'a été. L'historique, lui, ne suit que la branche active.

### Verrou à bail

Un journal en ajout seul suppose un seul auteur. Deux processus qui écrivent la même session entrelacent leurs lignes et cassent le chaînage. Le verrou garantit l'exclusivité.

Un fichier de verrou créé en création exclusive (`O_EXCL`) contient un jeton aléatoire, le nom d'hôte et le pid. Un fil dédié le touche à intervalle régulier (bail) et vérifie que le jeton est toujours le sien. Le verrou est périmé si son âge dépasse le bail, ou si l'hôte est le même et le pid n'existe plus. La reprise d'un verrou périmé passe par un renommage atomique vers un nom unique : un seul gagnant.

Le pid seul est faux entre conteneurs, qui ont des espaces de pid séparés. `flock` libère exactement à la mort du processus, mais sa sémantique sur un montage de machine virtuelle ou réseau est rarement vérifiée. Le bail ne dépend d'aucune des deux.

## Implémentation & patterns

### Écrire avant d'agir

L'ordre d'écriture fait la robustesse. La demande est écrite avant l'appel au modèle. Le message assistant, avec ses appels d'outils, est écrit avant l'exécution des outils. Chaque résultat est écrit dès qu'il existe. Une ligne = un seul `write` sur un descripteur en mode ajout. Un `write` survit à un SIGKILL parce que le noyau a déjà la donnée ; le `fsync` ne protège que d'une coupure de la machine. Un `fsync` en fin de tour et à la fermeture suffit.

### Réparer par ajout à la reprise

Un arrêt brutal laisse des anomalies prévisibles. La lecture est la seule étape qui les interprète, et elle ne modifie rien. Les réparations sont des ajouts.

| Anomalie | Traitement |
|---|---|
| Dernière ligne tronquée | ignorée avec avertissement ; avant le premier ajout, on ferme la ligne par `\n` et on écrit une entrée qui la désigne |
| Ligne invalide au milieu | refus, sauf si une entrée de réparation la désigne |
| Appel d'outil sans résultat | on ajoute un résultat d'erreur « action interrompue, état inconnu », que le modèle lira |
| Dernier message coupé par la longueur | conservé, marqué comme coupé au rejeu |

L'entrée qui désigne la ligne tronquée est indispensable. Sans elle, la ligne fermée par `\n` devient une « ligne invalide au milieu » à la reprise suivante, et un journal réparé une fois n'est plus relisible. Le résultat d'erreur synthétique répond à une contrainte des API de chat : chaque appel d'outil doit avoir exactement un résultat, sinon le fournisseur rejette l'historique.

### Rattacher la session au dossier

Une session appartient à un dossier de travail. Dans un conteneur, ce dossier a un chemin fixe qui ne dit rien de l'hôte. Il faut passer le chemin d'origine par une variable d'environnement, le consigner dans l'en-tête, et ne lister ou reprendre que les sessions dont le chemin égale le chemin courant. Claude Code lie de même ses sessions au répertoire. Un dossier déplacé emporte ses journaux mais les refuse : l'identité est le chemin d'origine.

### Restaurer sans mentir

Reprendre un fichier lu ne prouve pas qu'il n'a pas changé. Les empreintes restaurées servent à retrouver l'état « déjà lu », pas « encore à jour ». Après une reprise ou un changement de branche, le fichier a pu bouger. On prévient l'utilisateur et on injecte un message au modèle : le dossier peut différer, relire avant de modifier.

### Secrets

La clé API n'est jamais une donnée du journal : l'en-tête porte l'alias du modèle, pas la clé. À l'écriture, la valeur exacte des variables d'environnement sensibles est remplacée dans la ligne sérialisée, ce qui couvre un `env` lancé par le modèle. Pour des sorties écrites par blocs, il faut un tampon de recouvrement de la longueur de la clé, sinon une clé coupée entre deux blocs passe.

### Cycle de vie

Les sorties volumineuses enregistrées à côté du journal partagent son identifiant et vivent aussi longtemps que lui. À la suppression, supprimer les sorties d'abord, le journal ensuite : une interruption au milieu laisse un journal sans ses sorties (cas tolérable), l'ordre inverse laisse un dossier orphelin sans propriétaire. Une purge au lancement supprime les sessions inactives depuis N jours, sauf celles qui sont verrouillées.

## Limites & anti-patterns

> [!warning] Le journal est en clair
> Tout ce que le modèle a vu y est : contenu de fichiers, sorties de commandes, secrets que le masquage ne reconnaît pas. Une clé transformée (base64, découpée) passe. Stocké dans le projet, il est lisible et modifiable par l'agent lui-même via son shell. Ni confidentialité, ni intégrité.

- Reconstruire demande de lire tout le fichier. Pour des sessions très longues, un index (Codex garde une base SQLite des métadonnées) évite de tout relire pour lister.
- La reprise est une zone délicate. Codex y consacre un module de reconstruction dont les tests dépassent largement le code : compaction, branches et réparations interagissent.
- Le verrou à bail coûte jusqu'au bail d'attente après un crash entre conteneurs, et suppose des horloges à quelques secondes près.
- L'atomicité de `rename` et de `O_EXCL` sur un montage virtualisé reste à vérifier, pas à supposer.
- Une version de format inconnue doit provoquer un refus. Lire quand même un format dont on ignore les règles de chaînage corrompt silencieusement la branche reconstruite. À l'intérieur d'une version, ajouter des champs et des types d'entrée reste sûr si le lecteur ignore ce qu'il ne connaît pas mais garde le chaînage.
- Le coût ne se retrouve pas par la branche active. Une somme limitée à la branche courante sous-estime la dépense réelle.
- Une purge qui ne touche que le dossier lancé laisse les sessions des dossiers jamais relancés. Acceptable quand elles vivent dans le projet et partent avec lui.
- Le modèle peut modifier le journal par son shell quand il vit dans le dossier de travail : ce n'est pas une preuve d'audit.

## État de l'art & références

Les trois harness étudiés écrivent du JSONL en ajout seul. Pi : un fichier par session, en-tête avec version et dossier, entrées chaînées par `id` et `parentId`, branches dans le même fichier, commandes `/tree`, `/fork`, `/clone`, `/resume`. Codex : le « rollout » JSONL est distinct de l'historique en mémoire, garde la sortie complète des outils pour le rejeu, avec un index SQLite et un verrou d'écriture. Claude Code : transcription JSONL liée au répertoire, reprise sous le même identifiant, fork vers un nouvel identifiant.

Débats ouverts. Fichier plat contre base : le plat gagne en lisibilité et en robustesse, la base en requêtes. Fork par copie (Claude Code, Pi `/fork`) contre branche dans le même fichier (Pi `/tree`) : la copie isole, la branche garde tout au même endroit. Retour vers une branche abandonnée : le format l'autorise (écrire une entrée dont le parent est l'ancienne pointe), peu d'outils l'exposent. Reprise sur conteneurs sans état : Claude Code ajoute un adaptateur de stockage avec écriture double, local d'abord.

#### Ressources utiles :
- [Pi monorepo (coding-agent, session-format.md)](https://github.com/badlogic/pi-mono)
- [Codex (rollout, recorder, reconstruction)](https://github.com/openai/codex)
- [Claude Code — tools reference](https://code.claude.com/docs/en/tools-reference)
