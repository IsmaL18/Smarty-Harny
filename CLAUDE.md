# CLAUDE.md

Projet d'apprentissage du harness engineering : une base de connaissance (`docs/`) et un harness d'agent LLM en Python, construit par itérations.

## Objectifs

1. Construire un harness solide et utilisable : un noyau générique (boucle agent, outils, contexte, permissions) dont le premier profil est un agent de code.
2. Consigner chaque notion apprise pour la réutiliser en mission Gen AI.

## Cycle d'une itération

1. Choisir la notion dans `docs/ROADMAP.md`.
2. Écrire ou compléter la fiche `docs/notions/<notion>.md` à partir de la veille (`docs/veille/`).
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
