# ADR-0008 — Découpage en modules et points d'entrée testables

Statut : proposé ; §5 complété par ADR-0012 (`/resume`, `/branch`, options de lancement) · Spec : §5, §8, §9 q.3 · Notion : `boucle-agent`

## Contexte

Les tests vérifient des comportements visibles (ce que voient l'utilisateur et le modèle), de bout en bout, avec un modèle simulé et les vrais outils, sans toucher au code interne. Il faut des points d'entrée stables qui l'autorisent, un noyau sans E/S, et une structure lisible pour un lecteur qui apprend.

## Décision

1. **Paquet `src/harness/`** (layout `src`), remplaçant le `main.py` actuel. Dépendances : `litellm` (version figée), `jsonschema`. Stdlib pour le reste (`tomllib`, `argparse`, `asyncio`). Pas de bibliothèque d'affichage en v0 (texte brut ; `rich`/Textual arrivent à l'it. 12).

   ```
   src/harness/
     events.py        événements typés (noyau → interface)
     config.py        chargement et validation (ADR-0007)
     prompt.py        prompt système court, en sections nommées
     session.py       Session : historique, limites, run_turn / resume_turn (ADR-0001)
     cost.py          CostTracker (ADR-0004)
     models/
       base.py        protocole ModelClient, ModelResponse, ProviderError
       litellm_client.py   adaptateur LiteLLM, check(), coût (ADR-0003/0004)
     tools/
       base.py        Tool, ToolResult, ToolRegistry (ADR-0002)
       environment.py Environment + LocalEnvironment (shell, timeout, kill)
       read_file.py · write_file.py · shell.py
     cli/
       repl.py        boucle de lecture, commandes de session, « continuer ? »
       render.py      événement → ligne-titre ou détail
       main.py        argparse, garde conteneur, câblage réel
   ```
2. **Sens des dépendances** : `cli → session → {models.base, tools, cost}`. `session` et `tools` n'importent ni `cli` ni `litellm`. Seuls `litellm_client.py` importe `litellm` ; seul `main.py` lit l'environnement et câble les vraies implémentations. Le noyau n'appelle jamais `print` ni `input`.
3. **Points d'entrée pour les tests de bout en bout** :
   - `Session(config, client, environment)` + `async for event in session.run_turn(text)` / `resume_turn(grant)` : pilote la boucle et lit les événements (comportement visible de la boucle) ;
   - `cli.repl.run(config, client_factory, read_line, write)` : le REPL complet, avec `read_line` (comportement de `input`, peut lever `EOFError`/`KeyboardInterrupt`), `write` (sortie texte) et `client_factory(profil) -> ModelClient` injectables. Un test écrit les lignes tapées, lit le texte affiché, et inspecte les messages que le modèle simulé a reçus.
   - Le modèle simulé (`ScriptedModel`) est une aide de test qui implémente `ModelClient` (réponses prédéfinies, coût `float | None`, erreurs injectables) ; il n'est pas du code de production.
   - `cli.main` n'est testé qu'en validation humaine (garde conteneur, câblage).
4. **Événements** (liste de départ) : `ToolCallStarted(name, arguments)`, `ToolCallFinished(name, result)`, `AssistantMessage(text)`, `StepCompleted(usage, cost)`, `LimitReached(kind, summary)`, `ProviderFailed(error)`, `TurnEnded(reason)`. `render.py` en tire la ligne-titre (CA-12) ou le détail complet (CA-13) ; le mode détaillé est un état du REPL, pas du noyau.
5. **Commandes de session** (spec §9 q.3) :

   | Commande | Effet |
   |---|---|
   | `/quit` (ou Ctrl+D) | quitte, affiche le coût total (CA-3) |
   | `/detail` | bascule titres ↔ détail complet (CA-13) |
   | `/model <alias>` | change de modèle (CA-24) ; sans argument : liste les alias et indique l'actif |

   Toute ligne commençant par `/` qui n'est pas une commande connue affiche la liste des commandes et n'est pas envoyée au modèle. Pas de `/help` séparé en v0.
6. **Démarrage** : charge la config → `--model` → `client.check()` → affiche dossier de travail, modèle actif, limites, budget (CA-1) → invite.
7. **Outillage** : `ruff`, `pyright`, `pytest` (+ `pytest-asyncio` ou équivalent) en dépendances de développement ; tests dans `tests/`.

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. Noyau sans E/S + REPL injectable + modèle simulé au protocole** (retenue) | tests de comportement stables, TUI/API réutilisent `Session` | injection de quelques fonctions dans le REPL |
| B. Tester via `subprocess` et un faux serveur HTTP | plus « réel » | lent, fragile, signaux et pty compliqués |
| C. Patch de `litellm` / `input` dans les tests | pas d'injection | tests couplés à l'implémentation, casse à chaque refactoring |
| D. Découpage technique (`models/`, `utils/`…) sans séparation noyau/interface | plus court | interface mêlée au noyau ; réécriture avant la TUI |

## Conséquences

- Les tests de la spec (CA-1 à CA-24) passent par `Session` et `cli.repl.run` ; ils ne dépendent ni des noms de fonctions internes ni du format exact des lignes hors ce que la spec décrit.
- `ScriptedModel` et les aides de test appartiennent au `test-writer` ; la session d'implémentation écrit seulement le protocole.
- L'affichage exact des lignes-titres n'est pas un contrat figé au-delà de CA-12/13 : un test cherche l'absence des arguments/résultats complets en mode titre, et leur présence en mode détaillé.
- Quand la TUI (it. 12) arrivera, elle consomme le même flux d'événements.
