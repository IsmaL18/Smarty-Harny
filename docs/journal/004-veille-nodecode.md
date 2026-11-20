# Journal 004 — Veille sur Nodecode

Pas de notion ni de code du harness dans cette entrée : une veille sur un harness recommandé par un collègue. Livrable : [`docs/veille/nodecode.md`](../veille/nodecode.md), plus une section 6 ajoutée à [`docs/veille/synthese.md`](../veille/synthese.md). Niveau : hors workflow, documentation seule.

## Ce qui a été fait

- Vérification que Nodecode est bien un harness (site et dépôt MIT, Common Lisp) ; son modèle hébergé Cyber v1 est exclu du périmètre.
- Survol du site, puis clone superficiel du dépôt (commit `fed3cb7`) dans le scratchpad, supprimé à la fin.
- Lecture ciblée par trois sous-agents (1 haiku pour cartographier, 2 sonnet pour lire le code utile), aucun opus pour économiser les crédits. Fiche rédigée dans la session principale à partir de leurs notes.
- Vérifications faites par la session principale : `--sandbox` absent du README et des docs, exécution séquentielle des appels d'outils d'un round, licence MIT, 161 fichiers de test.

## Ce qui n'est pas vérifié

- Le code des cellules (`guard`, `mcp`, `team`, `web`...) est dans un dépôt externe et n'a pas été lu.
- Les autres affirmations de la fiche reposent sur les notes des sous-agents (lignes de code citées, non relues une à une).
- Le chiffre ARC-AGI-3 n'est pas reproductible depuis le dépôt.
- Le comportement de `--sandbox` sous macOS n'est pas établi.

## Apprentissages sur le processus

- Un survol puis une lecture du code en parallèle a coûté peu de tokens principaux : la carte des fichiers par un petit modèle évite que les agents suivants explorent à l'aveugle.
- Un agent peut signaler un écart avec le brief (161 fichiers de test, et non 167) : toujours recompter plutôt que recopier un chiffre.

## Grill de fin

Non fait (veille, pas d'itération de notion).
