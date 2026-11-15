# Harness Engineering Sandbox

Un dépôt pour apprendre le harness engineering en le pratiquant : comprendre ce qui entoure un LLM pour en faire un agent fiable (boucle, outils, contexte, mémoire, permissions, sandbox, évaluation), et construire pas à pas son propre harness en Python.

## Contenu

- `docs/veille/` : analyse des harness existants (Claude Code, Codex, Hermes Agent, Pi), selon une grille commune, et leur synthèse comparative.
- `docs/notions/` : une fiche par notion de harness engineering.
- `docs/journal/` : ce que chaque itération a appris.
- `docs/ROADMAP.md` : l'ordre des itérations.
- Le code du harness (à partir de la v0).

## État

Panorama de veille terminé ([synthèse](docs/veille/synthese.md)). Itération 1 (v0, boucle agent) implémentée : REPL, outils `read_file` / `write_file` / `shell`, LiteLLM, limites d'étapes et de budget, Ctrl+C, conteneur Docker. Spec : [`specs/001-v0-boucle-agent.md`](specs/001-v0-boucle-agent.md) ; décisions : [`docs/adr/`](docs/adr/).

## Lancer le harness

Le harness ne s'exécute que dans son conteneur, sur le dossier courant monté en `/workspace`.

```bash
mkdir -p ~/.config/harness && cp config.example.toml ~/.config/harness/config.toml
docker build -f docker/Dockerfile -t harness .
export ANTHROPIC_API_KEY=...        # ou la variable nommée par api_key_env dans la config
cd <dossier de travail> && <chemin du dépôt>/bin/harness [--model <alias>]
```

Pendant une session, les sorties de commande trop longues sont enregistrées dans `.harness/outputs/` du dossier de travail (exclu de Git par son propre `.gitignore`, supprimé à la sortie). La clé `[tools] toolset` choisit les outils exposés au modèle : `full` (défaut) ou `read_only`.

Développement : `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run pyright`.
