# Fiche de veille : Pi (pi-mono)

Convention : **[vérifié]** = lu dans le code ou la doc officielle (chemin relatif au dépôt cloné, commit `04fd089`, ou URL) ; **[déduit]** = interprétation ou source secondaire.
Les chemins `packages/...` sont ceux du dépôt `badlogic/pi-mono` au commit `04fd0897e4df737cd8422bc99085d6953da804ec`.

## 1. Identité

- Éditeur et auteur : Mario Zechner (badlogic). Le README et les paquets npm pointent maintenant vers l'organisation `earendil-works` (paquets `@earendil-works/pi-*`), le clone de `badlogic/pi-mono` fonctionne. [vérifié : `README.md`, `git remote -v`]
- Licence : MIT, copyright 2025 Mario Zechner. [vérifié : `LICENSE`]
- Langage : TypeScript, Node.js 22.19 ou plus. [vérifié : `README.md`]
- Version étudiée : `@earendil-works/pi-coding-agent` 1.5.2, commit `04fd089`. [vérifié : `packages/coding-agent/package.json`]
- Date de l'étude : 2026-11-15.
- Monorepo : paquets `ai` (API LLM unifiée), `agent` (runtime agent, nom `pi-agent-core`), `coding-agent` (CLI), `tui` (terminal), plus `mcp`, `schema`, `telemetry`, `durable`, `chord`, `codemode`, `evals`, `env`. [vérifié : `README.md`, `ls packages`]
- Attention : le projet a beaucoup grossi depuis l'article fondateur (nov. 2025). Beaucoup de ce qui est décrit dans l'article (pas de MCP, 4 outils, pas de compaction) est partiellement dépassé, voir sections 2, 10 et 15.

## 2. Philosophie et positionnement

- Slogan : « a minimal, extensible agent harness that you can make your own ». Livré avec des défauts solides mais sans sous-agents ni mode plan : « Ask Pi to build what you want, or install a package ». [vérifié : `README.md`]
- Motivation de l'article fondateur : Claude Code devient lourd, son prompt et ses outils changent à chaque version ; Mario veut un contrôle exact du contexte (« Exactly controlling what goes into the model's context yields better outputs ») et la visibilité complète des échanges avec le modèle. Règle : « if I don't need it, it won't be built ». [vérifié : https://mariozechner.at/posts/2025-11-30-pi-coding-agent/ via WebFetch]
- Partis pris assumés dans l'article [vérifié : même URL] :
  - prompt système + définitions d'outils sous 1000 tokens (« no need for 10,000 tokens of system prompt ») ;
  - 4 outils suffisent : read, write, edit, bash ;
  - YOLO par défaut, pas de permissions (« security theater » pour les autres agents), conteneur recommandé ;
  - pas de todo intégré (un fichier TODO.md), pas de mode plan (un PLAN.md observable) ;
  - pas de MCP natif (coût de contexte : Playwright MCP 13,7k tokens, Chrome DevTools 18k) ; préférer des CLI + README lus à la demande ;
  - pas de bash en arrière-plan (tmux), pas de sous-agents (« black box within a black box ») ;
  - pas de limite d'étapes : « The loop just loops until the agent says it's done ».
- Évolution à l'étude (v1.5.2) : le minimalisme est déplacé du noyau vers l'extensibilité. Le noyau reste petit, mais le dépôt contient désormais un paquet MCP (`packages/mcp`, `docs/mcp.md`), la compaction automatique, un modèle de confiance projet, des skills, des paquets installables. Le positionnement devient « noyau minimal + tout le reste en extensions/packages ». [vérifié : `README.md`, `packages/coding-agent/docs/mcp.md`, `docs/compaction.md`] Les sous-agents et le mode plan restent exclus du noyau, fournis en exemples (`examples/extensions/subagent/`, `plan-mode/`). [vérifié : `ls packages/coding-agent/examples/extensions`]
- Gouvernance : Mario se dit « dictatorial » sur le périmètre, incite au fork ; les PR de nouveaux contributeurs sont fermées automatiquement par défaut. [vérifié : article ; `README.md`]

## 3. Architecture globale

Couches, de bas en haut [vérifié : `README.md`, article] :

| Couche | Paquet | Rôle |
|---|---|---|
| Fournisseurs LLM | `packages/ai` | Streaming unifié, catalogue de modèles, auth, coûts, handoff entre providers |
| Boucle agent | `packages/agent` | `Agent`, `agentLoop`, outils, événements, steering/follow-up, hooks |
| Application | `packages/coding-agent` | Outils de code, sessions JSONL, compaction, extensions, skills, modes (TUI, print, JSON, RPC, SDK) |
| Interface | `packages/tui` | Rendu différentiel, composants retenus |

- Flux : `AgentMessage[]` → `transformContext()` (optionnel : élagage, injection) → `convertToLlm()` (obligatoire : filtre les messages UI, convertit les types custom) → `Message[]` → LLM. [vérifié : `packages/agent/README.md`]
- `AgentMessage` est un type extensible par « declaration merging » : des messages applicatifs (notifications, résumés) cohabitent dans l'historique et ne sont convertis qu'à l'appel du modèle. [vérifié : `packages/agent/README.md`]
- Tous les modes d'interface partagent la même boucle et la même gestion de session : « All interfaces use the same agent and session mechanisms ». [vérifié : `packages/coding-agent/docs/how-pi-works.md`]
- Séparation noyau / interface nette : `agent` n'a aucune dépendance TUI ; la boucle émet des événements (`agent_start`, `turn_start`, `message_start/update/end`, `tool_execution_start/update/end`, `turn_end`, `agent_end`) consommés par n'importe quel front. [vérifié : `packages/agent/README.md`, `src/agent-loop.ts`]
- Les outils sont paramétrés par des « operations » pluggables (`BashOperations`, `EditOperations`, `ReadOperations`…) pour déléguer à SSH ou à une micro-VM sans changer l'outil. [vérifié : `packages/coding-agent/src/core/tools/edit.ts`, `bash.ts`]
- Taille indicative du noyau : `agent-loop.ts` 952 lignes, `agent.ts` 623, `types.ts` 551. [vérifié : `wc -l`]

## 4. Boucle agent

Source : `packages/agent/src/agent-loop.ts`, fonction `runLoop` (l.172-340). [vérifié]

Déroulé :
1. Au départ, interroge `getSteeringMessages()` (l'utilisateur a pu taper pendant l'attente).
2. **Boucle externe** : continue tant que des messages « follow-up » arrivent après l'arrêt naturel.
3. **Boucle interne** : tant qu'il y a des appels d'outils ou des messages en attente :
   - `prepareNextTurn` (c'est là que la compaction automatique s'exécute entre deux tours), puis nouvel appel de steering ;
   - émission des messages préparés/en file, puis `prepareRequest` (dernière chance de remplacer le contexte ou le modèle) ;
   - `streamAssistantResponse` ;
   - si `stopReason` vaut `error` ou `aborted` : `finishTurn`, `turn_end`, `agent_end`, retour ;
   - sinon exécution des tool calls ; `finishTurn` peut décider `end` ou `continue`.
4. Condition d'arrêt : plus d'appels d'outils, plus de steering, plus de follow-up. Pas de plafond d'étapes (article). Un outil peut renvoyer `terminate: true` : la boucle ne s'arrête que si **tous** les résultats du lot l'indiquent. [vérifié : `agent-loop.ts` l.690-691]

Appels d'outils :
- Mode `parallel` par défaut : préflight séquentiel (validation + `beforeToolCall`), exécution concurrente, `tool_execution_end` à la fin de chaque outil, mais messages `toolResult` persistés dans l'ordre de la source de l'assistant. Mode `sequential` global ou par outil (`executionMode`) ; un seul outil séquentiel force tout le lot en séquentiel. [vérifié : `packages/agent/README.md`]
- Outil inconnu : résultat d'erreur « Tool X not found » renvoyé au modèle, pas d'exception. Annulation : chaque appel reçoit tout de même un résultat « Operation aborted » pour ne laisser aucun appel orphelin. [vérifié : `agent-loop.ts` `prepareToolCall` l.708-740]
- Arguments : normalisation (`prepareArguments`) puis validation JSON Schema avant exécution. [vérifié : `agent-loop.ts` l.694-760]
- Garde « length » : si la réponse est coupée par la limite de tokens (`stopReason: "length"`), **tous** les appels d'outils du message sont mis en échec au lieu d'être exécutés, car leurs arguments peuvent être tronqués. Détail précieux. [vérifié : `agent-loop.ts` l.272-281]
- Hooks `beforeToolCall` (peut bloquer avec une raison renvoyée au modèle) et `afterToolCall` (peut réécrire le résultat). [vérifié : `packages/agent/README.md`]

Streaming : l'API ai émet des événements typés `text_delta`, `thinking_delta`, `toolcall_delta`, `toolcall_end`, `done`, `error`, avec `partial: AssistantMessage` à chaque delta ; le JSON des arguments est parsé partiellement pour afficher un diff avant la fin de l'appel. [vérifié : `packages/ai/src/types.ts` l.831-847 ; article]

Erreurs et retries :
- Niveau agent (couche `coding-agent`) : `retry.enabled` vrai, `maxRetries` 3, délai de base 2000 ms en backoff exponentiel, plafond 60 s. Niveau provider : `maxRetries` 0 par défaut, car « Provider retries can delay Pi from handling quota and usage-limit errors itself ». [vérifié : `docs/settings.md` l.128-136 ; événements `auto_retry_start/end` dans `src/core/agent-session.ts`]
- Débordement de contexte ou arrêt « length » : une tentative de « compact-and-retry ». [vérifié : `docs/compaction.md`]

Interruption : abort propagé jusqu'aux outils (signal) ; les messages en file sont rendus à l'éditeur. Deux files : **steering** (injecté après le tour courant, pendant que l'agent travaille) et **follow-up** (injecté quand l'agent aurait fini). [vérifié : `docs/how-pi-works.md`]

## 5. Prompt système

Construction : `packages/coding-agent/src/core/system-prompt.ts`. [vérifié]

- **Préambule exact** : « You are a coding assistant running inside pi, a coding agent harness. Help users inspect files, run commands, and modify code. » (une phrase). [vérifié : `system-prompt.ts`]
- Le reste est assemblé en **sections XML nommées** (`<tools>`, `<rules>`, `<docs>`, `<addendum>`, `<project_context>`, `<skills>`, `<cwd>`, plus sections d'extensions). Seul `preamble` n'est pas balisé.
  - `tools` : une ligne `- nom: snippet` par outil actif + « Additional tools may be available. »
  - `rules` : puces dédupliquées. Si bash est présent sans grep/find/ls : « Use bash for file operations like ls, rg, find ». Chaque outil contribue ses propres directives (voir edit en section 6). Toujours : « Be concise in your responses » et « Show file paths clearly when working with files ».
  - `docs` : chemins vers la doc de Pi, à lire seulement si l'utilisateur interroge le harness lui-même (le modèle sait se documenter sur Pi).
  - `project_context` : fichiers AGENTS.md/CLAUDE.md, enveloppés dans `<project_instructions path="...">`.
  - `skills` : nom + description + chemin, pas le contenu.
  - `cwd` : répertoire courant, seule injection d'environnement.
- Remplaçable : `customPrompt` (remplace le préambule et saute tools/rules/docs), `appendSystemPrompt`, `forceSystemPrompt` (opaque), et `.pi/SYSTEM.md` / `APPEND_SYSTEM.md` (protégés par la confiance projet). [vérifié : `system-prompt.ts`, `docs/security.md`]
- Nouveauté architecturale : le prompt est **dans la transcription**. Le premier message de session est un `SystemMessage` avec toutes les sections et les déclarations d'outils ; les changements ultérieurs sont des messages système qui patchent les sections par nom (`null` retire) et listent `toolsAdded/toolsRemoved`. Rejouer la session redonne exactement le prompt et les outils courants. [vérifié : `docs/session-format.md`, `system-prompt.ts` `diffSystemPromptSections`, `agent-loop.ts` `declareToolChanges`]
- Taille : l'article annonce moins de 1000 tokens pour prompt + outils ; la version 1.5.2 ajoute le bloc `docs` et les règles par outil, donc plus long. [déduit : taille non mesurée]

## 6. Outils

Outils par défaut : `read`, `bash`, `edit`, `write`. Outils en lecture seule disponibles mais inactifs par défaut : `grep`, `find`, `ls` ; variante `powershell` sous Windows. [vérifié : `system-prompt.ts` (`selectedTools` par défaut), `src/core/tools/`]

Schémas (TypeBox, validés par AJV) [vérifié : fichiers `src/core/tools/*.ts`] :

| Outil | Paramètres | Notes |
|---|---|---|
| `read` | `path`, `offset?` (ligne, base 1), `limit?` | Texte tronqué à 2000 lignes ou 50 Ko ; images (jpg, png, gif, webp, bmp) envoyées en pièce jointe |
| `write` | `path`, `content` | Écrase le fichier |
| `edit` | `path`, `edits[]` = `{oldText, newText}` | Voir ci-dessous |
| `bash` | `command`, `timeout?` (secondes, aucun défaut) | Sortie combinée stdout+stderr, tronquée, chemin du fichier complet si tronqué ; code de sortie non nul = erreur pour le modèle |
| `grep` | `pattern`, `path?`, `glob?`, `ignoreCase?`, `literal?`, `context?`, `limit?` (100) | Respecte .gitignore, lignes tronquées à 500 caractères |
| `find` | `pattern` (glob), `path?`, `limit?` (1000) | Respecte .gitignore |
| `ls` | `path?`, `limit?` (500) | Dotfiles inclus, `/` suffixe les dossiers |

**Format d'édition** : remplacement de texte exact, **plusieurs remplacements disjoints par appel**. Règles dites au modèle (`editToolSystemPromptContribution`) : chaque `oldText` doit correspondre exactement et de façon unique dans le fichier **original** ; chaque remplacement est apparié contre l'original, pas de façon incrémentale ; pas de chevauchement, fusionner les changements proches. [vérifié : `src/core/tools/edit.ts` l.20-57]
- Tolérance aux modèles imparfaits : `prepareEditArguments` accepte `edits` sous forme de chaîne JSON (cas d'Opus 4.6 et GLM-5.1 d'après le commentaire), d'objet unique, ou l'ancien format `oldText/newText` à plat. [vérifié : `edit.ts` l.97-125]
- Appariement : exact d'abord, sinon flou (`fuzzyFindText`) avec normalisation NFKC, retrait des espaces de fin de ligne, guillemets et tirets Unicode ramenés à l'ASCII. Gestion des fins de ligne CRLF/BOM (`splitBom`, `normalizeToLF`, `applyReplacementsToOriginal` qui réinjecte les CRLF). [vérifié : `src/core/tools/edit-diff.ts`]
- Résultat : `details` contient `diff` (affichage), `patch` (unifié) et `firstChangedLine`. Séparation « ce que voit le LLM » / « ce que voit l'UI » : c'est un principe de l'article (résultat d'outil scindé). [vérifié : `edit.ts`; article]
- Concurrence : `withFileMutationQueue` sérialise les mutations d'un même fichier (clé = `realpath`) alors que des fichiers différents restent parallèles, nécessaire car l'exécution des outils est parallèle par défaut. [vérifié : `file-mutation-queue.ts`]

Troncature : constantes `DEFAULT_MAX_LINES = 2000`, `DEFAULT_MAX_BYTES = 50 Ko`, `GREP_MAX_LINE_LENGTH = 500`. Les messages d'outil disent explicitement comment continuer (`offset`). [vérifié : `truncate.ts` l.11-13, description de `read`]

Outil shell : un `spawn` avec nettoyage d'arbre de processus (`killProcessTree`), hook `spawnHook` pour réécrire commande/cwd/env, timeout optionnel seulement. Pas de bash en arrière-plan : tmux recommandé. [vérifié : `bash.ts`; article]

Recherche dans le code : grep/find/ls sont optionnels ; par défaut le modèle utilise bash (`rg`, `find`). [vérifié : `system-prompt.ts` règle citée plus haut]

## 7. Gestion du contexte

- **Fichiers d'instructions** : cherche `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD` (remontée dans les dossiers parents) ; chargés même si la confiance projet est refusée, donc traités comme entrée non fiable. [vérifié : `src/core/resource-loader.ts` l.213 ; `docs/security.md`]
- **Skills** : standard Agent Skills (`SKILL.md` avec frontmatter name + description). Seuls nom, description et chemin sont dans le prompt ; le modèle lit le fichier à la demande ; `/skill:nom` pour forcer. [vérifié : `docs/skills.md`]
- **Compaction automatique** [vérifié : `docs/compaction.md`, `docs/settings.md`] :
  - déclenchement : `contextTokens > contextWindow - reserveTokens` (réserve 16384) ;
  - vérifiée entre deux tours d'une même exécution (dans `prepareNextTurn`), avant un nouveau prompt, et en récupération sur erreur de débordement ;
  - point de coupe : on remonte en cumulant des tokens jusqu'à `keepRecentTokens` (20000) ; coupe aux frontières de messages utilisateur, ou au milieu d'un « span » trop gros (cas `isSplitTurn`) ;
  - un LLM produit un résumé structuré, itératif (reçoit le résumé précédent) ; suivi cumulatif des fichiers lus/modifiés dans `details` ;
  - effet : une entrée `compaction` (résumé + `firstKeptEntryId`) est **ajoutée** à l'arbre ; les entrées d'origine restent stockées, seule la projection envoyée au modèle change ;
  - les requêtes de résumé désactivent l'écriture du cache de prompt ;
  - personnalisable par hook `session_before_compact` (exemple `custom-compaction.ts`).
  - Tension avec l'article : Mario y disait tenir « des centaines d'échanges » sans compaction. Elle existe désormais, d'où l'importance de vérifier si la v0 en a besoin.
- **Entrées `context_edit`** : omissions de tentatives ratées de la projection sans les supprimer. [vérifié : `docs/compaction.md` sections de récupération ; `docs/session-format.md` mentionne `ContextEditEntry`]
- **Résumé de branche** : en naviguant avec `/tree`, un résumé de la branche quittée peut être injecté. [vérifié : `docs/compaction.md`]
- **Prompt caching** : `cacheRetention` (`short`, `none`…), `sessionId` pour le cache serveur, « cache warming » (appel pour garder le cache chaud, enregistré comme `UsageEntry` de type `cache_warm`), avertissements de cache manqué optionnels, mode Anthropic « message threads » qui n'envoie que les nouveaux messages. [vérifié : `packages/ai/README.md` l.1441, l.1527 ; `docs/session-format.md` ; `docs/settings.md` l.20]
- Budget de tokens : estimation grossière ~1 token / 4 caractères quand l'usage n'est pas fourni. [vérifié : `packages/ai/README.md` l.1574]
- Troncature des sorties d'outils : voir section 6.

## 8. Mémoire et persistance

- Sessions : fichiers JSONL dans `~/.pi/agent/sessions/--<chemin>--/<horodatage>_<id>.jsonl`. Première ligne : en-tête (version 3, `cwd`, `parentSession` éventuel). [vérifié : `docs/session-format.md`]
- **Arbre** : chaque entrée a `id` (8 hex) et `parentId`. L'entrée courante définit la branche active qui fournit l'historique. Continuer depuis un point antérieur crée une branche **dans le même fichier**, append-only. [vérifié : `docs/session-format.md`, `docs/how-pi-works.md`]
- Types d'entrées : `message` (user, assistant, toolResult, system, custom), `model_change`, `thinking_level_change`, `usage`, `compaction`, `branch_summary`, `context_edit`, entrées d'extension. [vérifié : `docs/session-format.md`]
- Commandes : `/tree` (navigue dans le fichier courant, branches proches), `/fork` (nouvelle session depuis un ancien message utilisateur), `/clone` (copie la branche active), `/resume`. [vérifié : `docs/sessions.md` l.42-46]
- Messages assistant : nomment `provider`, `model`, `api`, `usage` (tokens + coût), `stopReason`, et `thinkingLevel`. Cela permet le handoff entre modèles et le calcul de coût par session. [vérifié : `docs/session-format.md`]
- Migration de format automatique (v1 linéaire, v2 arbre, v3). [vérifié : `docs/session-format.md`]
- Mémoire long terme : aucune dans le noyau. AGENTS.md fait office de mémoire projet ; TODO.md/PLAN.md comme fichiers de travail. [vérifié : article]
- Export : HTML (`src/core/export-html`). [vérifié : listing du dossier]

## 9. Permissions et sandbox

- **Aucun système de permissions intégré.** Le README : « Pi does not include a built-in permission system for restricting filesystem, process, network, or credential access. By default, it runs with the permissions of the user ». [vérifié : `README.md`]
- Justification (article) : tout le monde finit en YOLO pour travailler efficacement ; les garde-fous des autres agents sont du « security theater » ; la vraie frontière est le conteneur. [vérifié : article]
- Doc de sécurité : « Watching the transcript, using project trust, and reviewing changes do not create a security boundary ». Injection de prompt reconnue comme risque. [vérifié : `docs/security.md`]
- **Confiance projet** (ajout récent) : avant de charger `.pi/settings.json`, `.pi/mcp.json`, `.pi/extensions`, `.pi/skills`, `.pi/prompts`, `.pi/SYSTEM.md`, Pi demande une décision (par extension via `project_trust`, décision sauvegardée dans `~/.pi/agent/trust.json`, ou réglage `defaultProjectTrust`). Ce n'est pas une sandbox : les outils gardent les droits du processus. Les fichiers AGENTS.md sont chargés quoi qu'il arrive. [vérifié : `docs/security.md`]
- Isolation recommandée (`docs/containerization.md`) [vérifié] : Docker simple (processus Pi entier dans le conteneur, image `node:24-bookworm-slim` avec git et ripgrep, `--ignore-scripts`), Docker Sandboxes (clés restées sur l'hôte, substituées par un proxy), OpenShell (politiques fichier/processus/réseau/identifiants), extension Gondolin (Pi sur l'hôte, outils intégrés routés vers une micro-VM Linux ; les commandes héritent encore des variables d'environnement hôte).
- Permission « à la carte » par extension : exemples `permission-gate.ts`, `confirm-destructive.ts`, `protected-paths.ts`, `dirty-repo-guard.ts` s'accrochent à l'événement `tool_call` pour bloquer. [vérifié : listing `examples/extensions` ; `docs/extensions.md` l.22-24]
- Secrets : identifiants dans `~/.pi/agent` (`auth-storage.ts`) ; la doc avertit de ne pas monter ce dossier dans le conteneur. Valeurs de config résolues avec `${VAR}`. [vérifié : `docs/containerization.md`, `docs/mcp.md`]
- Réseau : aucun contrôle intégré. [vérifié : absence dans le README et `security.md`]

## 10. Extensibilité

- **Extensions** : modules TypeScript chargés dans le processus (aucun isolement) ; une fonction d'usine enregistre outils (`pi.registerTool`), commandes (`registerCommand`), raccourcis, providers, rendus, composants TUI, serveurs MCP, entrées de session (`appendEntry`). [vérifié : `docs/extensions.md`]
- **Événements** très riches : `project_trust`, `resources_discover`, `session_start/before_switch/before_fork/before_compact/before_tree/shutdown`, `before_agent_start`, `agent_start/end/settled`, `turn_start/end`, `message_*`, `tool_execution_*`, `tool_call` (peut muter l'entrée ou bloquer), `context`, `before_provider_request`, `after_provider_response`, `model_select`, `cache_warming_decision`. Un handler `message_end` peut remplacer le message finalisé. [vérifié : `docs/extensions.md` table des matières]
- Cas d'usage listés : portes de permission, checkpoints git, protection de chemins, compaction personnalisée, outils d'interaction, outils à état, intégrations externes. [vérifié : `docs/extensions.md` l.22-30]
- **Skills** (voir section 7), **modèles de prompt** (`/commande` qui s'étend en message), **thèmes**, **paquets Pi** (npm ou git) qui regroupent tout cela. [vérifié : `README.md`, `docs/packages.md`]
- **MCP** : désormais supporté via `packages/mcp` : stdio et HTTP streamable, `~/.pi/agent/mcp.json` + `.pi/mcp.json` (projet, soumis à confiance), commande `pi mcp add`, option `exposure`/`toolExposure` pour maîtriser le coût de contexte. [vérifié : `docs/mcp.md`] Le choix « pas de MCP » de l'article est donc devenu « MCP facultatif, hors noyau de la boucle ». [déduit]
- **Sous-agents** : non intégrés ; exemple dans `examples/extensions/subagent/`. Mario lance des sous-agents via bash avec une commande slash, sortie visible. [vérifié : listing ; article]
- **Mode plan** : exemple `plan-mode/`. **Handoff** : exemple `handoff.ts`. [vérifié : listing]
- `codemode` : paquet permettant à des scripts d'appeler des outils de manière programmatique (la sortie bash a un `structuredContent` dédié). [vérifié : `packages/codemode`, `bash.ts` l.34-47] Non approfondi.
- Hot reload : `/reload` recharge extensions, skills, MCP. [vérifié : `docs/mcp.md`]

## 11. Providers et modèles

Paquet `ai` (`packages/ai`). [vérifié sauf mention]

- **Abstraction à deux niveaux** : un `Api` (protocole : `openai-completions`, `openai-responses`, `azure-openai-responses`, `openai-codex-responses`, `anthropic-messages`, `bedrock-converse-stream`, `google-generative-ai`, `google-vertex`, `mistral-conversations`, `pi-messages`, extensible par chaîne) et un `Provider` (fournisseur : une quarantaine, dont OpenRouter, Groq, DeepSeek, xAI, Ollama/vLLM/LM Studio via compat OpenAI, GitHub Copilot, abonnements ChatGPT par OAuth). `types.ts` l.64-76. Une dizaine d'implémentations d'API, `src/providers/*.ts` (ex. `anthropic-messages.ts` 69 Ko, `openai-completions.ts` 62 Ko : les différences entre « compatibles OpenAI » sont l'essentiel du volume).
- Pourquoi pas le Vercel AI SDK : besoin de contrôle total, surface réduite, problèmes de tool calling avec les modèles auto-hébergés. [vérifié : article]
- Catalogue de modèles généré (OpenRouter, models.dev, catalogue pi.dev) avec capacités ; ne contient que des modèles supportant le tool calling. Collection `Models` avec `setProvider(...)`, import par fabrique pour le tree-shaking. [vérifié : `packages/ai/README.md`]
- **Niveaux de raisonnement unifiés** (`reasoning`/`thinkingLevel` : off…high) via `streamSimple`, options natives via `stream`. Événements `thinking_*` normalisés.
- **Handoff entre providers** : messages utilisateur et résultats d'outils inchangés ; messages assistant du même provider/API/modèle conservés tels quels (thinking inclus) ; ceux d'un autre modèle perdent leurs blocs de thinking (signatures et raisonnement chiffré non transférables). [vérifié : `packages/ai/README.md` l.1579-1588] (L'article décrivait une conversion en texte `<thinking>`, remplacée depuis.)
- Coûts : suivis par message (`usage.cost`), « best-effort » pas pour la facturation. [vérifié : article ; `docs/session-format.md`]
- Fournisseur factice (« Faux Provider for Tests ») pour tester la boucle sans réseau. [vérifié : table des matières de `packages/ai/README.md`]
- Authentification : variables d'environnement, magasin d'identifiants, OAuth (Copilot, ChatGPT, Vertex), en-têtes réécrivables par hook. [vérifié : `packages/ai/README.md`]
- Sérialisation : `Context` sérialisable, ce qui permet de passer une conversation d'un modèle à un autre ou de la stocker. [vérifié : table des matières `packages/ai/README.md`]

## 12. Interfaces

Source : `docs/cli.md`, `docs/how-pi-works.md`. [vérifié]

| Mode | Invocation | Usage |
|---|---|---|
| TUI interactif | `pi` | Éditeur, `/tree`, `/compact`, `/model`, `/mcp`, rendu différentiel |
| Print | `pi --print "…"` (ou stdout redirigé) | Réponse finale seule, composable en pipe : `git diff \| pi --print "Review"` |
| JSON | `pi --mode json` | Flux d'événements JSONL |
| RPC | `pi --mode rpc` | Commandes JSONL sur stdin, réponses/événements sur stdout, pour intégrer Pi dans une autre application |
| SDK | `docs/sdk.md` | `createAgentSession`, `SessionManager` en TypeScript, en processus |

- TUI : approche « scrollback-friendly » (pas d'écran alterné, le défilement et la recherche du terminal restent), composants à `render(width)`, rendu différentiel avec séquences de sortie synchronisée, quelques scintillements assumés. [vérifié : article]
- Pas de serveur HTTP dans le noyau ; le mode RPC par stdio joue ce rôle, OpenClaw l'utilise en intégration réelle. [vérifié : `README.md`]
- Pas d'intégration IDE native identifiée. [déduit : non trouvée]

## 13. Observabilité et évaluation

- Sessions JSONL complètes (prompt, outils, usage, coûts) : c'est la trace principale ; export HTML. [vérifié : `docs/session-format.md`]
- Événements `before_provider_request`, `after_provider_response`, `provider_stream_event` pour inspecter les payloads ; exemple `debug-provider.ts`. [vérifié : `docs/extensions.md`]
- Paquet `telemetry` : contrats neutres (spans, adaptateur de référence en mémoire, adaptateurs OpenTelemetry/Sentry possibles), schémas typés. [vérifié : `packages/telemetry/README.md`]
- Suivi de coût et d'usage par session, notices de cache manqué. [vérifié : `docs/settings.md`, `docs/session-format.md`]
- Évaluation : Terminal-Bench 2.0 avec Claude Opus 4.5, 5 essais par tâche, comparé à Codex, Cursor, Windsurf ; Mario signale que Terminus 2 (agent minimal tmux) « is holding its own » et que les benchmarks ne sont pas représentatifs ; il note aussi une variation des taux d'erreur selon l'heure (charge US). Score exact non lu (images). [vérifié : article ; score non vérifié]
- `packages/evals` : évaluations surtout de documentation (le modèle répond-il juste sur les extensions, les modèles, la TUI ?) et un smoke eval, dans un conteneur (`docker/`). [vérifié : `ls packages/evals/evals`] Intérêt : évaluer le harness sur sa capacité à s'auto-documenter.
- Tests : `./test.sh`, tests LLM sautés sans clés API. [vérifié : `README.md`]

## 14. Idées à reprendre

| Idée | Pourquoi elle est bonne | Coût | Moment |
|---|---|---|---|
| 4 outils seulement (read, write, edit, bash) + grep/find/ls optionnels | Prompt et schémas courts, moins de surface, le modèle utilise `rg` via bash | faible | v0 |
| Prompt système court assemblé en sections nommées (préambule d'une phrase, tools, rules, project_context, skills, cwd) | Auditable, diffable, chaque outil contribue ses propres règles via `snippet` + `guidelines` | faible | v0 |
| Édition par `edits[]` de `{oldText, newText}` appariés contre l'original, unicité exigée, plusieurs disjoints par appel | Moins d'appels, erreurs claires, pas de dérive incrémentale | moyen | v0 |
| Appariement flou de repli (NFKC, espaces de fin, guillemets/tirets) + préservation CRLF/BOM | Réduit les échecs d'édition dus aux modèles sans autoriser l'ambiguïté | moyen | v0 (exact d'abord), flou plus tard |
| Normaliser les arguments d'outil avant validation (`prepareArguments` : chaîne JSON → tableau, objet seul → liste) | Absorbe les défauts connus de certains modèles | faible | v0 |
| Mettre en échec tous les tool calls d'un message `stopReason == "length"` | Évite d'exécuter des appels aux arguments tronqués | faible | v0 |
| Erreurs d'outil renvoyées comme résultats (outil inconnu, validation, abort) et un résultat pour **chaque** tool call, même annulé | Le modèle se corrige ; aucun appel orphelin ne corrompt l'historique | faible | v0 |
| Troncature standard des sorties (2000 lignes / 50 Ko), message de suite (`offset`), sortie complète écrite dans un fichier | Protège le contexte, garde l'accès à l'information | faible | v0 |
| Résultat d'outil scindé : contenu pour le LLM vs `details` (diff, patch) pour l'interface | Interface riche sans polluer le contexte | faible | v0 |
| Boucle émettant des événements typés, sans dépendance UI ; CLI/TUI/API consomment le même flux | Permet CLI → TUI → API serveur sans toucher au noyau | moyen | v0 |
| Deux files steering / follow-up et abort propagé aux outils | Interaction fluide pendant l'exécution, base du TUI et de l'API | moyen | plus tard (file unique en v0) |
| Sessions JSONL append-only, `id`/`parentId`, branches dans un même fichier, `cwd` et version en en-tête | Reprise, branches, audit, format simple à écrire et à lire en Python | moyen | v0 (JSONL linéaire avec `parentId` prêt), arbre complet plus tard |
| Projection du contexte à partir de la branche + entrées `compaction` qui n'effacent rien | Compaction réversible, historique conservé pour l'audit | moyen | plus tard |
| Compaction : seuil `contexte > fenêtre - réserve`, coupe à `keepRecentTokens`, résumé structuré itératif, suivi des fichiers touchés | Recette complète et réglable | élevé | plus tard |
| Hooks `beforeToolCall` / `afterToolCall` / `transformContext` / `prepareRequest` dans la boucle | Point d'accroche unique pour permissions, journalisation, élagage ; permet d'ajouter les garde-fous hors du noyau | faible | v0 |
| Opérations d'outils pluggables (`BashOperations`, `EditOperations`) | Permet d'exécuter les outils dans le conteneur Docker (exec) sans changer la logique d'outil | moyen | v0 (c'est le point d'insertion du conteneur) |
| File de mutation par fichier (`realpath`) | Indispensable dès que les outils tournent en parallèle | faible | v0 si parallèle, sinon plus tard |
| Handoff entre modèles : garder le thinking seulement pour le même provider/API/modèle | Évite des erreurs avec LiteLLM multi-provider | faible | v0 |
| Provider factice pour tester la boucle sans réseau, plus un test réel de validation de requête | Tests rapides et déterministes ; rappel que le mock ne valide pas un contrat externe | faible | v0 |
| Distinction API (protocole) / provider (fournisseur) dans le catalogue de modèles, capacités par modèle | Utile même avec LiteLLM pour piloter reasoning, cache, images | moyen | plus tard |
| Skills `SKILL.md` chargés à la demande (nom + description dans le prompt) | Contexte maigre, extensible sans code | faible | plus tard |
| Fichiers AGENTS.md/CLAUDE.md injectés dans `<project_instructions path>` | Convention déjà répandue | faible | v0 |
| Modèle de confiance projet avant de charger des ressources exécutables | Protège contre un dépôt malveillant, sans prétendre être une sandbox | moyen | plus tard |
| Pas de permissions dans le noyau, isolation par conteneur (ici Docker imposé) | Conforme au contrat du projet : la frontière est le conteneur | faible | v0 |
| Modes print/JSONL/RPC stdio avant le TUI | Chemin le plus court vers l'automatisation et l'API serveur | moyen | v0 (print + JSONL) |
| Coût et usage enregistrés par message dans la session | Visibilité du coût dès le début | faible | v0 |
| Évaluations de « le harness se documente-t-il lui-même » et Terminal-Bench | Mesure externe de la v0 | élevé | plus tard |

## 15. Limites et points d'attention

- **Sécurité** : exécution avec les droits de l'utilisateur, aucun contrôle réseau ni identifiants ; les extensions s'exécutent dans le processus sans isolement. Les auteurs le disent eux-mêmes. [vérifié : `docs/security.md`]
- **Injection de prompt** : AGENTS.md est chargé même sans confiance projet. [vérifié : `docs/security.md`]
- **Dérive du minimalisme** : le dépôt compte maintenant une dizaine de paquets (chord, durable, codemode, télémétrie…) ; l'image « tout tient dans 4 outils et 1000 tokens » n'est plus celle de la v1.5.2. Pour notre v0, il faut reprendre la boucle et les outils de l'époque de l'article, pas la totalité. [déduit : listing de `packages/` et `package-lock.json` 200 Ko]
- Prompt actuel plus long que « < 1000 tokens » (bloc docs, règles par outil) : non mesuré. [déduit]
- Critiques de l'approche (hors article, **non vérifiées** par nos sources) : absence de sous-agents et de mode plan, YOLO par défaut mal vu en entreprise. [déduit]
- Couverture : l'article ne mentionne pas l'arbre de sessions (il évoquait « continue, resume, branching ») ; les détails de l'arbre viennent de la doc actuelle. [vérifié : article, `docs/session-format.md`]
- Maintenance : projet piloté par une personne (« dictatorial »), PR externes fermées par défaut, changement d'organisation GitHub (badlogic → earendil-works) et de noms de paquets : risque pour qui voudrait dépendre de Pi plutôt que s'en inspirer. [vérifié : `README.md`, article]
- Lacunes de l'article : streaming des résultats d'outils non supporté, Google ne streame pas les appels d'outils à l'époque, coûts approximatifs. [vérifié : article ; état actuel non revérifié]
- Non vérifié ici : exécution réelle (code jamais lancé, par consigne), score Terminal-Bench, taille réelle du prompt, comportement de `grep`/`find` côté ripgrep, contenu de `packages/durable`, `chord`, `env`, `codemode`.

## 16. Sources

Code (clone `https://github.com/badlogic/pi-mono`, commit `04fd0897e4df737cd8422bc99085d6953da804ec`) :
- `README.md`, `LICENSE`
- `packages/agent/README.md`, `packages/agent/src/agent-loop.ts`, `agent.ts`, `types.ts`
- `packages/ai/README.md`, `packages/ai/src/types.ts`, `packages/ai/src/providers/*.ts`
- `packages/coding-agent/src/core/system-prompt.ts`, `resource-loader.ts`, `agent-session.ts`, `session-manager.ts`
- `packages/coding-agent/src/core/tools/{read,write,edit,edit-diff,bash,grep,find,ls,truncate,file-mutation-queue}.ts`
- `packages/coding-agent/src/core/compaction/compaction.ts`
- `packages/coding-agent/docs/{how-pi-works,sessions,session-format,compaction,security,containerization,extensions,skills,mcp,settings,cli}.md`
- `packages/coding-agent/examples/extensions/` (listing)
- `packages/telemetry/README.md`, `packages/evals/evals/` (listing)

Web :
- https://mariozechner.at/posts/2025-11-30-pi-coding-agent/ (lu via WebFetch, résumé par un modèle : les citations sont celles rapportées par l'outil, à recontrôler sur la page avant tout usage public)
- https://github.com/badlogic/pi-mono
- https://pi.dev (cité par le README, non consulté)
