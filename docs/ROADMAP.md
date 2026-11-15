# Feuille de route

**Statut : validée le 2026-11-15.** Elle découle de la [synthèse de veille](veille/synthese.md) et peut être révisée entre deux itérations.

Chaque itération suit le cycle décrit dans `CLAUDE.md` : fiche(s) de notion → implémentation → journal → grill de fin d'itération. Le niveau de rigueur (tests, revues) est fixé au cadrage de chaque itération.

Ordre retenu : d'abord un agent qui marche de bout en bout, puis ce qui le rend fiable sur une vraie tâche (outils, sessions, sécurité), puis ce qui le fait tenir sur des tâches longues (contexte, compaction), enfin l'extensibilité, les interfaces riches et la mesure.

## Phase 1 — Un agent qui marche

### It. 1 — v0 : la boucle agent
- **Notions :** `boucle-agent`, `tool-calling`, `prompt-systeme`, `conteneur-frontiere`.
- **Fonctionnalités :**
  - REPL dans le terminal ;
  - LiteLLM avec Anthropic et un provider compatible OpenAI (`mlx_lm.server` en local) ;
  - boucle bornée (`max_turns`, budget) ;
  - outils `read_file`, `write_file`, `shell` ;
  - événements typés ;
  - erreurs d'outil renvoyées au modèle ;
  - coût affiché ;
  - prompt système court en sections ;
  - harness lancé dans un conteneur Docker basique.
- **Inspirations :** Pi (boucle, prompt, échec sur `length`), Claude Code (plafonds, résultat typé), Hermes (`BaseEnvironment`).

### It. 2 — Concevoir de bons outils
- **Notions :** `conception-outils` (interface agent-machine), `edition-de-fichiers`, `troncature-des-sorties`.
- **Fonctionnalités :**
  - `edit_file` par remplacement exact (unicité, lecture préalable), puis appariement tolérant ;
  - troncature au milieu avec en-tête et débordement sur disque ;
  - normalisation des arguments ;
  - registre d'outils et toolsets ;
  - descriptions d'outils travaillées.
- **Inspirations :** Claude Code (édition, erreurs qui guident), Pi (paires `oldText`/`newText`, normalisation), Codex (troncature au milieu), Hermes (registre, débordement disque).

### It. 3 — Sessions et mode headless
- **Notions :** `etat-et-sessions`, `mode-headless`.
- **Fonctionnalités :**
  - journal JSONL en ajout seul (`id`/`parentId`) ;
  - reprise d'une session ;
  - mode non interactif (prompt en argument, sortie texte ou JSONL) pour scripter.
- **Inspirations :** Pi (sessions en arbre, modes print/JSONL), Codex (journal distinct de l'historique en mémoire).

### It. 4 — Sécurité et permissions
- **Notions :** `securite-des-agents`, `permissions-et-approbation`, `sandbox-docker`, `injection-de-prompt`.
- **Fonctionnalités :**
  - deux axes : politique de sandbox × politique d'approbation ;
  - règles `deny > ask > allow` sur les préfixes de commandes, avec découpage des commandes composées ;
  - chemins protégés montés `:ro` ;
  - durcissement Docker (`cap-drop ALL`, `no-new-privileges`, limites) ;
  - réseau coupé ou sur liste blanche ;
  - gel des drapeaux de contournement ;
  - hooks `before_tool` et `after_tool`.
- **Inspirations :** Codex (axes, escalade, règles testées), Claude Code (ordre des règles, modes), Hermes (recette Docker, gel des drapeaux).

## Phase 2 — Un agent qui tient sur la durée

### It. 5 — Contexte projet et prompt caching
- **Notions :** `context-engineering`, `prompt-caching`.
- **Fonctionnalités :**
  - `AGENTS.md` hiérarchique avec budget, et scan d'injection ;
  - préfixe stable ;
  - environnement et rappels injectés par messages ;
  - `cache_control` via LiteLLM ;
  - statistiques de cache ;
  - test de « surface du prompt ».
- **Inspirations :** Hermes (invariant du préfixe, test de surface), Claude Code (hiérarchie, ordonnancement), Codex (messages contextuels).

### It. 6 — Compaction
- **Notions :** `fenetre-de-contexte`, `compaction`.
- **Fonctionnalités :**
  - élagage des vieux résultats d'outils ;
  - bornes qui ne coupent jamais un groupe appel d'outil / résultat ;
  - résumé de passation par un modèle auxiliaire moins cher ;
  - compaction manuelle puis à seuil.
- **Inspirations :** Hermes (4 phases), Codex (résumé de passation), Pi (entrée de compaction qui n'efface rien).

### It. 7 — Fiabilité et multi-provider
- **Notions :** `abstraction-multi-provider`, `fiabilite-et-reprise`, `parallelisme-des-outils`.
- **Fonctionnalités :**
  - classification d'erreurs et retries par type ;
  - modèles de repli ;
  - table des capacités par modèle ;
  - interruption propre (Ctrl-C) ;
  - outils en lecture seule exécutés en parallèle (verrou lecteurs/écrivain) ;
  - comparaison Claude, GPT et modèles locaux sur les mêmes tâches.
- **Inspirations :** Codex (retries, verrou lecteurs/écrivain), Hermes (échelle de reprise), Pi (passage d'un modèle à l'autre).

## Phase 3 — Un agent extensible

### It. 8 — Skills
- **Notions :** `skills-et-divulgation-progressive`.
- **Fonctionnalités :** catalogue `SKILL.md`, chargement à la demande, commandes `/nom-du-skill`.
- **Inspirations :** Claude Code, Hermes, Pi.

### It. 9 — Sous-agents
- **Notions :** `sous-agents`, `isolation-de-contexte`.
- **Fonctionnalités :** sous-agents définis en Markdown, outils restreints, modèle propre ; seul un résumé remonte.
- **Inspirations :** Claude Code.

### It. 10 — Mémoire long terme
- **Notions :** `memoire-des-agents`.
- **Fonctionnalités :** fichiers mémoire plafonnés, injectés figés au démarrage ; outil `memory` ; recherche plein texte dans les sessions (SQLite FTS5).
- **Inspirations :** Hermes.

### It. 11 — MCP
- **Notions :** `mcp`, `outils-differes`.
- **Fonctionnalités :** client MCP, puis chargement différé des outils quand ils deviennent nombreux.
- **Inspirations :** Claude Code, Hermes.

## Phase 4 — Interfaces et mesure

### It. 12 — TUI
- **Notions :** `interface-agent`.
- **Fonctionnalités :**
  - TUI Textual branchée sur le flux d'événements ;
  - affichage des diffs ;
  - file de messages pendant l'exécution (pilotage).
- **Inspirations :** Pi (files de pilotage et de suite), Codex.

### It. 13 — API serveur
- **Notions :** `harness-as-a-service`.
- **Fonctionnalités :**
  - serveur HTTP/SSE ;
  - sessions multiples ;
  - mode sans humain (`dontAsk` / refus par défaut).
- **Inspirations :** Codex (app-server), Hermes (contrat d'adaptateur).

### It. 14 — Évaluation et observabilité
- **Notions :** `evaluation-des-agents`, `observabilite`.
- **Fonctionnalités :** traces, tableau de bord des coûts, benchmark public (Terminal-Bench ou SWE-bench Lite) pour se situer.
- **Inspirations :** Pi (Terminal-Bench), Claude Code (évaluation par transcripts).

### It. 15 — Secrets hors du conteneur
- **Notions :** `gestion-des-secrets`.
- **Fonctionnalités :** proxy d'identifiants hors du conteneur, OAuth ou coffre-fort, clé API absente de l'environnement de l'agent.
- **Inspirations :** Claude Code (proxy), Hermes (liste blanche `forward_env`).

## Réserve d'idées (non planifiées)

- Points de contrôle des fichiers et retour arrière (Claude Code, Hermes).
- Shell à sessions persistantes (Codex `unified_exec`).
- Exécution de code qui appelle les outils (Hermes `execute_code`).
- Création automatique de skills avec curator (Hermes).
- Réviseur d'actions par un LLM (Codex guardian).
- Fichiers de progression pour les tâches longues (Claude Code).
