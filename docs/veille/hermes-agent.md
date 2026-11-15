# Veille : Hermes Agent (Nous Research)

Convention de sources : `C:chemin` désigne un fichier du dépôt `NousResearch/hermes-agent` au commit `77a30e9` (cloné le 2026-11-15, `git clone --depth 1`, code lu, jamais exécuté). `D:chemin` désigne un fichier de la documentation embarquée dans le dépôt (`website/docs/...`, source du site hermes-agent.nousresearch.com/docs). Marqueurs : **[vérifié]** = lu dans le code ou la doc officielle ; **[déduit]** = interprétation ou source secondaire.

## 1. Identité

| Champ | Valeur |
|---|---|
| Éditeur | Nous Research **[vérifié]** (`C:LICENSE` : « Copyright (c) 2025 Nous Research ») |
| Licence | MIT **[vérifié]** (`C:LICENSE`) |
| Langage | Python `>=3.11,<3.15` pour le noyau **[vérifié]** (`C:pyproject.toml`) ; TypeScript pour le TUI, le desktop et le dashboard (`C:ui-tui/`, `C:apps/`, `C:web/`) **[vérifié]** |
| Dépôt | https://github.com/NousResearch/hermes-agent (URL confirmée par recherche web et par le clone) **[vérifié]** |
| Commit étudié | `77a30e9127998c0277306c361663f63c0694b88b`, daté 2026-11-15 **[vérifié]** |
| Version | `pyproject.toml` indique `version = "0.0.0"` (la version réelle n'est pas portée par ce champ) **[vérifié]**. Sources secondaires : v0.1.0 le 25 février 2026, v0.5.0, v0.10 le 16 avril 2026, tag `v2026.7.7` **[déduit]**, non recoupés avec des tags (clone superficiel, aucun tag) |
| Date de l'étude | 2026-11-15 |
| Taille du code | ~26 100 fichiers dans l'arbre de travail, ~8 500 fichiers Python de test (`find tests -name '*.py'`), ~25 000 tests annoncés **[vérifié]** (`D:developer-guide/architecture.md`) ; `agent/` seul pèse ~146 000 lignes **[vérifié]** (`wc -l`) |

Remarque d'échelle : ce n'est pas un petit projet lisible en une heure. Le dépôt est un produit complet (CLI, TUI, appli Electron, dashboard web, passerelle de 25+ plateformes, cron, kanban, mode « bot desktop »). Pour notre apprentissage, la valeur est dans les **invariants de conception**, bien documentés dans les `AGENTS.md`, pas dans la copie du code.

## 2. Philosophie et positionnement

- **Agent personnel unique, multi-surface** : « un noyau d'agent à travers CLI, TUI, appli desktop, dashboard web, éditeurs ACP et passerelle de messagerie (25+ plateformes) », étendu « par plugins et skills, pas en faisant grossir le noyau » **[vérifié]** (`C:AGENTS.md`, section « What Hermes Is »).
- **Deux invariants déclarés comme « lentille de revue » de tout changement** **[vérifié]** (`C:AGENTS.md`) :
  1. *Le prompt caching par conversation est sacré.* Muter le contexte passé, changer les toolsets, recharger la mémoire ou reconstruire le prompt système en cours de conversation casse le préfixe en cache. Seule exception : la compaction du contexte.
  2. *Le noyau est une « taille étroite » (narrow waist), les capacités vivent aux bords.* Chaque outil du modèle est envoyé à chaque appel API, donc le seuil d'ajout d'un outil core est élevé.
- **Échelle d'empreinte (« footprint ladder »)** pour toute nouvelle capacité : étendre le code existant → commande CLI + skill → outil conditionné par service (`check_fn`) → plugin → serveur MCP du catalogue → nouvel outil core en dernier recours **[vérifié]** (`C:AGENTS.md`).
- **Auto-amélioration** : l'agent écrit ses propres skills depuis l'expérience et une revue de fond peut mettre à jour mémoire et skills après un tour **[vérifié]** (`C:agent/background_review.py`, `D:user-guide/features/skills.md`). C'est le principal argument marketing (« self-improving agent » sur PyPI, d'après la recherche web) **[déduit]**.
- **Modèle agnostique** : « harness d'agent open source indépendant du modèle », distinct de la famille de modèles Hermes du même éditeur **[déduit]** (sources secondaires). Les profils de provider sont des plugins (`C:providers/README.md`) **[vérifié]**.
- **Rigueur d'ingénierie assumée** : plafonds de complexité par fonction (CC ≤ 20, ≤ 300 lignes, fichiers ≤ 2 000 lignes), lints maison `HX0xx`, test de « surface du prompt » en CI, rubrique de contribution qui rejette des PR « bien faites » (nouvel outil core si terminal + fichiers suffisent, variables d'env pour de la config non secrète…) **[vérifié]** (`C:AGENTS.md`).

Positionnement par rapport à notre projet : Hermes est un **agent généraliste de longue durée** (mémoire, cron, messagerie) là où nous visons d'abord un profil agent de code dans un conteneur. Il porte néanmoins un « posture de code » (`_CODING_TOOLS`, `C:toolsets.py`) **[vérifié]**.

## 3. Architecture globale

### 3.1 Composants **[vérifié]** (`D:developer-guide/architecture.md`, `C:AGENTS.md`)

```text
Points d'entrée : CLI (cli.py) | Passerelle (gateway/run.py) | ACP (acp_adapter/) | batch_runner | API server | lib Python
                          │
                  AIAgent (run_agent.py, façade)
   prompt_builder │ résolution provider │ dispatch outils (model_tools.py) │ compaction │ cache prompt
                          │
   Stockage session : SQLite + FTS5 (hermes_state*.py)      Backends d'outils : terminal (local/docker/ssh/modal/daytona/vercel), navigateur, web, MCP
```

- `run_agent.py` (1 581 lignes) est une **façade** : `AIAgent` est assemblé par mixins ; la boucle vit dans `agent/conversation_loop.py` (1 972 lignes) et une vingtaine de modules `agent/turn_*.py`, un par phase **[vérifié]** (`C:agent/AGENTS.md`).
- **Layout « façade + siblings »** généralisé : chaque ancien « god file » devient une façade plus des fichiers `<stem>_<sujet>.py` (ex. `hermes_state_*.py`, une centaine de fichiers, `tools/approval_*.py`, `tools/mcp_tool_*.py`) **[vérifié]** (`C:AGENTS.md`). Règle associée : « les siblings importent la façade tardivement, dans les fonctions, jamais de cycle au niveau module ».
- **Chaîne de dépendances** : `tools/registry.py` (sans dépendance) ← `tools/*.py` (s'enregistrent à l'import) ← `model_tools.py` (déclenche la découverte) ← `run_agent.py`, `cli.py`, `batch_runner.py` **[vérifié]** (`D:developer-guide/architecture.md`).
- **Séparation noyau / interface** : un seul `AIAgent` sert CLI, passerelle, ACP, batch, API ; les différences de plateforme vivent dans le point d'entrée, via des callbacks (`tool_progress_callback`, `stream_delta_callback`, `clarify_callback`, `step_callback`…) **[vérifié]** (`D:developer-guide/agent-loop.md`).
- **Profils** : `hermes -p <nom>` donne un `HERMES_HOME` propre (config, mémoire, sessions). Un même processus de passerelle peut servir plusieurs profils (« multiplex »), d'où une discipline de portée (`get_hermes_home()` jamais `~/.hermes` en dur, `ContextVar` pour la portée) **[vérifié]** (`C:AGENTS.md`).
- **Flux CLI** : entrée → `AIAgent.run_conversation()` → prompt système → résolution du provider → appel API → outils ? boucle → réponse → écriture en `SessionDB` **[vérifié]** (`D:developer-guide/architecture.md`).
- **Flux cron** : un `AIAgent` neuf sans historique, skills attachés injectés, livraison sur la plateforme cible **[vérifié]** (idem).

### 3.2 Remarque pour nous

Le découpage « une phase de tour = un module » est lisible mais produit une très grande surface (146 000 lignes pour `agent/`). Pour notre noyau, on retient l'idée (phases nommées, testables isolément), pas la granularité **[déduit]**.

## 4. Boucle agent

### 4.1 Forme **[vérifié]** (`C:agent/AGENTS.md`)

Boucle **entièrement synchrone**, avec vérification d'interruption, budget d'itérations et un appel de grâce :

```python
while (
    api_call_count < self.max_iterations and self.iteration_budget.remaining > 0
) or self._budget_grace_call:
    if self._interrupt_requested:
        break
    response = client.chat.completions.create(
        model=model, messages=messages, tools=tool_schemas
    )
    if response.tool_calls:
        for tc in response.tool_calls:
            messages.append(
                tool_result_message(handle_function_call(tc.name, tc.args, task_id))
            )
        api_call_count += 1
    else:
        return response.content
```

(version volontairement simplifiée dans la doc ; la vraie est répartie sur `turn_preflight*`, `turn_iteration_prep`, `turn_request_assembly`, `turn_api_call`, `turn_api_error`, `turn_response_intake`, `turn_tool_round`, `turn_overflow`, `turn_truncation`, `turn_recovery*`, `turn_stop_gates`, `turn_finalizer`, etc.)

- Deux points d'entrée : `chat(message) -> str` et `run_conversation(user_message, system_message, conversation_history, task_id) -> dict` (`final_response` + `messages`) **[vérifié]**. `AIAgent.__init__` prend ~60 paramètres **[vérifié]**.
- Budget : `max_iterations` par défaut **500**, sous-agents avec budget propre plafonné à `delegation.max_iterations` (50) **[vérifié]** (`D:developer-guide/agent-loop.md`).

### 4.2 Trois modes d'API, un format interne unique **[vérifié]** (`D:developer-guide/agent-loop.md`)

`chat_completions` (OpenAI-compatible, la grande majorité), `codex_responses` (API Responses), `anthropic_messages` (natif via adaptateur). Tous convergent vers le format interne OpenAI (`role`/`content`/`tool_calls`) ; le raisonnement est stocké dans `assistant_msg["reasoning"]`. Résolution du mode : argument explicite > détection par provider > heuristique d'URL > défaut `chat_completions`.

### 4.3 Invariants de flux de messages (revus à chaque changement) **[vérifié]** (`C:agent/AGENTS.md`)

- Prompt système **stable octet pour octet** pendant toute la conversation ; seule la compaction le mute.
- Tout contenu à injecter en cours de route passe par un **message utilisateur ou un résultat d'outil**, jamais le prompt système (ex. les hints de sous-répertoire `AGENTS.md` sont ajoutés au résultat d'outil, tronqués à 32 000 caractères tête+queue).
- **Alternance stricte des rôles** : jamais deux messages de même rôle consécutifs, jamais de message utilisateur synthétique en milieu de boucle. Seule exception : `/steer`, livré comme ligne utilisateur autonome après un résultat d'outil.

### 4.4 Exécution des outils **[vérifié]** (`C:agent/tool_executor.py`, `D:developer-guide/agent-loop.md`)

- Un seul appel : exécution directe. Plusieurs : `ThreadPoolExecutor` concurrent (`DaemonThreadPoolExecutor`), résultats réinsérés **dans l'ordre d'origine** quelle que soit la complétion. Une liste `_NEVER_PARALLEL_TOOLS` (ex. `clarify`, interactif) force le séquentiel. Un « start-order gate » garantit l'ordre de démarrage.
- Timeouts séquentiel et concurrent configurables (`_resolve_concurrent_tool_timeout`, `_resolve_sequential_tool_timeout`), heartbeat d'activité pendant les outils longs, résultats « abandonnés/non terminés » synthétisés si dépassement (`_unfinished_tool_result`).
- Pipeline par outil : hook `pre_tool_call` → garde d'approbation → `handler(args, task_id)` → hook `post_tool_call` → message `tool`. Les outils « niveau agent » (`todo`, `memory`, `session_search`, `delegate_task`) sont interceptés **avant** le registre via une table `INLINE_TOOL_EXECUTORS` (pas de chaîne de `if name == ...`) **[vérifié]**.
- Un appel d'outil invalide est refusé par `tools/arg_validation.py` avant le handler ; les exceptions sont renvoyées au modèle sous forme `{"error": ...}`, assainies (`_sanitize_tool_error`) **[vérifié]** (`C:tools/registry.py::dispatch`).

### 4.5 Interruption **[vérifié]** (`D:developer-guide/agent-loop.md`)

L'appel API tourne dans un thread de fond pendant que le thread principal attend « réponse prête / événement d'interruption / timeout » (`_interruptible_api_call`). À l'interruption (nouveau message, `/stop`, signal) le thread API est abandonné, la réponse jetée, **aucune réponse partielle n'est injectée dans l'historique**. Un échafaudage de reprise (`[This response was interrupted by a user correction.]`) rejoue le texte déjà visible dans la ligne utilisateur suivante (`C:agent/conversation_loop.py`, l.74, 328-352).

### 4.6 Erreurs, retries, fallback **[vérifié]**

- Classification d'erreurs dédiée (`C:agent/error_classifier.py`, 1 759 lignes) et échelle de reprise (`turn_recovery`, `turn_recovery_autorecover` : attente et nouvel essai après épuisement).
- **Fallback de modèle** : sur 429, 5xx, 401/403, bascule sur la liste `fallback_providers` de la config, avec tentative de rafraîchissement de credential sur 401/403 ; chaînes de fallback **séparées** pour les tâches auxiliaires (vision, compression, titre) **[vérifié]** (`D:developer-guide/agent-loop.md`).
- **Pool de credentials** (`C:agent/credential_pool.py`, 2 966 lignes) avec rotation **[vérifié]**.
- Un tour qui bloque en « raisonnement seul » trois continuations d'affilée bascule sur le fallback, avec un unique appel de grâce borné **[vérifié]** (idem).
- À 100 % du budget, l'agent s'arrête et renvoie un résumé du travail fait (`MAX_ITERATIONS_SUMMARY_REQUEST`, `C:agent/chat_completion_helpers.py` l.2276) **[vérifié]**.

### 4.7 Streaming **[vérifié]**

Streaming optionnel via `stream_delta_callback` (jetons) et `tool_gen_callback` (appel d'outil parsé depuis le flux) ; modules dédiés `agent/stream_delivery*`. Détail non lu ligne à ligne.

## 5. Prompt système

### 5.1 Construction **[vérifié]** (`D:developer-guide/prompt-assembly.md`, `C:agent/system_prompt.py`, `C:agent/prompt_builder.py`)

Assemblé en **trois niveaux ordonnés** `stable → context → volatile`, puis mis en cache pour la session :

1. **stable** : identité (`SOUL.md` ou identité par défaut), guidage outils/modèle, « coding operating brief », index des skills.
2. **context** : message système fourni par l'appelant, fichiers de contexte projet (`.hermes.md` / `AGENTS.md` / `CLAUDE.md` / `.cursorrules`), instantané du workspace git, consignes opérateur, hints de plateforme.
3. **volatile** : instantané `MEMORY.md`, instantané `USER.md`, bloc du fournisseur de mémoire externe, ligne horodatage/session/modèle/provider, puis environnement d'exécution (hôte, home, **cwd**).

Détail fin : dans le niveau context, les fichiers projet partagés viennent **avant** tout ce qui nomme le worktree courant, pour que des sessions du même projet dans des worktrees différents partagent le plus long préfixe possible côté cache provider **[vérifié]**.

### 5.2 Taille et contenu

- `agent/prompt_builder.py` fait 1 785 lignes, `agent/system_prompt.py` 896 ; la taille effective du prompt n'a pas été mesurée **[non vérifié]**. Un snapshot CI du prompt et de `tools[]` est versionné (`tests/fixtures/prompt_surface/`, `scripts/ci/prompt_surface.py render`) et toute modification du prompt par défaut ou des schémas d'outils casse `tests/ci/test_prompt_surface.py` tant que le snapshot n'est pas mis à jour **[vérifié]** (`C:AGENTS.md`). C'est un excellent garde-fou.
- `SOUL.md` du dépôt : une seule ligne de ton (« direct, réponse à l'échelle de la demande, pas de remplissage… ») **[vérifié]** (`C:SOUL.md`). Le prompt réel est donc surtout composé de blocs de guidage dans le code.
- Consigne de rappel de session : « quand l'utilisateur référence une conversation passée, utilise `session_search` avant de lui demander de répéter » ; renforcement « tool-use enforcement » pour les modèles GPT/Codex uniquement **[vérifié]** (`D:developer-guide/prompt-assembly.md`).

### 5.3 Dynamique sans casser le cache

- Les changements de plateforme (desktop ↔ TUI) livrent leur guidage par une **note ponctuelle sur le canal du message utilisateur** (`agent/surface_switch.py`) plutôt que de réécrire le prompt **[vérifié]**.
- Les deltas de l'index des skills (ajout/suppression pendant la session) suivent le même canal (`agent/skills_index_delta.py`) ; l'index converge à la prochaine compaction **[vérifié]**.
- Fichiers de contexte : chargés depuis le cwd **au démarrage seulement**, plafonnés (`CONTEXT_FILE_MAX_CHARS` / cap dynamique selon la fenêtre) ; **scannés contre l'injection de prompt** : un match **bloque** le chargement (`_scan_context_content`, `C:agent/prompt_builder.py` l.84), sauf `SOUL.md` de l'utilisateur (avertissement seulement) **[vérifié]**.

## 6. Outils

### 6.1 Enregistrement **[vérifié]** (`C:tools/registry.py`, `C:tools/AGENTS.md`)

- Chaque `tools/*.py` appelle `registry.register(...)` **à l'import**. `discover_builtin_tools()` détecte les modules par **analyse AST** (`_module_registers_tools`) : tout fichier avec un appel `registry.register()` de niveau module est importé, sans liste manuelle ; cache de découverte sur disque.
- Signature : `register(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description, emoji, max_result_size_chars, dynamic_schema_overrides, override, scope, execution_timeout, compat_args, self_checked_args)`.
- Le schéma est **validé à l'enregistrement** (un `parameters` non dict ferait échouer toute la requête provider ; on veut nommer le coupable tôt).
- `ToolEntry` est un dataclass ; `check_fn` (disponibilité : clé API présente, service joignable) est **mis en cache avec TTL**, par profil, avec timeout (`CheckFnTimeout`).
- Convention : **tous les handlers renvoient une chaîne JSON** (exception : l'enveloppe multimodale `{"_multimodal": True, "content": [...], "text_summary": ...}`).
- **Règle de schéma** : une description d'outil ne doit jamais nommer un outil d'un autre toolset (il peut être indisponible, le modèle halluciner l'appel). Les renvois sont ajoutés dynamiquement dans `get_tool_definitions()` **[vérifié]**.
- Portées : overlay de portée de session (`session_tool_scope`, `ContextVar`) additif au registre du profil ; un plugin ne peut remplacer un outil natif qu'avec `override=True` et l'opt-in de l'opérateur **[vérifié]**.

### 6.2 Toolsets **[vérifié]** (`C:toolsets.py`)

Un dict `TOOLSETS` (`_ts(description, tools, includes)`), un bundle de base `_HERMES_CORE_TOOLS` hérité par chaque plateforme, des toolsets nommés (`web`, `terminal`, `file`, `skills`, `memory`, `session_search`, `delegation`, `code_execution`, `browser`, `cronjob`, `kanban`, `safe`…), et des **postures** : `_CODING_TOOLS` = noyau sans messagerie, TTS, génération d'image, cron, computer-use. Un toolset webhook « sûr » (`_HERMES_WEBHOOK_SAFE_TOOLS` = recherche web, extraction, vision, clarify) car « les payloads de webhook sont du contenu tiers non fiable ». Activation par plateforme via `hermes tools` ou `tools.<platform>.enabled/disabled` dans `config.yaml`. Un outil n'est exposé que si un toolset le nomme **et** si son `check_fn` passe.

### 6.3 Liste (noyau) **[vérifié]** (`C:toolsets.py::_HERMES_CORE_TOOLS`)

`web_search`, `web_extract`, `terminal`, `process_manage`, `read_file`, `write_file`, `patch`, `search_files`, `vision_analyze`, `image_generate`, `skills_list`, `skill_view`, `skill_manage`, `browser_exec` (Python sur CDP), `browser_cdp`, `browser_dialog`, `text_to_speech`, `todo_list`, `memory`, `session_search`, `clarify`, `execute_code`, `delegate_task`, `cronjob_manage`, une dizaine d'outils `kanban_*`, `computer_use`. La doc annonce « 70+ outils, ~28 toolsets » **[vérifié]** (`D:developer-guide/architecture.md`).

### 6.4 Édition de fichiers, shell, recherche

- Outils `read_file` / `write_file` / `patch` / `search_files` (`C:tools/file_tools.py`, `file_operations*.py`, `patch_parser.py`, `fuzzy_match.py` 39 K) : un `patch` à correspondance floue et un parseur de patch dédié existent ; le format exact (remplacement `old_string/new_string` vs patch unifié) n'a pas été vérifié ligne à ligne **[non vérifié]**. Gardes d'écriture (`file_tools_write_guards.py`), suivi de lecture (`file_tools_read_tracking.py`), lint post-édition (`file_operations_lint.py`) **[vérifié]** par les noms de fichiers.
- **Shell** : `terminal` délègue à un backend d'environnement (section 9). Le shell est **persistant** : instantané d'environnement sourcé avant chaque commande, suivi du cwd par marqueur, état conservé entre commandes (`BaseEnvironment.execute`, `C:tools/environments/base.py` l.285-372, `_persist_env`) **[vérifié]**.
- **Troncature locale** : défauts `max_bytes=50 000` (sortie terminal), `max_lines=2000`, `max_line_length=2000`, configurables sous `tool_output` (`C:tools/tool_output_limits.py`) **[vérifié]**.
- **`execute_code` (Programmatic Tool Calling)** : le LLM écrit un script Python qui appelle des outils Hermes par RPC (socket Unix, noyau de session persistant), « seul le stdout du script retourne au LLM » ; effondre des chaînes d'outils en un seul tour d'inférence **[vérifié]** (`C:tools/code_execution_tool.py`).
- **Tool search (divulgation progressive)** : les outils MCP/plugin et un jeu d'outils core déclenchés par événement sont remplacés dans le tableau `tools[]` par trois outils-ponts `tool_search` / `tool_describe` / `tool_call` ; le catalogue est reconstruit sans état à chaque assemblage **[vérifié]** (`C:tools/tool_search.py`).

## 7. Gestion du contexte

### 7.1 Fichiers d'instructions projet **[vérifié]**

`.hermes.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules` du cwd, chargés au démarrage (section 5.3). **Hints de sous-répertoire** : un `AGENTS.md` rencontré dans un sous-dossier pendant le travail est ajouté au résultat d'outil (jamais au prompt), avec rejet des chemins hors du dossier de travail pour ne pas mélanger `~/.codex/AGENTS.md` ou `~/.claude/CLAUDE.md` (`C:agent/AGENTS.md`).

### 7.2 Compaction : deux couches **[vérifié]** (`D:developer-guide/context-compression-and-caching.md`)

- **Hygiène de session côté passerelle** à 85 % de la fenêtre (filet de sécurité entre les tours, estimation grossière ou ancre d'usage persistée).
- **`ContextCompressor` dans la boucle** à **50 %** (configurable, surcharges par modèle), avec compte de jetons réel du provider via une « ancre d'usage » (dernier compte prompt/complétion + estimation des seuls messages ajoutés depuis).
- Interface remplaçable : ABC `ContextEngine` (`should_compress()`, `compress()`, `update_from_response()`, hooks de cycle de vie) ; moteur choisi par `context.engine` ; jamais auto-activé pour un plugin **[vérifié]** (`C:agent/context_engine.py`).

### 7.3 Algorithme en 4 phases **[vérifié]** (idem)

1. **Élagage des vieux résultats d'outils sans appel LLM** : résultats > 200 caractères hors queue protégée remplacés par `[Old tool output cleared to save context space]`.
2. **Bornes** : tête protégée (système + premier échange, `protect_first_n=3`), milieu résumé, queue protégée par budget de jetons (plafonné à 20 % de la fenêtre, `protect_last_n=20` comme minimum borné) ; alignement pour ne **jamais couper un groupe tool_call/tool_result**.
3. **Résumé structuré** par un modèle **auxiliaire** : Goal / Constraints & Preferences / Progress (Done, In Progress, Blocked) / Key Decisions / Relevant Files / Next Steps / Critical Context ; budget = 20 % du contenu, min 2 000, max `min(5 % fenêtre, 12 000)` jetons.
4. **Assemblage** : tête + résumé + queue ; nettoyage des paires orphelines (`_sanitize_tool_pairs`) ; recompression **itérative** (le résumé précédent est mis à jour, pas refait).
- Mode `tail_mode: lean` : queue clampée à 2,5 % de la fenêtre (10 K–25 K), résumé « journal de session » préservant les identifiants, index d'ancres extrait par regex, messages utilisateur cités tels quels, et **pointeur de récupération `session_search`** ; la doc annonce ~49 K conservés au lieu de ~162 K sur des sessions réelles de 500 K jetons, avec un meilleur rappel (`evals/compaction/results/`) **[vérifié que la revendication est dans la doc ; chiffres non reproduits]**.
- Les skills chargés disparus à la compaction portent un marqueur `[SKILL_PRUNED … reload with skill_view(name=…)]` et le résumé se termine par une « Skill Safety Rule » **[vérifié]**.
- Garde-fous : cooldown après échec provider, anti-thrash, la mémoire est **vidangée sur disque avant** compaction, un nouvel identifiant de lignée de session est créé **[vérifié]** (`D:developer-guide/agent-loop.md`). Piège documenté : si le modèle de résumé a une fenêtre plus petite que le modèle principal, le milieu est jeté **sans résumé**.

### 7.4 Troncature et débordement des sorties d'outils **[vérifié]** (`C:tools/tool_result_storage.py`)

Trois couches : plafonds par outil ; `maybe_persist_tool_result` : toute sortie au-dessus du seuil de l'outil est **écrite sur disque** (`$HERMES_HOME/cache/spillover/{id}.txt`) et remplacée par un **aperçu + chemin** (balise `<persisted-output>`) ; `enforce_turn_budget` pour le budget par tour. Le modèle peut relire le fichier.

### 7.5 Prompt caching **[vérifié]** (`D:developer-guide/context-compression-and-caching.md`, `C:agent/prompt_caching.py`)

Stratégie `system_and_3` pour Anthropic : 4 points de rupture `cache_control` (prompt système + 3 derniers messages non système en fenêtre glissante), TTL `5m` par défaut ou `1h`. Aucune fonctionnalité ne doit changer silencieusement de modèle ou de credential en cours de session (coût cache nul). Toute la discipline de la section 4.3 découle de ce choix.

## 8. Mémoire et persistance

### 8.1 Mémoire curée en fichiers **[vérifié]** (`C:tools/memory_tool.py`, `D:user-guide/features/memory.md`)

- Deux fichiers Markdown dans `~/.hermes/memories/` : **`MEMORY.md`** (notes de l'agent, plafond **2 200 caractères**) et **`USER.md`** (profil utilisateur, plafond **1 375 caractères**), entrées séparées par `§`.
- Injectés dans le prompt comme **instantané figé au démarrage de session** ; les écritures en cours de session vont sur disque immédiatement mais n'apparaissent dans le prompt qu'à la session suivante (cache préservé). L'en-tête affiche l'utilisation (« 67 % — 1 474/2 200 »).
- Un seul outil `memory` : actions `add` / `patch` (remplacement d'un fragment par correspondance de sous-chaîne unique) / `remove`, avec `target` obligatoire (`memory` ou `user`) et lots `operations`. Pas d'action `read` (le contenu est déjà dans le prompt). L'ancienne action `replace` a été supprimée car les modèles l'utilisaient comme « chercher-remplacer » et écrasaient d'autres faits.
- **Pas de compaction automatique** : au-delà du plafond l'outil renvoie une erreur actionnable (liste des entrées courantes, nombre de caractères à libérer) et l'agent libère de la place lui-même en **un seul lot**. Verrou de fichier (`fcntl`, `msvcrt` sous Windows) ; contenu scanné (`_scan_memory_content`) ; option `write_approval` pour mettre les écritures en attente de validation humaine (`/memory pending`, `/memory approve all`).
- Piège documenté : un agent par `HERMES_HOME`, sinon deux écrivains « composent » leurs entrées ; petits modèles (< 30 B) qui annoncent « sauvegardé » sans appeler l'outil **[vérifié]**.

### 8.2 Sessions et recherche **[vérifié]** (`D:developer-guide/session-storage.md`, `C:hermes_state_schema.py`, `C:tools/session_search_tool.py`)

- SQLite (`state.db`) avec tables de messages, **FTS5** (`messages_fts`) et une seconde table FTS5 à tokenizer **trigram** pour CJK/sous-chaînes ; sondage de disponibilité de FTS5 au démarrage ; migrations versionnées ; modes de réparation et diagnostics de la base.
- **Lignée de sessions** : la compaction crée une session enfant (parent/enfant) ; compaction « sur place » possible avec un identifiant stable.
- `session_search` : outil à forme unique, mode déduit des arguments : DISCOVERY (`query`, FTS5 dédupliqué par lignée), SCROLL (`session_id` + `around_message_id`), READ, BROWSE. **Aucun appel LLM** ; renvoie de vrais messages de la base, contenu borné (2 000 caractères par message). Les sessions `cron` sont **rétrogradées** dans le classement (sinon leur vocabulaire répétitif écrase les sessions interactives par BM25) ; les sessions de sous-agents/kanban/outils sont masquées.
- Reprise : `/resume`, `hermes chat --resume` ; l'ancre d'usage de jetons est persistée sur la ligne de session pour qu'un processus neuf restaure son estimation.
- **Frontière de session** : toute la mémoire est conçue autour de la fin de session ; sur les passerelles de messagerie une conversation peut durer des semaines (coût, mémoire jamais relue) d'où la recommandation `/new` aux frontières naturelles **[vérifié]**.

### 8.3 Fournisseurs de mémoire externes **[vérifié]** (`C:agent/memory_provider.py`, `C:plugins/memory/`)

ABC `MemoryProvider` (`name`, `is_available()` sans réseau, `initialize(session_id, **kwargs)` avec `hermes_home`, hooks `on_pre_compress`, `on_session_end`…) orchestrée par `MemoryManager` ; **un seul fournisseur externe actif** en plus de la mémoire intégrée (dans le dépôt : `byterover/`, `retaindb/` ; Honcho, Mem0, Hindsight, Supermemory via le catalogue de plugins). Contrat multi-profil strict : nouvelle instance par agent, aucune donnée de profil au niveau module.

### 8.4 Création automatique de skills et revue de fond (la « boucle d'apprentissage ») **[vérifié]**

- **Compteurs** : `_turns_since_memory` et `_iters_since_skill` (`C:agent/agent_init.py` l.1159-1237). Intervalles par défaut : **10** tours pour la mémoire (`nudge_interval`) et **10** itérations d'outils pour les skills (`skills.creation_nudge_interval`).
- **Déclenchement** (`C:agent/codex_runtime.py::_finish_codex_turn`, miroir de la boucle chat) : à la fin d'un tour réussi avec réponse finale non interrompue, si `0 < _skill_nudge_interval <= _iters_since_skill` et que `skill_manage` est disponible, le compteur est remis à zéro et `_spawn_background_review(messages_snapshot, review_memory, review_skills)` est appelé.
- **La revue** (`C:agent/background_review.py`) : un **thread démon** rejoue un instantané de la conversation dans un `AIAgent` **forké** qui hérite du runtime vivant (provider, modèle, credentials, **prompt système en cache**, donc les mêmes préfixes) sous une **liste blanche d'outils côté dispatch** ; il écrit directement dans les stockes de mémoire et de skills ; la conversation principale et son cache ne sont jamais touchés. Trois prompts : `_MEMORY_REVIEW_PROMPT`, `_SKILL_REVIEW_PROMPT`, `_COMBINED_REVIEW_PROMPT`. Le fork a ses propres nudges à 0 (pas de récursion).
- **Prompt de revue de skill** (extraits) : « Sois ACTIF — la plupart des sessions produisent au moins une mise à jour de skill » ; cible : des skills **de niveau classe** (`SKILL.md` de règles toujours actives + petit jeu de `references/` thématiques), pas une liste plate de skills étroits à une session ; signaux déclencheurs : corrections de style/ton/format, corrections de méthode, technique ou contournement non trivial, skill consulté qui s'est avéré faux ou périmé ; ordre de préférence : 1) patcher un skill **chargé** pendant la session, 2) patcher un skill « parapluie » existant, 3) ajouter un fichier d'appui, puis créer.
- **Format de skill** (`D:user-guide/features/skills.md`, compatible standard agentskills.io) : dossier avec `SKILL.md` à frontmatter YAML (`name`, `description`, `version`, `platforms`, `metadata.hermes.{tags,category,fallback_for_toolsets,requires_toolsets,config}`) + sections « When to Use / Procedure / Pitfalls / Verification », sous-dossiers `references/`, `templates/`, `scripts/`, `assets/`.
- **Outil `skill_manage`** : actions `create`, `patch` (préféré, `old_string`/`new_string`), `patch` avec `content` complet, `delete`, `write_file`, `remove_file` ; linter consultatif (`incident-log-shape`, `references-sprawl`, `oversized-body` > ~24 K) qui avertit sans bloquer ; skills **épinglés** (suppression refusée) ou **verrouillés** (toute écriture refusée) ; `write_approval` pour faire valider les changements.
- **Principe éditorial** : « des leçons, pas des journaux » : une règle généralisable + une proposition de « pourquoi », sans narration d'incident, numéro de PR ou date.
- **Divulgation progressive** : niveau 0 `skills_list()` (~3 K jetons : nom, description, catégorie), niveau 1 `skill_view(name)`, niveau 2 `skill_view(name, path)` ; chaque skill installé devient aussi une commande `/nom-du-skill` (injectée comme message utilisateur, pas dans le prompt) et jusqu'à 5 skills peuvent être empilés.
- **Curator** (`C:agent/curator.py`, 1 208 lignes ; `D:user-guide/features/curator.md`) : maintenance de fond **uniquement des skills créés par l'agent**, déclenchée par inactivité (tous les 7 jours, après 2 h d'inactivité) ; phase 1 **déterministe sans LLM** : `active → stale` après 14 jours sans usage, `→ archived` (`~/.hermes/skills/.archive/`, récupérable) après 30 jours ; skills épinglés ou référencés par un cron ignorés ; jamais de suppression automatique ; phase 2 optionnelle (`curator.consolidate: true`, désactivée par défaut) : fork LLM qui fusionne les skills qui se recouvrent en parapluies. Suivi d'usage (`C:tools/skill_usage.py`, `skill_ledger.py`). Premier passage différé d'un intervalle complet sur une installation neuve.
- **Garde de sécurité** : `skills_guard.py` (73 K) scanne les skills installés du hub et les skills de projet (verdict « dangerous » = mise en quarantaine : injection de prompt, exfiltration de credentials, texte caché) **[vérifié]** (`D:user-guide/features/skills.md`).
- Chiffre marketing relevé en source secondaire : « typiquement cinq appels d'outils ou plus » avant l'écriture automatique d'un skill **[déduit]** ; le code étudié utilise un compteur de 10 itérations d'outils configurable, pas un seuil de complexité.

### 8.5 Autres persistances **[vérifié]**

- **Checkpoints / rollback** transparents : dépôt git « fantôme » partagé (`~/.hermes/checkpoints/store/`), instantané une fois par tour avant toute opération mutante (`write_file`, `patch`, `terminal` destructif), non visible du LLM (`C:tools/checkpoint_manager.py`).
- **Trajectoires** : sauvegarde au format ShareGPT (`trajectory_samples.jsonl` pour les réussites) pour générer des données d'entraînement (`D:developer-guide/trajectory-format.md`, `C:batch_runner.py`).
- **Cron** : tâches JSON de premier ordre (des tâches d'agent, pas de shell), skills attachés, livraison sur n'importe quelle plateforme ; les sessions cron passent `skip_memory=True` par défaut (`C:agent/AGENTS.md`).

## 9. Permissions et sandbox

### 9.1 Couches de sécurité (huit) **[vérifié]** (`D:user-guide/security.md`)

Autorisation des utilisateurs (listes blanches, appairage DM) ; approbation des commandes dangereuses ; sûreté d'écriture de fichiers (liste noire + bac à sable d'écriture optionnel) ; isolation conteneur ; filtrage d'environnement des sous-processus MCP ; scan des fichiers de contexte ; isolation inter-sessions ; assainissement des entrées (cwd validé contre une liste blanche pour éviter l'injection shell).

### 9.2 Modèle d'approbation **[vérifié]** (`C:tools/approval.py` + `approval_*.py`, `D:user-guide/security.md`)

- Détection par motifs « hardline » (blocage sans appel) et « dangereux » (`approval_detection.py`).
- Modes `approvals.mode` : **`smart`** (défaut : un LLM auxiliaire « gardien » évalue le risque ; bas risque auto-approuvé pour cette commande, danger refusé, doute escaladé à l'humain), `manual`, `off`. `/yolo` limité au chat courant.
- **Disjoncteur de refus** : après N refus consécutifs du gardien (3), le message devient une consigne d'arrêt ferme ; seul le texte du résultat d'outil change (invariant cache) **[vérifié]** (`C:tools/approval.py`).
- Contextes sans humain : `cron_mode`, `single_query_mode`, `unattended_mode` valent `deny` par défaut (webhook/API) : la commande est bloquée **immédiatement** au lieu d'attendre le timeout.
- `HERMES_YOLO_MODE` est **figé à l'import** : « lire `os.environ` à chaque appel laisserait un skill du processus l'activer et contourner toutes les vérifications (escalade par injection de prompt) » **[vérifié]** (`C:tools/approval.py` l.46-48). Pattern à retenir.
- Qui peut répondre à une approbation en salon partagé : `approvals.approvers` (`["*"]` par défaut).
- Les sous-agents résolvent **toujours** les approbations en non interactif (`subagent_auto_approve/deny`) **[vérifié]** (`C:hermes_cli/config_defaults.py` l.1336, `C:tools/delegate_tool_config.py`).

### 9.3 Backends d'exécution et isolation **[vérifié]**

- Backend par défaut : **`local`** (`terminal.backend: "local"`, `C:hermes_cli/config_defaults.py` l.285-286) : **pas d'isolation par défaut**. Backends : `local`, `docker`, `ssh`, `modal` (+ `managed_modal`), `daytona`, `vercel_sandbox`, plus plugins (Singularity) (`C:tools/environments/`, `D:developer-guide/terminal-environment-plugin.md`).
- **Contrat `BaseEnvironment`** (ABC) : une sous-classe implémente `_run_bash()` (renvoie un `ProcessHandle`) et `cleanup()` ; la base fournit `execute()` avec instantané d'environnement, suivi du cwd, gestion d'interruption et timeouts, plus la couche processus longue durée (`start_process`/`attach_process`/`stop_process`). Drapeaux de classe : `is_local`, `uses_host_filesystem`, `_stdin_mode` (`pipe|payload|heredoc`), `cleanup_stops_processes`. Les outils fichiers lisent le disque de l'hôte directement seulement pour le backend local ; sinon tout passe par `execute()` **[vérifié]** (`C:tools/environments/base.py`).
- **Docker durci** (`C:tools/environments/docker.py`, 71 K) : `--cap-drop ALL` puis `DAC_OVERRIDE`/`CHOWN`/`FOWNER` seulement ; `--security-opt no-new-privileges` (désactivé en mode `snap_compat`) ; `--pids-limit 2048` (anti fork-bomb) ; `--cpus`/`--memory` conditionnés à la disponibilité des cgroups (sondage unique) ; `/tmp` en tmpfs 512 Mo `nosuid` ; `/var/tmp` `noexec`. Mode persistant (bind-mount de `/workspace` et `/root` depuis `~/.hermes/sandboxes/docker/<task_id>/`) ou éphémère (tmpfs).
- **Secrets** : aucune variable d'hôte transmise par défaut ; `docker_forward_env` est une **liste blanche explicite** ; les variables déclarées par un skill sont transmises automatiquement (`D:user-guide/security.md`). Le doc avertit que ces variables sont exfiltrables par le code du conteneur.
- **Sortie réseau** : proxy d'egress et isolation réseau Docker (`C:tools/environments/docker_egress.py`, `D:user-guide/egress/network-isolation`) **[vérifié que ces modules existent ; comportement non lu en détail]**. Un module `sandbox_conformance.py` (30 K) vérifie la conformité des backends **[vérifié par le nom ; non lu]**.
- Validation d'URL et politique de sites (`url_safety.py`, `website_policy.py`), garde de dépôt propre (`self_repo_guard.py`), garde de plugin (`plugin_guard.py`) **[vérifié par les noms]**.

## 10. Extensibilité

- **Plugins** (`D:developer-guide/plugins/`, `C:plugins/AGENTS.md`) : trois sources de découverte (`~/.hermes/plugins/`, `.hermes/plugins/` projet, entry points pip) ; `plugin.yaml` + `__init__.py` avec `register(ctx)` ; types : outils, hooks, commandes CLI, **plateformes de messagerie**, **fournisseurs de modèle**, mémoire, moteur de contexte, génération d'image/vidéo, recherche web, navigateur, secrets, fournisseurs de délégation, backends terminal. API publique versionnée (`hermes_cli/data/plugin_api.json`) ; lint de frontière (`scripts/boundary_lint.py`) : le core n'importe jamais un plugin bundlé, un plugin n'utilise que l'API publique **[vérifié]**.
- **Hooks** : `pre_tool_call`, `post_tool_call`, `pre_api_request`, `post_api_request`, hooks de shell (`C:agent/shell_hooks.py`, avec allowlist d'approbation persistée) ; payloads lus par introspection de signature (un handler étroit `handle(args)` n'est pas cassé par les nouveaux champs) **[vérifié]**. Contrat « observer hooks » en lecture seule pour traces/métriques (Langfuse, OpenTelemetry) **[vérifié]** (`D:developer-guide/observer-hooks.md`). Documents `middleware.md` pour les wrappers modifiants.
- **MCP** : client complet (`C:tools/mcp_tool*.py`, ~25 fichiers : OAuth, transports, découverte, santé, sampling, élicitation, filtrage d'environnement, confiance `trust: untrusted`) ; catalogue `optional-mcps/` **[vérifié]**.
- **Skills** : section 8.4 ; hub (ClawHub, GitHub, skills.sh, installation par URL, « taps » = dépôt GitHub de `SKILL.md`), répertoires externes avec précédence `projet → local → create_dir → external_dirs` **[vérifié]**.
- **Sous-agents** (`C:tools/delegate_tool.py`) : `delegate_task` crée des `AIAgent` enfants avec conversation neuve, `task_id` propre (session terminal et cache fichiers), toolsets du parent moins les outils interdits aux enfants, prompt focalisé ; mode simple ou lot parallèle ; profondeur et concurrence bornées par config ; worktree git isolé optionnel ; « le parent ne voit que l'appel et le résumé final, jamais les appels d'outils intermédiaires de l'enfant » **[vérifié]**. Un outil `moa` (mélange d'agents, `agent/moa_loop.py`) existe aussi **[vérifié par le nom]**.
- **Commandes** : `COMMAND_REGISTRY` central de slash commands partagé CLI/passerelle (`C:hermes_cli/commands.py`) ; toute nouvelle clé de config ou commande doit livrer sa doc (`tests/ci/test_docs_drift.py`) **[vérifié]**.
- **Tâches de fond** : cron, kanban (dispatch d'agents sur un tableau), délégation asynchrone (`async_delegation*.py`) **[vérifié par noms]**.

## 11. Providers et modèles

### 11.1 Abstraction **[vérifié]**

- **Pas de LiteLLM** : le seul mot « LiteLLM » dans le code est une mention d'un proxy compatible Anthropic (`C:agent/agent_init.py` l.678, `agent/auxiliary_client.py` l.1858). Hermes maintient **sa propre couche** : un `ProviderProfile` (dataclass, `C:providers/base.py`) par fournisseur, enregistré par plugin (`plugins/model-providers/<nom>/`, ~40 dossiers : openrouter, anthropic, gemini, bedrock, azure-foundry, vertex, xai, deepseek, ollama-cloud, lmstudio, nvidia, huggingface, zai, kimi, minimax, qwen-oauth, nous, openai-codex, custom…), surchargeable par l'utilisateur (`$HERMES_HOME/plugins/model-providers/`).
- `ProviderProfile` porte : `api_mode`, `env_vars`, `base_url`, `models_url`, `auth_type` (`api_key`, `oauth_device_code`, `oauth_external`, `external_process`, `aws_sdk`…), `fetch_models()`, `prepare_messages()`, `build_extra_body()`, `build_api_kwargs_extras()`, `classify_api_error()`, `refresh_credential()`, `default_aux_model`. Le résolveur central ne contient **aucune branche par provider** : un nouveau plugin suffit (`D:developer-guide/provider-runtime.md`).
- **Précédence de résolution** : requête CLI/runtime explicite > `config.yaml` > variables d'env > défauts du provider. Principe : le choix enregistré fait foi, un `export` périmé ne doit pas le contourner silencieusement.
- Chaque clé API est **liée à son `base_url`** pour ne pas fuiter la mauvaise clé vers un endpoint custom **[vérifié]** (`D:developer-guide/provider-runtime.md`).
- Métadonnées de modèle : longueurs de contexte et capacités (`C:agent/model_metadata.py`, 2 608 lignes), intégration du registre models.dev (`agent/models_dev.py`), cache de longueurs appris par erreur provider **[vérifié]**.
- **Appels auxiliaires** (compression, vision, embeddings, titres, `session_search`, curator) : `agent/auxiliary_client.py` (8 234 lignes, le plus gros fichier) ; chaque tâche peut épingler son propre `provider/model/base_url/reasoning_effort` sous `auxiliary:` ; hooks `pre/post_auxiliary_call` distincts des hooks de la boucle principale **[vérifié]**.

### 11.2 Spécificités exploitées

Cache Anthropic `cache_control`, API Responses/Codex (compaction native, app-server Codex), Bedrock, Gemini natif (`gemini_native_adapter.py`), raisonnement multi-formats normalisé (`reasoning`, `reasoning_content`, `reasoning_details` opaques conservés pour le rejeu) **[vérifié]**. Avertissements de coût dans la doc pour tout changement de modèle en cours de conversation (cache perdu).

## 12. Interfaces

**[vérifié]** (`D:developer-guide/architecture.md`, `C:AGENTS.md`)

| Surface | Implémentation |
|---|---|
| CLI / REPL | `cli.py` + mixins `hermes_cli/cli_*_mixin.py`, skins, commande `hermes` |
| TUI | `ui-tui/` (TypeScript/Ink) parlant à `tui_gateway/` en **JSON-RPC** ; le dashboard web embarque le vrai TUI |
| Desktop | `apps/desktop/` (Electron), mode « Bot Desktop » |
| Dashboard web | `web/`, routeurs `hermes_cli/web_routers/` |
| Passerelle de messagerie | `gateway/` + `plugins/platforms/` (voir ci-dessous) |
| Éditeurs | `acp_adapter/` : serveur ACP stdio/JSON-RPC (VS Code, Zed, JetBrains) |
| API serveur | `gateway/platforms/api_server` (compatible chat completions, `/v1/runs`, approbation par `POST /v1/runs/{id}/approval`), webhooks, `hermes serve` |
| Mode non interactif | `hermes chat -q` (« single query », approbations en `deny` par défaut), `batch_runner.py`, cron |
| Bibliothèque | `AIAgent` utilisable en Python (`agent.chat("...")`) |

### Passerelle **[vérifié]**

- Chemin d'un message : événement de plateforme → `Adapter.on_message()` → `MessageEvent` → `GatewayRunner._handle_message()` → **autorisation de l'utilisateur** (listes blanches, appairage DM) → clé de session → création d'un `AIAgent` avec l'historique → réponse livrée via l'adaptateur.
- Contrat d'adaptateur : `BasePlatformAdapter` (`C:gateway/platforms/base.py` l.1780) avec `connect()`, `disconnect()`, `send()` abstraits et des surcharges optionnelles (`send_typing`, `get_chat_info`, `send_exec_approval`, `send_clarify`, `send_slash_confirm`). Les entrées reçues passent par `self.handle_message(event)`.
- **25+ plateformes** en plugins (`C:plugins/platforms/` : telegram, discord, slack, whatsapp, signal, matrix, mattermost, email, sms, irc, line, teams, google_chat, feishu, wecom, dingtalk, weixin, qqbot, bluebubbles, ntfy, simplex…). Ajouter une plateforme : un dossier avec `plugin.yaml` (`kind: platform`) + `adapter.py`, zéro changement du core (`D:developer-guide/adding-platform-adapters.md`).
- Robustesse : file d'admission durable avec reprise au démarrage ; un tour « démarré » dont la passerelle a crashé est récupéré comme `unknown` (jamais rejoué : effets de bord invérifiables) et la file derrière est mise en pause jusqu'à `/discard` ou `/reset` ; verrous de jeton, drain contrôlé, socket de contrôle (`C:gateway/control_socket.py`), anti-boucle de bots (`bot_loop_guard.py`) **[vérifié]** (`D:developer-guide/gateway-internals.md`).

## 13. Observabilité et évaluation

- **Logs** : `~/.hermes/logs/` consultables par `hermes logs` ; `hermes doctor` ; télémétrie sortante interdite sans opt-in (rubrique de contribution) **[vérifié]**.
- **Traces** : contrat d'observation en lecture seule (corrélation, timing, statut, erreurs, payloads assainis) pour Langfuse / OpenTelemetry / « NeMo Relay » ; chemin de métriques partagées Relay de première partie **[vérifié]** (`D:developer-guide/observer-hooks.md`, `relay-shared-metrics.md`).
- **Coûts et usage** : suivi des crédits (`agent/credits_tracker.py`, `billing_usage.py`, `account_usage_nous.py`), table d'usage par modèle en base, télémétrie de tentatives de compaction **[vérifié par les noms et la doc]**.
- **Redaction** : `C:agent/redact.py` (2 049 lignes) pour masquer les secrets dans les sorties/logs **[vérifié par le nom]**.
- **Évaluations internes** (`C:evals/`) : harnais live-modèle A/B et sondes (`compaction`, `core_tool_deferral`, `prompt_footprint`, `prefix_rediet`, `provider_fallback`, `provider_wire`, `plugin_isolation`, `codebase_navigability`, `liveness`, `postmortem`…), résultats datés versionnés (`evals/compaction/results/codex-arm-2026-08-15/`, `jev-cycles-2026-09-19/`) **[vérifié que les dossiers existent ; contenus des résultats non analysés]**.
- **Tests** : ~25 000 annoncés ; runner imposé `scripts/run_tests.sh` (jamais `pytest` nu) ; règles de tests : « contrats de comportement, jamais de tests détecteurs de changement ni de tests qui lisent le source » ; un test d'invariant par correction, « prouvé rouge sur la base » **[vérifié]** (`C:AGENTS.md`).
- **Benchmarks publiés** : aucun benchmark de type SWE-bench n'a été trouvé dans le dépôt ni dans les sources consultées **[non vérifié]**. Les chiffres d'adoption (224 G jetons/jour sur OpenRouter, 95 000 à 211 000 étoiles GitHub) viennent de sources secondaires divergentes **[déduit]**.

## 14. Idées à reprendre

Légende coût : faible / moyen / élevé. Moment : **v0** (noyau initial) ou **plus tard**.

| # | Idée | Pourquoi elle est bonne | Coût | Moment |
|---|---|---|---|---|
| 1 | **Invariant « préfixe de prompt octet-stable »** : le prompt système est construit une fois par session ; tout contenu dynamique (rappels, skills, mémoire modifiée, changement de surface) passe par un message utilisateur ou un résultat d'outil ; seule la compaction mute le contexte | Divise le coût sur Anthropic/OpenAI/Gemini via LiteLLM + prompt caching ; rend le comportement déterministe et testable | faible | v0 |
| 2 | **Test de « surface du prompt » en CI** : snapshot versionné du prompt par défaut et de `tools[]` (cf. `tests/fixtures/prompt_surface/`) ; tout changement demande une mise à jour explicite | Protège le cache et rend chaque ajout d'outil visible en revue ; applique la règle « un outil de plus coûte à chaque appel » | faible | v0 |
| 3 | **Registre d'outils auto-découvert** : `registry.register(name, toolset, schema, handler, check_fn, requires_env, max_result_size_chars)` appelé à l'import, découverte par AST, validation du schéma à l'enregistrement, handlers renvoyant toujours du JSON, exceptions converties en `{"error": ...}` | Ajouter un outil = un fichier ; échecs de schéma détectés tôt ; contrat de retour uniforme | faible | v0 |
| 4 | **Toolsets + `check_fn` + postures** : `TOOLSETS` composables (`includes`), posture « code » sans messagerie/média, `check_fn` mis en cache pour la disponibilité (clé présente, service joignable), outil exposé seulement si toolset **et** `check_fn` | Même noyau pour profil code puis autres profils ; surface d'outils minimale par contexte | faible | v0 |
| 5 | **Table de dispatch pour les outils « niveau agent »** (`INLINE_TOOL_EXECUTORS`) plutôt qu'une chaîne `if name ==` | Les outils qui touchent l'état de l'agent (todo, mémoire, délégation) restent hors du registre générique sans spaghetti | faible | v0 |
| 6 | **ABC `BaseEnvironment`** : sous-classe = `_run_bash()` + `cleanup()` ; la base fournit `execute()` (instantané d'environnement, suivi du cwd, interruption, timeout) ; backends `local` puis `docker` | Exactement notre cible (Docker d'abord) avec la porte ouverte à SSH ; sépare politique d'exécution et transport | moyen | v0 (local+docker), plus tard (autres) |
| 7 | **Durcissement Docker de référence** : `--cap-drop ALL` + ajouts minimaux, `no-new-privileges`, `--pids-limit`, `--cpus/--memory` sondés, tmpfs `/tmp` `nosuid`, secrets seulement par liste blanche explicite `forward_env` | Une recette éprouvée à copier telle quelle dans notre lanceur de conteneur | faible | v0 |
| 8 | **Débordement des sorties d'outils sur disque** : au-dessus d'un seuil par outil, écrire dans un fichier de cache, renvoyer aperçu + chemin balisé (`<persisted-output>`) ; plafonds `max_bytes/max_lines/max_line_length` configurables | Protège le contexte sans perdre l'information ; le modèle relit à la demande | faible | v0 |
| 9 | **Compaction en 4 phases** : (1) élaguer les vieux résultats d'outils sans LLM, (2) bornes protégeant tête et queue sans couper un groupe tool_call/tool_result, (3) résumé structuré par modèle auxiliaire (Goal/Progress/Decisions/Files/Next steps), (4) recompression itérative qui met à jour le résumé ; vidanger la mémoire avant | Qualité de long contexte, coût maîtrisé ; la phase 1 seule est un gain immédiat | moyen | v0 (phase 1+2), plus tard (3+4) |
| 10 | **Modèle auxiliaire configurable par tâche** (`auxiliary.compression.model`, vision, titre…) avec sa propre chaîne de fallback | Résumés et tâches annexes sur un modèle moins cher via LiteLLM ; un seul réglage par tâche | faible | v0 (compaction), plus tard (le reste) |
| 11 | **Mémoire curée en deux fichiers à plafond de caractères**, instantané figé injecté au démarrage, outil unique `memory` (`add/patch/remove` + lots), erreur actionnable au dépassement, verrou de fichier | Mémoire simple, lisible, versionnable, bornée en tokens, compatible cache | faible | v0 |
| 12 | **`session_search` sans LLM sur SQLite FTS5** : modes DISCOVERY/SCROLL/READ déduits des arguments, dédup par lignée, rétrogradation des sessions automatisées, contenu par message borné ; pointeur de récupération laissé dans le résumé de compaction | Rappel exact, gratuit, et c'est ce qui permet une compaction agressive sans perte | moyen | plus tard (la table de sessions SQLite elle-même en v0) |
| 13 | **Revue de fond par fork** : thread démon qui rejoue un instantané dans un agent forké héritant du prompt en cache, liste blanche d'outils côté dispatch, nudges à 0 ; déclenché par compteur (tours/itérations) | Auto-amélioration sans alourdir le tour principal ni casser le cache ; réutilisable pour mémoire et skills | moyen | plus tard |
| 14 | **Skills `SKILL.md` en divulgation progressive** : index léger (nom + description), chargement à la demande, `references/` pour la profondeur, `/nom-du-skill` injecté comme message utilisateur, marqueur `SKILL_PRUNED` après compaction | Standard ouvert (agentskills.io), peu de tokens, extensible par l'utilisateur | moyen | v0 (lecture + index), plus tard (création automatique) |
| 15 | **Principe éditorial et linter de skills** (« leçons, pas journaux », skills de niveau classe, avertissements `incident-log-shape`/`oversized-body`) et **curator déterministe** (`active → stale → archived`, jamais de suppression, épinglage/verrouillage) | Empêche la dérive d'une bibliothèque auto-écrite ; la phase sans LLM est triviale | moyen | plus tard |
| 16 | **Approbation de commandes à 3 modes** (`smart/manual/off`) + motifs « hardline » + **disjoncteur de refus** + modes `deny` par défaut pour contextes sans humain (cron, `-q`, API) | Sécurité utile sans bloquer l'automatisation ; le disjoncteur évite les boucles de réessai | moyen | v0 (hardline + manual), plus tard (smart) |
| 17 | **Geler les drapeaux de contournement à l'import** (`_YOLO_MODE_FROZEN`) | Empêche qu'un skill ou une sortie d'outil active un contournement en modifiant `os.environ` | faible | v0 |
| 18 | **Scan d'injection des fichiers de contexte projet** (AGENTS.md etc.) avec blocage, et hints de sous-répertoire ajoutés aux résultats d'outils | Un dépôt cloné est une entrée non fiable ; conserve le cache | faible | v0 |
| 19 | **Ordre de préfixe favorable aux worktrees** : fichiers projet partagés avant le snapshot dépendant du cwd | Gain de cache gratuit si l'on lance plusieurs sessions en parallèle | faible | plus tard |
| 20 | **Profils de provider déclaratifs** (dataclass : `api_mode`, `env_vars`, `base_url`, `fallback_models`, `classify_api_error`) | Avec LiteLLM on n'en a pas besoin pour le transport, mais la **classification d'erreurs** et la table des capacités (fenêtre de contexte) par modèle restent à nous | moyen | plus tard |
| 21 | **Classification d'erreurs + échelle de reprise + chaîne de fallback** (429/5xx/401, rotation de credential, appel de grâce borné au dernier budget) | Fiabilité sur des runs longs ; LiteLLM fournit retries et fallbacks, mais pas la politique de reprise de la boucle | moyen | v0 (retries simples), plus tard (échelle) |
| 22 | **Appels d'outils parallèles avec ordre de résultats préservé** et liste « jamais en parallèle » | Gain de latence sans corrompre l'alternance de rôles | moyen | plus tard |
| 23 | **Interruption propre** : appel API dans un thread, attente sur événement, pas de réponse partielle persistée | Ctrl-C fiable en CLI/TUI, base de l'API serveur | moyen | v0 |
| 24 | **Checkpoints git fantômes** avant les écritures (`write_file`, `patch`) et rollback | Filet de sécurité très peu coûteux pour un agent de code, invisible du LLM | moyen | plus tard |
| 25 | **`execute_code` (PTC)** : le LLM écrit un script qui appelle les outils en RPC, seul le stdout revient | Collapse les chaînes d'outils (économie de tours et de tokens) ; utile pour l'agent de code | élevé | plus tard |
| 26 | **Tool search / outils différés** (3 outils-ponts) | Maintient `tools[]` petit quand les outils MCP/plugins se multiplient | élevé | plus tard |
| 27 | **Contrat d'adaptateur de plateforme** (`connect/disconnect/send` + `handle_message`) en plugin | Modèle propre pour notre future API serveur et d'éventuelles passerelles | moyen | plus tard |
| 28 | **Discipline de dépôt** : plafonds de complexité par fonction, lints maison, règle « pas de try/except défensif », « patch where production reads » | Garde la base saine ; applicable à un dépôt d'apprentissage | faible | v0 |

### Patterns Python directement réutilisables

- **Registre à l'import + découverte AST** (`discover_builtin_tools`, `_module_registers_tools`) : on lit le fichier avec `ast.parse` pour savoir s'il contient un `registry.register(...)` de niveau module avant de l'importer, ce qui évite d'importer (et donc d'exécuter) tout fichier de `tools/`.
- **`ToolEntry` en dataclass** + `dynamic_schema_overrides: Callable` (fusion de champs de schéma calculés à chaque `get_definitions()`).
- **`ContextVar` pour la portée** (session, profil, scénario d'approbation) plutôt que des globaux ; `copy_context()` pour les threads enfants (`spawn_context_thread`).
- **Introspection de signature** pour les handlers : n'envoyer que les kwargs que le handler accepte (`_kwargs_accepted_by`), ce qui protège les plugins des champs ajoutés.
- **Table dict → handler** au lieu de chaînes `if/elif` (`INLINE_TOOL_EXECUTORS`, backends).
- **`DaemonThreadPoolExecutor`** + résultats réinsérés dans l'ordre d'origine + timeouts de lot.
- **Cache TTL de `check_fn`** avec timeout de sonde et clé de profil.
- **Écriture mémoire atomique avec verrou `fcntl`** et erreurs retournées sous forme de JSON actionnable (`current_entries`, caractères à libérer).
- **ABC à contrat documenté en docstring** (`BaseEnvironment`, `MemoryProvider`, `ContextEngine`) avec drapeaux de classe pour les différences de comportement (`is_local`, `_stdin_mode`).

## 15. Limites et points d'attention

- **Complexité et taille** : 146 000 lignes dans `agent/`, fichiers de plusieurs milliers de lignes (`auxiliary_client.py` 8 234, `context_compressor.py` 5 548), centaines de fichiers « siblings ». Le dépôt est un produit, pas une base pédagogique : copier l'architecture complète serait contre-productif **[vérifié]**.
- **Boucle synchrone par threads** : choix simple mais lourd en gestion d'interruption, de heartbeats et de timeouts (des milliers de lignes dans `tool_executor.py` et `turn_*`) ; une boucle `asyncio` n'est pas envisagée dans la doc lue **[vérifié / déduit]**.
- **Isolation par défaut inexistante** : backend `local` par défaut ; l'approbation `smart` repose sur un LLM gardien, donc faillible ; `docker_forward_env` expose des secrets au code du conteneur (documenté par le projet) ; mode `off`/YOLO désactive jusqu'à l'invite de confiance MCP **[vérifié]**.
- **Mémoire de 2 200 / 1 375 caractères** : très bornée ; dépend de la discipline du modèle (les petits modèles « disent » sauvegarder sans appeler l'outil) ; mémoire figée pendant la session ; un seul agent par `HERMES_HOME` **[vérifié]**.
- **Auto-création de skills = risque de dérive** : sans le curator et le linter, prolifération de skills étroits ; le prompt de revue pousse à l'activité (« une passe qui ne fait rien est une occasion manquée »), ce qui peut produire du bruit ; le curator ne consolide pas par défaut **[vérifié]**.
- **Compaction lossy** : un modèle de résumé à fenêtre plus petite fait perdre le milieu sans résumé ; recouvrement par `session_search` seulement si le modèle y pense **[vérifié]**.
- **Dette de compatibilité** : stubs « frozen old-updater » (`browser_tool.py`), fichiers `hermes_constants_scratch*.py` à la racine, mentions de legacy partout ; indices d'un dépôt qui évolue très vite (versions datées, 0.0.0 dans `pyproject`) **[vérifié]**.
- **Fiabilité des sources secondaires** : chiffres d'étoiles, de jetons, de versions divergents ; les articles de blog (noqta, dsebastien, etc.) ne sont pas des sources primaires **[déduit]**. Aucune annonce officielle de Nous Research n'a pu être consultée directement (la recherche web n'en a pas retourné) **[non vérifié]**.
- **Contribution** : le dépôt rejette des correctifs « bien faits » selon une rubrique de goût ; la surface réelle à maintenir est énorme (plateformes, desktop, navigateur, voix) **[vérifié]**.
- **Points non lus ou non vérifiés** : la taille réelle du prompt système ; le format exact de `patch` ; le comportement détaillé des backends SSH/Modal/Daytona ; le contenu des résultats d'`evals/` ; l'implémentation exacte du streaming ; la qualité réelle de la boucle d'apprentissage (aucune évaluation indépendante trouvée).

## 16. Sources

### Code (dépôt `NousResearch/hermes-agent`, commit `77a30e9127998c0277306c361663f63c0694b88b`, clone du 2026-11-15)

- `AGENTS.md` (racine), `agent/AGENTS.md`, `tools/AGENTS.md`, `LICENSE`, `SOUL.md`, `pyproject.toml`
- `run_agent.py`, `model_tools.py`, `toolsets.py`
- `agent/conversation_loop.py`, `agent/tool_executor.py`, `agent/background_review.py`, `agent/codex_runtime.py`, `agent/agent_init.py`, `agent/curator.py`, `agent/context_engine.py`, `agent/memory_provider.py`, `agent/prompt_builder.py`, `agent/chat_completion_helpers.py`
- `tools/registry.py`, `tools/memory_tool.py`, `tools/session_search_tool.py`, `tools/tool_result_storage.py`, `tools/tool_output_limits.py`, `tools/tool_search.py`, `tools/approval.py`, `tools/delegate_tool.py`, `tools/code_execution_tool.py`, `tools/checkpoint_manager.py`
- `tools/environments/base.py`, `tools/environments/docker.py`
- `providers/README.md`, `providers/base.py`, `plugins/model-providers/`, `plugins/platforms/`, `plugins/memory/`
- `gateway/platforms/base.py`, `hermes_state_schema.py`, `hermes_cli/config_defaults.py`, `evals/`
- Documentation embarquée (`website/docs/`) : `developer-guide/architecture.md`, `agent-loop.md`, `prompt-assembly.md`, `context-compression-and-caching.md`, `session-storage.md`, `provider-runtime.md`, `adding-platform-adapters.md`, `gateway-internals.md`, `observer-hooks.md`, `tools-runtime.md`, `trajectory-format.md` ; `user-guide/security.md`, `user-guide/features/memory.md`, `skills.md`, `curator.md`, `memory-providers.md`

### Web

- https://github.com/NousResearch/hermes-agent (dépôt officiel, confirmé)
- https://hermes-agent.nousresearch.com/docs/llms.txt (index de la documentation officielle)
- https://pypi.org/project/hermes-agent (page de paquet, résultat de recherche non ouvert)
- Sources secondaires, résultats de recherche non ouverts : https://noqta.tn/en/news/nous-research-open-source-ai-2026 (version, date), https://www.digitalapplied.com/blog/hermes-agent-v0-10-self-improving-open-source-guide (v0.10), https://betterstack.com/community/guides/ai/hermes-agent.md, https://www.dsebastien.net/hermes-agent/
