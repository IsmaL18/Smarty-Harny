---
title: "Troncature des sorties d'outils"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: technique
date: 2026-11-15
---

## Principe & cas d'usage

Une sortie d'outil entre telle quelle dans le contexte du modèle. Une commande qui crache 5 Mo de logs, un fichier minifié ou un `grep` trop large saturent la fenêtre, coûtent des tokens et noient le signal. La troncature borne ce que le modèle voit. Le débordement sur disque garde ce qui a été coupé accessible.

Trois exigences vont ensemble. Borner la taille. Dire qu'une omission a eu lieu. Donner au modèle le moyen de récupérer ce qui manque.

Les harness convergent sur ce triptyque. Claude Code applique des limites par outil et écrit les gros résultats dans un fichier de session relisible avec `Read` et `Grep`. Codex coupe au milieu avec un en-tête explicite et garde la sortie complète dans son journal de session. Pi tronque à 2000 lignes ou 50 Ko avec un message de suite et un chemin vers le fichier complet. Hermes écrit toute sortie au-dessus du seuil sur disque et la remplace par un aperçu et un chemin.

## Implémentation

### Où couper : au milieu

Garder le début seul est le mauvais réflexe. Pour une commande, l'information utile est à la fin : résumé des tests, dernière erreur, code de sortie. Pour un fichier, début et fin portent les imports et les exports. Couper au milieu préserve les deux extrémités.

Le budget est total, pas par morceau. La coupe tombe à une limite de ligne pour ne pas livrer une ligne amputée. La répartition est asymétrique pour une commande, environ 40 % de début et 60 % de fin. Elle est symétrique, 50/50, pour un fichier.

### Signaler l'omission

Un en-tête indique ce qui manque, en numéros de ligne et non en tokens. Codex y met le nombre de tokens d'origine et le total de lignes. Mieux vaut y ajouter la commande ou la plage qui permet de relire la partie omise : le modèle peut agir directement dessus.

```text
[sortie tronquée : lignes 412 à 9 873 omises sur 10 240]
[relire avec : read_file(path, offset=412, limit=200)]
```

Le message qui dit quoi faire ensuite est l'élément qui rend la troncature supportable. Sans lui, le modèle croit avoir tout vu ou relance la commande à l'aveugle.

### Ligne géante

Un fichier minifié tient en une ligne de plusieurs Mo. La coupe à la limite de ligne n'a alors aucun sens. On coupe au caractère et on le dit. Cette partie n'est pas relisible par plage de lignes : l'en-tête doit suggérer autre chose (filtre, `cut`, recherche ciblée). Pi plafonne aussi la longueur de ligne des résultats de `grep` (500 caractères), Hermes celle des sorties (2000).

### Capture en streaming à mémoire bornée

Ne jamais accumuler la sortie entière. Pendant la lecture du flux, on garde trois choses :

- le début, jusqu'à son budget ;
- une fenêtre glissante de fin, qui se renouvelle ;
- des compteurs : octets et lignes vus au total.

Avec cela, la sortie finale se reconstruit à la fin sans que la mémoire dépende de la taille du flux.

### Déborder sur disque

Le disque ne sert qu'au dépassement. Tant que la sortie tient dans le budget, rien n'est écrit. On bufferise en mémoire, et au premier dépassement on ouvre le fichier, on y vide le tampon, puis on continue d'y écrire. Une commande bavarde mais courte ne laisse aucune trace.

Le fichier a un plafond. Sans lui, une commande comme `yes` remplit le disque en quelques minutes. Au plafond, on cesse d'écrire et on signale le fichier comme incomplet. La fenêtre de fin continue de suivre la vraie fin du flux : le modèle voit la dernière erreur même si le fichier s'est arrêté avant.

L'ensemble tient dans la réponse : un aperçu tronqué, le chemin du fichier, la mention éventuelle d'incomplétude.

### Cycle de vie du fichier

Un dossier par session, dans le dossier de travail. Un `.gitignore` interne contenant `*` l'exclut de Git sans toucher au `.gitignore` du dépôt. Le dossier est supprimé en fin de session. Au lancement, une purge supprime les restes de plus de 24 heures. Une session concurrente récente n'est jamais touchée.

## Pièges & limitations

> [!warning] Couper un flux d'octets peut trancher un caractère
> Un plafond en octets qui tombe au milieu d'un caractère UTF-8 multi-octets écrit un fichier illisible. Couper sur une frontière de caractère. Pour les lectures par blocs d'un sous-processus, utiliser un décodeur UTF-8 incrémental, qui garde en attente les octets d'un caractère incomplet entre deux blocs.

Les autres pièges tiennent à la gestion des ressources.

- Le nettoyage doit couvrir tous les chemins. Fermer le fichier et tuer le groupe de processus aussi sur annulation et sur exception, pas seulement sur le chemin normal. Sinon un `Ctrl-C` laisse un descripteur ouvert et un processus qui écrit encore.
- Un arrêt par SIGTERM sans gestionnaire n'exécute pas les blocs `finally`. La suppression de fin de session est donc perdue. La purge au lancement est le filet de sécurité, pas un détail.
- Le fichier de débordement est un fichier comme un autre. Il se relit par plage avec l'outil de lecture et il est soumis à la même troncature. Un modèle qui le relit en entier recrée le problème qu'on voulait éviter, d'où l'intérêt de l'en-tête avec plage.
- La sortie d'un timeout ou d'une interruption suit la même troncature. Elle est partielle, mais aussi volumineuse qu'une autre.
- Interdire à l'agent d'écrire dans le dossier réservé est une commodité, pas une sécurité. Elle évite qu'il pollue ou écrase ses propres débordements. Le shell, lui, peut y écrire : ne pas présenter cela comme une garantie.
- La troncature s'applique à l'historique vivant. Codex garde la sortie complète dans le journal de session pour le replay. Séparer les deux évite de perdre l'information pour l'audit.
- Tronquer ne réduit pas ce que le modèle peut demander ensuite. Un modèle qui relit chaque plage consomme autant que sans troncature. La limite doit s'accompagner de consignes d'usage (filtrer, paginer).

## Variantes & tooling

Les harness étudiés se distinguent surtout par l'unité et la destination.

| Harness | Unité | Débordement |
|---|---|---|
| Claude Code | tokens et caractères, par outil | fichier de session, relu par `Read` et `Grep` |
| Codex | tokens (10 000 par défaut), coupe au milieu | journal de session complet |
| Pi | 2000 lignes ou 50 Ko | fichier complet, chemin dans le message |
| Hermes | 50 000 octets, 2000 lignes, 2000 caractères par ligne | fichier de débordement, aperçu et balise `<persisted-output>` |

Hermes ajoute un budget par tour, qui borne le total de sorties d'un même tour et pas seulement chaque résultat. Une autre variante déplace le filtrage en amont : un hook `PreToolUse` de Claude Code peut réécrire la commande pour y ajouter `| tail -n 100`. La sortie arrive déjà réduite, sans troncature ni fichier.

## Retours terrain

La règle la plus constante : les messages de troncature qui indiquent quoi faire ensuite (relire par pages avec offset et limit, restreindre la recherche) guident mieux le modèle qu'une simple coupe. Les guides de conception d'outils d'agents le recommandent aussi.

Garder le début seul est l'erreur de départ la plus fréquente, et elle ne se voit qu'en usage réel : tout paraît correct jusqu'à ce qu'une commande échoue à la dernière ligne.

Les risques d'exploitation viennent du disque, pas de la mémoire : plafond absent, fichiers orphelins après un arrêt brutal, caractères tranchés. Ce sont des défauts de cycle de vie qu'une troncature en mémoire seule n'a pas.

#### Ressources utiles :
- [Claude Code — tools reference](https://code.claude.com/docs/en/tools-reference)
- [Anthropic — Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Pi monorepo (truncate.ts, bash.ts)](https://github.com/badlogic/pi-mono)
- [Codex (utils/output-truncation)](https://github.com/openai/codex)
