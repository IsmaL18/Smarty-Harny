# CLAUDE.md

Projet d'apprentissage du harness engineering : une base de connaissance (`docs/`) et un harness d'agent LLM en Python, construit par itérations.

## Objectifs

1. Construire un harness solide et utilisable : un noyau générique (boucle agent, outils, contexte, permissions) dont le premier profil est un agent de code.
2. Consigner chaque notion apprise pour la réutiliser en mission Gen AI.

## Cycle d'une itération

1. Choisir la notion dans `docs/ROADMAP.md`.
2. Écrire ou compléter la fiche `docs/notions/<notion>.md` à partir de la veille (`docs/veille/`), selon les règles « Fiches de notion » ci-dessous.
3. Implémenter l'amélioration dans le harness.
4. Consigner les apprentissages dans `docs/journal/NNN-<iteration>.md`.
5. Faire un grill de fin d'itération (questions à l'utilisateur sur la notion) ; les lacunes révélées complètent la fiche.

Le niveau de rigueur (tests, revues) se décide à chaque itération, au cadrage (task-kickoff).

## Conventions

- Docs, commentaires, messages de commit et messages affichés à l'utilisateur : en français.
- Identifiants du code (modules, classes, fonctions, variables) : en anglais.
- Le code est écrit par Claude et relu par l'utilisateur pour apprendre : commentaires pédagogiques abondants, qui expliquent le *pourquoi* et la notion de harness engineering en jeu, avec renvoi vers la fiche `docs/notions/` correspondante.
- Approche « équilibrée » : le cœur du harness (boucle, outils, contexte, permissions) est écrit à la main ; le périphérique passe par des bibliothèques.
- Appels aux modèles via LiteLLM (Anthropic + tout provider compatible OpenAI, dont `mlx_lm.server` et Ollama en local). Version de LiteLLM figée dans `uv.lock`.
- Le harness s'exécute entièrement dans un conteneur Docker (Colima sur le poste). La clé API est lisible depuis le conteneur : risque accepté au début, à traiter dans une itération dédiée.
- Tests : uniquement des tests de comportement du harness (ce que voit l'utilisateur ou le modèle), jamais fonction par fonction. Un test ne doit pas casser à chaque petite modification interne. Peu de tests, mais pertinents.
- Fiches de notion (`docs/notions/`) : notes **génériques**, destinées à être copiées telles quelles dans le second cerveau Obsidian de l'utilisateur. Format et style du skill `technical-knowledge-note-generator` (frontmatter, structure « concept », français, sans liste numérotée, 4 sources maximum). Aucune référence au projet : pas de « notre harness », « la v0 », « l'itération N », d'ADR, de numéros de test (T-xxxx) ou de CA-xx, de chemins du dépôt. Les apprentissages tirés du projet s'intègrent au fond de la note, formulés comme des connaissances générales (piège, pattern, limite), sans dire qu'ils viennent d'ici. Ce qui est propre au projet (décisions, état de la v0, pièges rencontrés, renvois aux ADR et aux tests) va dans `docs/journal/NNN-<iteration>.md` et dans les ADR, jamais dans la fiche. Relecture avant de rendre : chercher dans la fiche les mots « ADR », « T-0 », « CA-», « v0 », « itération », « notre ».
- Fiches de veille : suivre la grille `docs/veille/_grille.md`, marquer chaque affirmation [vérifié] ou [déduit].

## Commandes

- Installer : `uv sync`
- Lancer : à définir à la v0.
- Lint / format : `uv run ruff check .` / `uv run ruff format .` (à ajouter à la v0)
- Types : `uv run pyright` (à ajouter à la v0)
- Tests : `uv run pytest` (à ajouter à la v0)

## Pièges

- Ce dossier a son propre dépôt Git, imbriqué dans `~/Documents/code` : lancer les commandes Git depuis ce dossier.
- `docs/veille/` reflète l'état des harness à la date de l'étude ; ces outils évoluent chaque mois.
