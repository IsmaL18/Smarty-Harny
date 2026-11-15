# Veille harness : Claude Code (Anthropic)

Fiche rédigée selon `_grille.md`. Convention : **[vérifié S#]** = lu dans la source numérotée de la section 16 (doc officielle, article Anthropic, dépôt public) ; **[déduit]** = interprétation ou source secondaire ; **[déduit — observation directe]** = observé depuis l'intérieur du harness par l'agent qui rédige cette fiche (qui tourne dans Claude Code).

Limite structurelle : Claude Code n'est pas open source. Le code du harness (boucle, prompts, outils) n'est pas lisible ; seuls la doc, des articles d'ingénierie et le dépôt « vitrine » (changelog, plugins, exemples) le sont. Aucune rétro-ingénierie tierce n'a été lue pour cette fiche : tout ce qui touche au contenu exact du prompt système ou aux heuristiques internes est donc soit absent, soit en observation directe.

---

## 1. Identité

| Champ | Valeur |
|---|---|
| Éditeur | Anthropic PBC |
| Licence | Propriétaire : « © Anthropic PBC. All rights reserved. Use is subject to Anthropic's Commercial Terms of Service » [vérifié S17 `LICENSE.md`] |
| Code source | Non publié. Le dépôt `anthropics/claude-code` contient README, CHANGELOG, `plugins/`, `mods/`, `examples/` (passerelle LLM, hooks, MDM, settings), `scripts/` (tri d'issues GitHub) [vérifié S17] |
| Distribution | Binaire natif ; paquet npm `@anthropic-ai/claude-code` (installation npm « dépréciée ») [vérifié S17 README]. Node 18+ mentionné au README [vérifié S17] |
| Langage | Non documenté officiellement pour le cœur. Le SDK livre un « binaire natif Claude Code » dans ses paquets Python et TypeScript [vérifié S9]. Langage interne exact : non vérifié |
| Version étudiée | 2.1.325 (tête du `CHANGELOG.md`, commit `0cb75cebcdfd767ee14cd06295f9bf4163274e79`, 2026-11-15) [vérifié S17] |
| Modèles de référence | Famille Claude (Sonnet, Opus, Haiku, Fable ; Sonnet/Opus/Haiku 5.5 cités) [vérifié S6, S15] |
| Date de l'étude | 2026-11-15 |

Surfaces : terminal, app desktop, extensions IDE (VS Code, JetBrains), claude.ai/code, Remote Control, Slack, CI/CD (GitHub Actions) [vérifié S1]. Trois environnements d'exécution : local, cloud (VM gérées par Anthropic ou auto-hébergées), Remote Control (exécution locale pilotée depuis un navigateur) [vérifié S1].

## 2. Philosophie et positionnement

- **Le harness est la couche autour du modèle.** La doc le dit explicitement : « Claude Code is the layer around the model that provides the tools and manages the context the model sees. This surrounding layer is what the term agentic harness refers to » [vérifié S1].
- **Boucle simple, autonomie large, humain dans la boucle.** Trois phases mêlées (rassembler le contexte, agir, vérifier), « Claude decides what each step requires » ; l'utilisateur peut interrompre à tout moment [vérifié S1]. Pas de graphe d'états ni de planificateur externe documentés : le modèle pilote.
- **Le contexte est la ressource rare.** Principe formulé par Anthropic : « trouver le plus petit ensemble de tokens à fort signal » ; commencer simple (« do the simplest thing that works ») [vérifié S12]. Tout le design (skills différés, sous-agents isolés, MCP différé, compaction, CLAUDE.md court) découle de là.
- **Récupération « juste à temps » plutôt que RAG pré-calculé.** Claude Code charge CLAUDE.md d'avance et le reste par `glob`/`grep`/`Read` à la demande (« hybrid retrieval ») [vérifié S12].
- **Sécurité par défaut en lecture seule + approbation**, puis réduction de la fatigue d'approbation par sandbox et classifieur : Anthropic annonce 84 % de prompts de permission en moins en usage interne avec le sandbox [vérifié S11].
- **Le prompt ne garantit rien, les hooks si.** « Claude treats [CLAUDE.md] as context, not enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook » [vérifié S7]. Séparation nette entre instruction (probabiliste) et garde-fou (déterministe).
- **Un seul moteur, plusieurs surfaces.** « The agentic loop, tools, and capabilities are the same everywhere you use Claude Code » [vérifié S1] ; le Agent SDK expose la même boucle en bibliothèque [vérifié S8].
- **Extensible par composition** : skills, sous-agents, hooks, MCP, plugins, « mods » (nouvelle notion : extensions de l'interface/comportement) [vérifié S2, S3, S17].
- Parti pris produit : Claude Code est aussi un produit à abonnement, d'où une forte attention à la gestion du cache de prompt et des limites d'usage [vérifié S15, S16].

## 3. Architecture globale

Composants documentés [vérifié S1, S8, S9] :

1. **Modèle** (raisonnement) + **outils** (action) : « The agentic loop is powered by two components: models that reason and tools that act » [S1].
2. **Gestionnaire de contexte** : assemble system prompt, définitions d'outils, CLAUDE.md, mémoire auto, skills chargés, historique ; compacte ; injecte des `<system-reminder>` [S1, S16].
3. **Moteur de permissions** : règles allow/ask/deny, modes, classifieur « auto », hooks `PreToolUse`/`PermissionRequest` [S3].
4. **Sandbox** (optionnel, Bash et processus fils) : seatbelt/bubblewrap + proxy réseau [S10].
5. **Sessions** : transcription JSONL locale sous `~/.claude/projects/`, points de contrôle (snapshots de fichiers), reprise/fork [S1].
6. **Extensions** : MCP, skills, sous-agents, hooks, plugins (paquets regroupant skills, agents, hooks, serveurs MCP) [S5, S6, S4, S8].
7. **Interfaces** : TUI (défaut), mode non interactif `-p`, SDK Python/TypeScript, IDE, web [S1, S8].

Séparation noyau / interface : le SDK « exécute le binaire Claude Code » et fait transiter un flux de messages typés (`SystemMessage`, `AssistantMessage`, `UserMessage`, `StreamEvent`, `ResultMessage`) [vérifié S9]. **[déduit]** : l'architecture est donc un processus-agent unique, la TUI et le SDK étant deux clients du même flux d'événements ; c'est cohérent avec « the underlying agentic loop is identical » [S1] mais le protocole interne exact n'est pas documenté ici.

Flux de données (simplifié) : prompt → assemblage de la requête (prompt système + outils + contexte projet + historique) → API Claude (cache de préfixe) → blocs texte/tool_use → vérif permissions + hooks → exécution outil (sandbox éventuel) → résultat ajouté à l'historique → boucle [vérifié S9, S16].

Un mode serveur/cloud existe (sessions cloud, Remote Control, passerelle « Claude apps gateway » auto-hébergée avec attribution par utilisateur et plafonds de dépense) [vérifié S1, S15]. Le dépôt contient des exemples de déploiement de passerelle (AWS/GCP, Terraform) [vérifié S17 `examples/gateway`].

## 4. Boucle agent

### Déroulé d'un tour [vérifié S9]

1. Réception du prompt ; le SDK émet un `SystemMessage` `init` (métadonnées de session).
2. Évaluation : le modèle répond avec du texte et/ou des demandes d'outils (un `AssistantMessage` par bloc de contenu).
3. Exécution des outils ; chaque lot de résultats est renvoyé au modèle (`UserMessage`). Les hooks peuvent intercepter, modifier ou bloquer.
4. Répétition jusqu'à une réponse sans appel d'outil.
5. `ResultMessage` final : texte, usage en tokens, coût, `session_id`.

Un « tour » = une passe de la boucle (sortie modèle + exécution des outils) [S9].

### Condition d'arrêt [vérifié S9]

- Fin naturelle : réponse sans `tool_use` (`stop_reason: end_turn`).
- Plafonds : `max_turns`/`maxTurns` (par défaut illimité), `max_budget_usd` (le dépassement peut aller jusqu'au coût d'une réponse, plus les sous-agents en cours). Sous-types de résultat : `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`. `stop_reason` peut valoir `refusal`.
- Le budget couvre les sous-agents ; à épuisement, le lancement d'un nouveau sous-agent échoue (« Budget limit reached ») et les sous-agents en arrière-plan sont arrêtés [S9].
- Garde anti-boucle de compaction : si une sortie est si grosse que le contexte se re-remplit aussitôt, Claude Code cesse d'auto-compacter après quelques tentatives et affiche une erreur [vérifié S1].

### Appels d'outils parallèles [vérifié S9]

Les outils en lecture seule (`Read`, `Glob`, `Grep`, outils MCP annotés `readOnlyHint`) peuvent s'exécuter en concurrence ; ceux qui modifient l'état (`Edit`, `Write`, `Bash`) sont séquentiels. Les outils custom sont séquentiels par défaut sauf `readOnlyHint`. **[déduit — observation directe]** : mon propre environnement m'invite à émettre plusieurs appels indépendants dans un même bloc, ce qui confirme que le modèle est poussé à paralléliser les lectures.

### Streaming

Les événements bruts de l'API (deltas de texte, morceaux d'entrée d'outil) ne sont exposés que si `include_partial_messages` est activé (`StreamEvent`) [vérifié S9]. La TUI affiche un compteur de tokens de sortie du tour en cours [vérifié S15].

### Erreurs et retries

- Outil refusé : le modèle reçoit un message de rejet comme résultat d'outil et tente une autre voie ou abandonne [vérifié S9].
- Échec Grep : l'erreur de ripgrep est renvoyée au modèle pour qu'il corrige (corrigé en 2.1.208 : avant, « No files found ») [vérifié S2].
- Sandbox : en cas d'échec, le modèle peut retenter avec `dangerouslyDisableSandbox`, soumis au mode de permission [vérifié S10].
- Reprise d'usage : attente automatique puis poursuite après réinitialisation d'une limite d'usage (v2.1.234+) [vérifié S15]. Repli automatique de modèle sur classification de sécurité [vérifié S16].
- Détails de retry réseau/API (backoff, nombre d'essais) : non documentés dans les sources lues.

### Interruption par l'utilisateur [vérifié S1]

- `Esc` : arrête immédiatement, annule l'appel d'outil en cours.
- Saisir un message pendant l'exécution : il est mis en file et lu dès la fin des appels d'outils en cours, dans le même tour (« steering » sans redémarrage).
- `Esc Esc` / `/rewind` : retour à un point de contrôle (conversation et/ou fichiers).

## 5. Prompt système

Contenu exact : non publié **[vérifié S17 : absent du dépôt]**. Éléments documentés :

- **Construction hybride statique/dynamique.** Ordre voulu pour le cache : (1) prompt système + définitions d'outils ; (2) contexte projet (CLAUDE.md, mémoire auto, règles sans `paths`) ; (3) conversation [vérifié S16].
- **Injection d'environnement.** Le prompt système embarque les chemins de mémoire auto ; la conversation s'ouvre sur une annonce du répertoire de travail, de la plateforme, du shell et de la version d'OS, plus un instantané git (branche, commits récents) [vérifié S16].
- **Rappels système (`<system-reminder>`)** : Claude Code ajoute lui-même du contexte dans la conversation : CLAUDE.md, instructions du style de sortie, note quand un fichier lu a changé sur disque, lignes d'attribution de commit/PR [vérifié S1, S16]. Interrupteurs : `attribution`, `includeGitInstructions`.
- **Personnalisation** : style de sortie (`output-styles`), `--append-system-prompt`, remplacement complet côté SDK ; un prompt système personnalisé affecte la réutilisation du cache entre sessions [vérifié S9, S16].
- Les modes (plan, style de sortie) et l'invocation de skills ajoutent leurs instructions comme **messages de conversation**, pas dans le prompt système, pour préserver le préfixe en cache [vérifié S16].

**[déduit — observation directe]** (sans recopie) : mon prompt système est assemblé en blocs distincts. Un bloc d'instructions générales (rôle, style, règles d'usage d'outils, sécurité, git), puis des blocs injectés sous forme de `<system-reminder>` : contenu des CLAUDE.md (globaux et projet, avec chemins), mémoire auto (index `MEMORY.md`), contexte utilisateur (e-mail), instantané git, consignes d'attribution de commit, catalogue des skills (nom + description d'une ligne), catalogue des types de sous-agents, instructions des serveurs MCP, liste des outils différés « présents par nom seulement », date du jour, répertoire de travail et scratchpad. Les rappels sont donc la voie d'injection de tout ce qui varie entre sessions ou entre tours. La taille totale est de l'ordre de milliers de lignes dans mon cas à cause des CLAUDE.md et des catalogues (estimation qualitative, non mesurée).

**[déduit — observation directe]** : des messages d'« auto mode » arrivent en cours de session sous forme de rappels, preuve que le harness modifie le comportement par injection de messages plutôt que par réécriture du prompt système.

## 6. Outils

### Liste officielle [vérifié S2]

Les noms de la table de la doc servent aussi de chaînes pour règles de permission, listes d'outils de sous-agents et matchers de hooks.

| Famille | Outils |
|---|---|
| Fichiers | `Read`, `Edit`, `Write`, `NotebookEdit` |
| Recherche | `Glob`, `Grep` (ripgrep), `LSP` (définitions, références, erreurs de type après édition) |
| Exécution | `Bash` (processus séparé par commande), `PowerShell`, `Monitor` (flux de lignes d'un processus en arrière-plan renvoyé au modèle) |
| Web | `WebFetch`, `WebSearch` |
| Orchestration | `Agent` (sous-agent), `Skill`, `AskUserQuestion`, `EnterPlanMode`/`ExitPlanMode`, `EnterWorktree`/`ExitWorktree`, `SendMessage`, `ListAgents`, `Workflow` (script orchestrant plusieurs sous-agents) |
| Suivi de tâches | `TaskCreate/Get/List/Update/Stop` (remplace `TodoWrite`, désactivé par défaut) |
| Découverte | `ToolSearch` (charge des outils différés à la demande) |
| Planification | `CronCreate/List/Delete`, `ScheduleWakeup`, `RemoteTrigger` |
| MCP | `ListMcpResourcesTool`, `ReadMcpResourceTool`, `WaitForMcpServers` |
| Divers | `ReportFindings`, `SendUserFile`, `PushNotification`, `Artifact`, `EndConversation`, `SubagentHandback` |

Les outils de recherche `Glob`/`Grep` sont « absents par défaut sur macOS, Linux, WSL » dans la table : **[déduit]** le modèle les remplace alors par `Bash` + commandes (ripgrep embarqué ou `find`/`grep`) ; la doc ne détaille pas le mécanisme, la condition d'absence n'a pas été élucidée.

### Édition de fichiers : remplacement exact de chaîne [vérifié S2]

`Edit` prend `old_string` et `new_string`. Pas de regex, pas de fuzzy. Trois contrôles :
1. **Lire avant d'éditer** : le fichier doit avoir été lu dans la conversation (une lecture tronquée « PARTIAL view » ne compte pas). Les modèles récents peuvent éditer un fichier non lu si lire ne demanderait pas de permission.
2. **Correspondance exacte** : un caractère d'espace de différence suffit à échouer.
3. **Unicité** : `old_string` doit apparaître une seule fois, sinon fournir plus de contexte ou `replace_all: true`.

Détails utiles : un fichier modifié sur disque depuis la lecture reste éditable si `old_string` correspond exactement et sans ambiguïté, avec une note pour relire ; une lecture via `cat`/`head`/`tail`/`sed -n`/`grep`/`rg` sur un seul fichier sans pipe compte comme lecture ; refus des fichiers non UTF-8 (sauf UTF-16 LE avec BOM) ; mode Perforce (`CLAUDE_CODE_PERFORCE_MODE`) [S2]. **[déduit]** le contrat « lire d'abord + chaîne unique » transforme une édition mal localisée en erreur explicite plutôt qu'en corruption silencieuse : c'est l'idée centrale à copier.

**[déduit — observation directe]** : mon outil `Edit` a exactement cette forme (`file_path`, `old_string`, `new_string`, `replace_all`) avec les messages d'erreur correspondants (« must Read the file first », « must be unique »).

### Lecture [vérifié S2]

`Read` renvoie le contenu numéroté ; images (PNG/JPEG/GIF/WebP) en contenu visuel, PDF par pages (`pages`, 20 pages max/appel, rendu `pdftoppm`), notebooks avec sorties ; refuse les extensions binaires (`.xlsx`, `.zip`…) en suggérant un skill ou un script ; ne lit pas les répertoires. Limites : 25 000 tokens par appel et refus d'un fichier de plus de 256 Ko, lecture par `offset`/`limit` ; `allow_large: true` (v2.1.296+) pour lire plus [S2]. Les erreurs servent d'instructions au modèle (« resize or export a smaller copy »).

### Shell [vérifié S2]

- Chaque commande dans un processus séparé ; le `cd` persiste seulement s'il reste dans le projet ou les répertoires ajoutés, sinon réinitialisation avec le message « Shell cwd was reset to <dir> ».
- Les variables d'environnement ne persistent pas ; alias et fonctions du shell de l'utilisateur sont capturés au démarrage ; `CLAUDE_ENV_FILE` ou hook `SessionStart` pour persister des variables.
- Délai par défaut 2 min, plafond 10 min, le modèle passe `timeout` lui-même. Exécution en arrière-plan ; les sorties volumineuses vont dans un fichier lu ensuite via `Read`.
- Résultats MCP valides : inline jusqu'à ~30 000 caractères, au-delà fichier de session + aperçu des 2 000 premiers caractères ; échecs ~10 000 caractères avec extrait tête/queue [S2, ligne « Valid/Failure »].

### Recherche dans le code [vérifié S2]

`Grep` sur ripgrep, trois modes de sortie (`files_with_matches` par défaut, `content`, `count`), `glob`/`type`, `multiline`, `head_limit`/`offset`, respect de `.gitignore`. `Glob` par motif. Pas d'index sémantique : recherche « agentique » à la demande [S12 : glob et grep pour le just-in-time].

### Conception des outils : principes publiés par Anthropic [vérifié S13]

Peu d'outils à fort impact plutôt que des wrappers d'API ; espaces de noms clairs ; réponses avec noms lisibles plutôt qu'UUID ; paramètre `response_format` concis/détaillé (~1/3 de tokens en concis dans l'exemple Slack) ; pagination et troncature avec indication de comment affiner ; messages d'erreur disant quoi corriger avec un exemple ; description d'outil rédigée « comme pour un nouvel arrivant » ; évaluation sur tâches réalistes multi-appels avec transcripts lus en entier.

### Outils différés

Les définitions MCP sont différées par défaut : seuls noms et instructions de serveur occupent le contexte, `ToolSearch` charge le schéma à la demande [vérifié S1, S9]. **[déduit — observation directe]** : dans ma session, les outils `WebFetch`, `WebSearch`, plusieurs outils Atlassian, navigateur, etc. étaient listés par nom seulement ; il fallait appeler `ToolSearch select:<nom>` avant de pouvoir les invoquer (schéma absent tant que non chargé).

## 7. Gestion du contexte

### Fichiers d'instructions : hiérarchie CLAUDE.md [vérifié S7]

| Portée | Emplacement |
|---|---|
| Politique gérée (organisation) | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux `/etc/claude-code/CLAUDE.md`, Windows `C:\Program Files\ClaudeCode\CLAUDE.md` ; non excluable par `claudeMdExcludes` |
| Projet | `./CLAUDE.md` ou `./.claude/CLAUDE.md` |
| Utilisateur | `~/.claude/CLAUDE.md` |
| Local | `CLAUDE.local.md` (non versionné) |

Règles de chargement : les fichiers des répertoires parents du répertoire de travail sont chargés au lancement ; ceux des **sous-répertoires sont chargés à la demande**, la première fois que Claude lit, écrit ou édite un fichier de ce sous-répertoire (y compris par `cat`/`grep` en Bash) [S7, S2]. Imports `@chemin` récursifs sur 4 niveaux max, avec dialogue d'approbation pour les imports hors du répertoire de travail (protection contre des fichiers committés par des tiers) [S7]. `.claude/rules/*.md` avec en-tête `paths:` (glob) : règles chargées seulement quand des fichiers correspondants sont touchés [S7]. `AGENTS.md` lu à la place de `CLAUDE.md` si présent seul [S1, S7]. Conseil : moins de 200 lignes par fichier ; les instructions contradictoires sont départagées « arbitrairement » [S7]. CLAUDE.md est un contexte, pas une configuration appliquée [S7]. Une édition en cours de session n'est prise en compte qu'après `/clear`, `/compact` ou redémarrage [S16].

### Auto-compaction [vérifié S1, S9, S12, S16]

- À l'approche de la limite, la conversation est résumée ; sont conservés les demandes de l'utilisateur et les extraits de code clés ; des instructions détaillées anciennes peuvent se perdre [S1]. Anthropic décrit : décisions d'architecture, bugs non résolus, détails d'implémentation gardés ; sorties d'outils redondantes jetées ; poursuite avec le résumé plus les cinq fichiers les plus récemment accédés [S12].
- Contrôle : section « Compact Instructions » dans CLAUDE.md, `/compact <focus>`, hook `PreCompact` (champ `trigger` manuel/auto) et `PostCompact`, événement `compact_boundary` dans le flux SDK [S1, S9, S4].
- La compaction est elle-même une requête (même préfixe + instruction de résumé), peu coûteuse si le cache est chaud, coûteuse sinon ; compaction « idle » après inactivité sur TTL d'une heure (`idleCompaction`, v2.1.290+) [S16].
- Ré-attachement après compaction : chaque skill invoqué est ré-attaché dans la limite de 5 000 tokens (25 000 au total) [S5].
- Forme la plus légère : effacement de résultats d'outils anciens (« tool result clearing ») [S12] ; compté comme « reconstruction attendue » du cache [S15].
- Seuil exact de déclenchement : réglable (`auto-compact window`, `model-config`) mais valeur par défaut non lue dans les sources de cette fiche.

### Troncature des sorties [vérifié S2]

Limites par outil (Read 25k tokens, MCP ~30k caractères, erreurs ~10k) ; fichier de repli dans le répertoire de session pour les gros résultats, consulté ensuite par `Read`/`Grep`. Un hook `PreToolUse` peut réécrire la commande (`updatedInput`) pour filtrer la sortie (exemple officiel : `| tail -n 100` sur les commandes de test) [S15, S4].

### Prompt caching [vérifié S16, S9]

C'est un axe de conception de premier ordre.
- Préfixe exact : « there is no per-file or per-segment caching » ; un changement dans le préfixe recalcule tout ce qui suit.
- Ordre de stabilité décroissante : système + outils, contexte projet, conversation.
- **Ce qui invalide** : changer de modèle (cache par modèle), changer d'effort sur la plupart des modèles, mode rapide, ajout/retrait d'outils (serveur MCP sans tool search, refus d'un outil entier), compaction, accumulation d'images, mise à jour de version.
- **Ce qui préserve** : édition de fichiers (un `<system-reminder>` annonce le changement), changement de mode de permission, de style de sortie, invocation de skills/commandes (ajoutés comme messages), `/rewind` (retour à un préfixe déjà en cache), lancement de sous-agent.
- Les outils MCP différés permettent de garder la liste d'outils de la première requête pour toute la conversation ; plan mode et skills ajoutent des messages au lieu de modifier les outils [S16].
- TTL 5 min ou 1 h selon facturation (1 h par défaut sur abonnement dans le quota, 5 min sinon), réglables (`promptCacheTtl`, `CLAUDE_CODE_PROMPT_CACHE_TTL`, v2.1.242+) ; marqueurs `cache_control` ; statistiques de cache dans `/usage` (taux de lecture, ratés, cause probable) [S15, S16].
- Un fork hérite exactement du préfixe parent et lit donc son cache ; un sous-agent normal a son propre préfixe et ne le lit pas [S16].
- Article de conception cité par la doc : « Lessons from building Claude Code: Prompt caching is everything » (https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything) : **non lu directement** ; seul le renvoi est vérifié [S16].

### Budget de tokens

Coût moyen annoncé ~13 $ par développeur et par jour actif, 90 % sous 30 $ [vérifié S15]. Raisonnement étendu activé par défaut ; niveaux d'effort `low`→`max` et `MAX_THINKING_TOKENS` [S15, S9]. `/context` détaille l'occupation [S1]. Les skills `disable-model-invocation` n'occupent aucun contexte tant qu'ils ne sont pas invoqués [S5].

## 8. Mémoire et persistance

- **Sessions** : chaque message, appel d'outil et résultat est écrit en JSONL en clair sous `~/.claude/projects/` ; `--continue`/`--resume` rouvrent sous le même ID ; `--fork-session` ou `/branch` copie vers un nouvel ID ; les sessions sont liées au répertoire et on parallélise avec des git worktrees [vérifié S1].
- **Points de contrôle** : instantané des fichiers avant édition ; `Esc Esc` pour revenir ; séparés de git ; ne couvrent ni bases de données ni API distantes ; ne restaurent pas symlinks/hard links [vérifié S1].
- **Sessions indépendantes** : chaque nouvelle session démarre avec un contexte vide [vérifié S1].
- **Mémoire auto** : notes que Claude écrit lui-même (préférences, corrections), par dépôt, partagées entre worktrees ; les 200 premières lignes ou 25 Ko de `MEMORY.md` sont chargées à chaque session [vérifié S1, S7]. Mémoire persistante des sous-agents (`memory: user|project|local`, répertoire `agent-memory/<nom>/`, mêmes limites) [vérifié S6].
- **SDK** : `session_id` dans `ResultMessage`, reprise et fork ; adaptateur `session_store` pour reprendre sur des conteneurs sans état, avec écriture double (disque local d'abord) [vérifié S9].
- **Notes structurées et listes de tâches** comme mémoire de travail : `TodoWrite`/`TaskCreate…` ; Anthropic cite le fichier NOTES.md comme patron [vérifié S12].
- **Harnais pour longues tâches** (article distinct) : un agent initialiseur crée `init.sh`, un journal `claude-progress.txt`, une liste de fonctionnalités JSON (champ `passes` seul modifiable, JSON choisi car moins facilement réécrit par le modèle que du Markdown), un commit git initial ; chaque session suivante avance sur une fonctionnalité, commit, met à jour le journal, et démarre par un test de bout en bout [vérifié S14].
- Journal de rétention : nettoyage au démarrage des fichiers plus vieux que `cleanupPeriodDays` (30 jours par défaut) [vérifié S15].

## 9. Permissions et sandbox

### Modèle d'approbation [vérifié S3]

| Type d'outil | Approbation en mode manuel | « Ne plus demander » |
|---|---|---|
| Lecture seule (Read, Grep) | Non, dans le répertoire de travail | n/a |
| Bash | Oui, sauf ensemble intégré de commandes en lecture seule | Permanent, par dépôt et commande |
| Modification de fichier | Oui | Jusqu'à la fin de session |
| WebFetch | Oui, sauf domaines de documentation préapprouvés | Permanent par domaine |
| WebSearch | Oui | Permanent |

### Modes de permission [vérifié S3, S9, S1]

- `default`/Manual : demande avant éditions et commandes.
- `acceptEdits` : édite et exécute `mkdir`/`mv`/`cp`… dans les répertoires de travail sans demander.
- `plan` : explore en lecture seule, propose un plan (`ExitPlanMode` demande approbation).
- `auto` : un **classifieur de modèle** relit en arrière-plan les actions (commandes shell, requêtes réseau) et bloque les risquées au lieu de demander ; mode de départ par défaut en interactif depuis v2.1.283 [S1].
- `dontAsk` : refuse tout ce qui demanderait une approbation (agents sans humain).
- `bypassPermissions` : saute les invites, sauf « actions qu'aucun mode n'auto-approuve » ; chemins protégés (`.git`, `.claude`) ; refusé en root sous Unix ; réservé aux environnements isolés [S3, S9].
- Interdiction par politique : `permissions.disableBypassPermissionsMode`, `disableAutoMode` [S3].

### Règles [vérifié S3]

- Ordre d'évaluation **deny, puis ask, puis allow** ; la première correspondance gagne, la spécificité n'entre pas en jeu : une règle `deny` large bloque même une règle `allow` plus étroite.
- Syntaxe `Tool(spécificateur)` : `Bash(npm *)`, motifs de chemins gitignore pour `Read`/`Edit`, domaines pour `WebFetch`, globs de noms d'outils (`mcp__github__*`).
- **Commandes composées** : séparateurs `&&`, `||`, `;`, `|`, `|&`, `&`, retours à la ligne reconnus ; chaque sous-commande doit être autorisée ; `deny`/`ask` s'appliquent si **n'importe quelle** sous-commande correspond, y compris dans une substitution `$(...)` ou une boucle ; « oui, ne plus demander » enregistre une règle par sous-commande ; `cmd &&` sans suite est jugé non analysable. Les enveloppes (wrappers) de processus sont retirées avant correspondance.
- Les règles ne correspondent qu'à la forme habituelle de la commande (une autre invocation du même programme peut y échapper) ; la doc recommande de ne pas voir les `deny` Bash comme un coupe-feu complet, d'où le sandbox [S3].
- **Hooks et règles** : une décision `allow` d'un hook `PreToolUse` ne contourne pas les `deny`/`ask` ; un hook qui sort en code 2 bloque avant l'évaluation des règles `allow` [vérifié S3].
- Hiérarchie de réglages : politique gérée (non écrasable, y compris verrouillage de modes), utilisateur, projet (`.claude/settings.json`), local (`settings.local.json`) [vérifié S3, S10 ; ordre précis de priorité non relu en entier].
- Sous-agents : outils par allowlist/denylist, `permissionMode` propre ; prompts des sous-agents d'arrière-plan remontés dans la session principale [vérifié S6].
- Journalisation côté SDK : callbacks `canUseTool`, `--permission-prompt-tool` [vérifié S3, S9].

### Sandbox [vérifié S10, S11]

- Bâti sur le paquet open source `@anthropic-ai/sandbox-runtime` ; **seatbelt** sous macOS, **bubblewrap** (avec `socat`) sous Linux/WSL2 ; Windows natif non sandboxé. Désactivé par défaut ; `/sandbox` pour l'activer.
- Enforcement au niveau OS, couvre les sous-processus ; périmètre : Bash, PowerShell, Monitor. Les outils de fichiers intégrés (`Read`, `Edit`, `WebFetch`), hooks, serveurs MCP, commandes de barre d'état et « mods » **tournent hors sandbox** [S10].
- Écritures : répertoire de travail, temp utilisateur, répertoires ajoutés ; chemins protégés (`.claude/settings*`, `.bashrc`, `.git/hooks`) non inscriptibles. Lectures : la plus grande partie de la machine par défaut, y compris `~/.ssh` et `~/.aws/credentials` (à restreindre par `denyRead`) [S10].
- Réseau : aucun accès direct ; un **proxy local** hors sandbox, joint par socket Unix, filtre par nom d'hôte (`allowedDomains` vide au départ, `deniedDomains`, `strictAllowlist`) ; nouvelle destination = invite utilisateur ; ne fait pas d'inspection TLS ; ssh brut, UDP/QUIC/ICMP bloqués [S10, S11].
- Variables d'environnement : héritées (secrets compris) par défaut ; `sandbox.credentials` pour refuser ou **masquer** une valeur (le proxy injecte la vraie valeur uniquement vers des hôtes autorisés, via `network.tlsterminate`) [S10].
- Mode auto-allow : les commandes sandboxées s'exécutent sans invite, mais un `deny` Bash, un `rm` sur chemin critique ou un `ask` ciblé (`Bash(git push *)`) priment [S10].
- `excludedCommands` (commandes hors sandbox, ex. `docker compose *`) et échappatoire `dangerouslyDisableSandbox` avec nouvelle tentative soumise au mode ; désactivable (`allowUnsandboxedCommands: false`) ; l'administrateur peut verrouiller et ignorer les réglages dépôt qui desserrent le sandbox [S10].
- Résultat annoncé : −84 % d'invites de permission [S11].
- Cloud : chaque session dans un sandbox isolé ; **les identifiants git ne sont jamais dans le sandbox** ; un proxy git vérifie un jeton à portée limitée et la branche cible puis ajoute le vrai jeton avant de transférer à GitHub [vérifié S11].
- Sécurité du dépôt public : exigence de runner à pare-feu sortant, liste d'hôtes autorisés en mode `enforce` et `--permission-mode auto` pour les jobs qui appellent Claude [vérifié S17 `CLAUDE.md`].

## 10. Extensibilité

### MCP

Serveurs MCP pour services externes ; définitions différées (`ToolSearch`) ; ressources MCP lisibles ; sorties MCP plafonnées ; contrôle d'organisation sur les connecteurs ; SDK : serveurs MCP en process et outils custom annotés `readOnlyHint` [vérifié S1, S2, S9]. Conseil de coût : préférer des CLI (`gh`, `aws`) aux serveurs MCP car elles n'ajoutent pas de listing par outil [vérifié S15].

### Skills (divulgation progressive) [vérifié S5]

Un skill = un dossier avec `SKILL.md` (frontmatter YAML + Markdown).
1. Les descriptions (`description` + `when_to_use`, tronquées à 1 536 caractères) sont dans le contexte.
2. Le contenu complet ne se charge qu'à l'invocation (par l'utilisateur ou par le modèle via l'outil `Skill`).
3. Une fois chargé, il reste dans la conversation (pas de relecture).
4. Les fichiers annexes (`reference.md`, `scripts/`) ne sont lus qu'au besoin ; `SKILL.md` sous 500 lignes.

Champs notables : `disable-model-invocation`, `user-invocable`, `allowed-tools` (pré-approuve des outils pour le tour), `disallowed-tools`, `model`, `effort`, `context: fork` + `agent` (exécute le skill dans un sous-agent à contexte vide), `hooks`, `paths` (auto-chargement limité par glob). Injection dynamique de contexte `` !`commande` `` exécutée avant que le modèle voie le skill (échec = abandon de l'invocation, désactivable par `disableSkillShellExecution`). Précédence : entreprise > personnel > projet ; plugins espacés par nom `/plugin:skill` ; skills imbriqués dans des sous-répertoires. **[déduit — observation directe]** : le catalogue de skills de ma session est une liste « nom : description » ; le corps du skill n'entre dans le contexte qu'après l'appel à l'outil `Skill`.

### Hooks [vérifié S4]

- Événements (liste partielle de la page lue sur les 100 000 premiers caractères) : `SessionStart`, `Setup`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `StopFailure`, `PreToolUse`, `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `SubagentStart/Stop`, `TaskCreated/Completed`, `PreCompact`, `PostCompact`, `PreModelSwitch`, `Elicitation`, `InstructionsLoaded`, `ConfigChange`, `CwdChanged`, `FileChanged`, `WorktreeCreate/Remove`, `Notification`…
- Types de gestionnaires : `command` (stdin JSON), `http` (POST), `mcp_tool`, `prompt` (décision d'un modèle en un tour), `agent` (sous-agent vérificateur, expérimental).
- Codes de sortie : 0 = succès (stdout JSON analysé), **2 = erreur bloquante** (stderr = raison, l'action s'arrête si l'événement peut bloquer), autre = erreur non bloquante. `onFailure: "block"` rend bloquants échec, délai ou sortie invalide (v2.1.295+).
- Sortie JSON : `decision`/`reason` ; `hookSpecificOutput.permissionDecision` (`allow|deny|ask|defer`), `updatedInput` (réécriture des paramètres de l'outil), `additionalContext` (injection de texte). Choisir codes de sortie ou JSON, pas les deux.
- Les hooks tournent hors contexte du modèle, donc ne consomment pas de tokens [vérifié S9].

### Sous-agents [vérifié S6]

- Fichiers Markdown + frontmatter (`name`, `description` requis ; `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `isolation: worktree`, `effort`…). Le corps est le prompt système du sous-agent. Priorité : politique gérée > `--agents` > `.claude/agents/` > `~/.claude/agents/` > plugin.
- Intégrés : Explore (lecture seule, démarre sans CLAUDE.md ni git status ; niveaux quick/medium/very thorough), Plan (lecture seule, en mode plan), general-purpose, plus assistants spécialisés (`claude-code-guide` sur Haiku, `statusline-setup`).
- **Contexte isolé** : fenêtre neuve ; il reçoit son prompt, le message de tâche écrit par le parent, les CLAUDE.md et un instantané git ; **seul son résumé final remonte** ; l'article sur le context engineering parle de résumés de 1 000 à 2 000 tokens [S6, S12].
- Choix du modèle par ordre : paramètre d'appel, champ du sous-agent, `CLAUDE_CODE_SUBAGENT_MODEL`, modèle parent. Imbrication jusqu'à 3 niveaux (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`), 20 concurrents par défaut. Avant-plan bloquant ou arrière-plan (Ctrl+B) ; **fork** = sous-agent qui hérite de la conversation et du pool d'outils exacts du parent (et donc de son cache).
- « Agent teams » (expérimental, coût ~7× en tokens en mode plan) et « Workflow » (script orchestrant beaucoup de sous-agents) existent [S15, S2].
- **[déduit — observation directe]** : l'outil `Agent` de mon environnement accepte `subagent_type` (liste de types définis, dont `Explore`, `Plan`, `general-purpose`, agents personnalisés du dépôt), `prompt`, `model`, `effort`, `isolation: worktree`, mode arrière-plan et notification de fin ; `SubagentHandback` est l'outil par lequel un sous-agent rend son rapport, et c'est le seul canal vers l'appelant (le texte final libre n'est pas transmis).

### Plugins

Paquets regroupant commandes slash, agents, hooks, serveurs MCP, skills ; marketplaces ; installation par `/plugin` ; les plugins de dépôt `claude-code` sont désormais développés dans `anthropics/claude-plugins-official` [vérifié S17 `plugins/README.md`]. Ajouts/retraits de plugins : skills, agents, hooks n'invalident pas le cache, seuls les serveurs MCP le font [vérifié S16]. Nouvelle notion de « mods » (`tool.check`, panneaux, barres d'état) apparaissant dans les docs de permissions [vérifié S3] : non étudiée.

### Commandes personnalisées

Commandes slash en Markdown, fusionnées avec les skills (`/commands`, `.claude/commands/`) [vérifié S9 : « commands … load from .claude/ »].

## 11. Providers et modèles

- Fournisseurs de modèles : API Claude directe, abonnement claude.ai, Amazon Bedrock, Google Cloud (Agent Platform), Microsoft Foundry, plus passerelles LLM via `ANTHROPIC_BASE_URL` [vérifié S15, S16]. Le dépôt contient un exemple de passerelle ; LiteLLM est cité comme passerelle utilisée par de grandes entreprises, avec réserve (« not audited ») [vérifié S15].
- Abstraction : **il n'y a pas d'abstraction multi-fournisseur au sens LiteLLM**. Tous les fournisseurs servent des modèles Claude via des formats compatibles de l'API Anthropic ; le cache dépend de la passerelle qui doit transmettre les marqueurs `cache_control` ; sinon tout l'historique est facturé en non-caché [vérifié S16]. Les sessions sur passerelles tierces peuvent échouer sur dépassement de contexte (correctif 2.1.325) [vérifié S17].
- Spécificités exploitées : cache de préfixe et TTL, raisonnement étendu et niveaux d'effort, repli automatique de modèle sur classifieur de sécurité, mode rapide, `opusplan` (Opus en plan, Sonnet en exécution, avec coût de cache), modèles différents par sous-agent, hook `PreModelSwitch` [vérifié S16, S9, S6].
- Le SDK interdit d'offrir la connexion claude.ai à des produits tiers : clé d'API requise [vérifié S8].

## 12. Interfaces

- **TUI interactive** (défaut) : modes cyclés par Shift+Tab, `/` commandes (`/init`, `/doctor`, `/context`, `/usage`, `/compact`, `/rewind`, `/sandbox`, `/model`…), file d'attente des messages pendant l'exécution, sessions, barre d'état scriptable (champs `current_usage`, `prompt_cache`) [vérifié S1, S15, S16].
- **Non interactif** : `claude -p` avec `--output-format json` ; le SDK conseille d'exécuter le CLI en sous-processus pour d'autres langages [vérifié S8].
- **Agent SDK** Python et TypeScript : `query()`, `ClaudeSDKClient`, options (`allowed_tools`, `permission_mode`, `max_turns`, `max_budget_usd`, `setting_sources`, `effort`, hooks, sous-agents, MCP, `session_store`) [vérifié S8, S9]. Hébergement conteneur/serverless documenté ; offre parallèle « Managed Agents » (harnais hébergé avec sandbox géré) [vérifié S8].
- **IDE** : extensions VS Code et JetBrains ; **web/cloud** : claude.ai/code ; **Remote Control** ; **Slack** ; **GitHub Actions** (`claude-code-action`, mode de permission `auto` imposé dans ce dépôt) [vérifié S1, S17].
- Serveur : pas d'API HTTP « serveur Claude Code » à auto-héberger documentée dans les pages lues, hormis la passerelle et les environnements auto-hébergés [déduit].

## 13. Observabilité et évaluation

- **Coût et usage** : `/usage` (tokens par modèle, coût estimé localement au tarif catalogue, ligne de statistiques de cache), `ResultMessage` avec `total_cost_usd`, `usage`, `model_usage` ; `modelPricing` pour appliquer les tarifs contractuels [vérifié S15, S9].
- **Télémétrie** : export OpenTelemetry de métriques et événements (tokens, coût, outils, lecture/création de cache) par utilisateur et par session ; API Analytics Claude Code ; tableaux de bord d'organisation [vérifié S15, S16].
- **Logs** : `claude --debug-file`, `/hooks`, journal JSONL de session ; ligne de log « modified tool input keys » quand un hook réécrit une entrée [vérifié S15].
- **Attribution d'usage** par skill, sous-agent, plugin, serveur MCP, boucle planifiée, avec recommandations (`/usage`, touche `f` pour appliquer) ; `/insights` produit un rapport HTML sur l'usage [vérifié S15].
- **Évaluation** : l'article « Writing tools for agents » décrit une méthode d'évaluation outillée (tâches réalistes, vérificateurs tolérants, jeu de test retenu, lecture des transcripts, analyse par Claude Code lui-même) [vérifié S13]. Le CHANGELOG mentionne `claude plugin eval` (suites d'évaluation de plugins, rapport JSON) [vérifié S17].
- **Benchmarks publiés** : l'article S13 cite des gains sur SWE-bench Verified liés à l'affinage des descriptions d'outils [vérifié S13] ; aucun score de Claude Code lu ici [non vérifié].

## 14. Idées à reprendre

Hypothèse de lecture : harnais Python, noyau générique, premier profil « agent de code », LiteLLM, exécution dans un conteneur Docker, CLI puis TUI puis API serveur.

| # | Idée | Pourquoi elle est bonne | Coût | Moment |
|---|---|---|---|---|
| 1 | Boucle minimale « appel modèle → outils → résultat → répéter jusqu'à une réponse sans outil », avec arrêt par `max_turns` et `max_budget` et sous-types de résultat typés | C'est le noyau de Claude Code et du SDK ; simple, testable, sans planificateur [S9] | Faible | v0 |
| 2 | Flux d'événements typés (init, message assistant, résultat d'outil, résultat final avec coût et session_id), consommé par CLI, TUI et API | Une seule boucle, plusieurs interfaces ; rend la TUI et l'API serveur triviales plus tard [S9] | Faible | v0 |
| 3 | `edit_file` par remplacement exact : lire avant d'éditer, correspondance exacte, unicité sinon erreur guidante, `replace_all` | Erreurs explicites plutôt que corruption ; pas de format de patch fragile [S2] | Faible | v0 |
| 4 | Outils en lecture seule parallélisables, outils mutants séquentiels (annotation `read_only`) | Gain de latence sans risque de conflit [S9] | Faible | v0 |
| 5 | Messages d'erreur et troncatures qui indiquent quoi faire ensuite (« lire par pages avec offset/limit », « restreindre la recherche ») ; sorties volumineuses écrites dans un fichier de session avec aperçu | Réduit le contexte et guide le modèle [S2, S13] | Faible | v0 |
| 6 | Règles de permission `deny > ask > allow`, première correspondance, analyse des commandes composées (chaque sous-commande doit passer) | Modèle prévisible, difficile à contourner ; à copier tel quel pour le shell [S3] | Moyen | v0 (version simple), plus tard (wrappers, substitutions) |
| 7 | Modes de permission réduits à `default` / `acceptEdits` / `plan` / `dontAsk` | Couvre CLI interactif et exécution sans humain ; `dontAsk` indispensable en API serveur [S3, S9] | Faible | v0 |
| 8 | Le conteneur Docker remplace le sandbox OS, mais garder le proxy réseau à liste blanche hors conteneur et l'absence de secrets dans le conteneur (jetons git injectés par un proxy) | Reprend les deux frontières (système de fichiers + réseau) ; pas d'exfiltration même si injection de prompt [S10, S11] | Moyen | v0 (réseau coupé ou liste d'hôtes), plus tard (proxy d'identifiants) |
| 9 | Hooks `PreToolUse`/`PostToolUse`/`Stop` en commandes externes avec code 2 = blocage et JSON (`permissionDecision`, `updatedInput`) | Garde-fous déterministes séparés du prompt ; extensibilité sans toucher au noyau [S4] | Moyen | Plus tard (v0 : un point d'extension Python `before_tool`/`after_tool`) |
| 10 | Fichiers d'instructions hiérarchiques (`AGENTS.md`/`CLAUDE.md` global, projet, sous-répertoire chargé à la demande quand un fichier du dossier est lu), imports `@` et règles à `paths:` | Contexte précis sans tout charger ; compatible avec le `AGENTS.md` existant de l'utilisateur [S7] | Faible (global + projet), moyen (chargement à la demande) | v0 (global + projet), plus tard (le reste) |
| 11 | Ordonnancement de la requête pour le cache : système + outils stables d'abord, contexte projet, puis conversation en ajout seul ; informations changeantes (fichier modifié, mode) injectées comme messages de rappel, jamais en réécrivant le préfixe | Gros gain de coût et de latence ; lié au marquage `cache_control` via LiteLLM sur les fournisseurs Anthropic [S16] | Moyen | v0 (règle de conception : ne jamais modifier l'historique passé), plus tard (marqueurs et statistiques) |
| 12 | Compaction automatique à l'approche de la limite avec instructions de résumé configurables (section dans CLAUDE.md), ré-attachement des fichiers récents, et garde anti-boucle | Indispensable pour tâches longues ; l'effacement de vieux résultats d'outils est la version légère à faire d'abord [S1, S12] | Moyen | Plus tard (v0 : effacement des vieux résultats d'outils et erreur claire à la saturation) |
| 13 | Sous-agents à contexte isolé : définition Markdown + frontmatter, liste d'outils restreinte, modèle propre, seul le résumé final remonte ; type `explore` en lecture seule | Protège le contexte principal, permet un modèle moins cher par tâche [S6, S12] | Moyen | Plus tard |
| 14 | Skills à divulgation progressive : catalogue nom + description dans le contexte, corps chargé via un outil `skill`, fichiers annexes à la demande | Contexte léger, extensible par fichiers [S5] | Faible à moyen | Plus tard |
| 15 | Points de contrôle : instantané des fichiers avant édition, retour arrière indépendant de git | Rend l'autonomie acceptable ; à faire simple (copie ou worktree) [S1] | Moyen | Plus tard |
| 16 | Session JSONL en ajout seul (un événement par ligne) avec reprise et fork | Persistance triviale, débogage lisible, base de la reprise en API serveur [S1] | Faible | v0 |
| 17 | Liste de tâches et fichiers de progression pour tâches longues : `feature_list.json` (seul le champ `passes` modifiable), journal de progression, `init.sh`, test de bout en bout au démarrage de chaque session | Mémoire entre sessions sans dépendre de la compaction [S14] | Faible | Plus tard |
| 18 | Outils différés (`tool_search`) quand le nombre d'outils MCP grandit | Évite de gonfler le préfixe et d'invalider le cache [S1, S16] | Moyen | Plus tard |
| 19 | Plafonds de coût et de tours, comptage du coût par modèle et par arbre d'agents, statistiques de cache dans la sortie | Maîtrise des dérives ; LiteLLM fournit déjà le coût par appel [S9, S15] | Faible | v0 |
| 20 | Écriture des outils selon les principes d'Anthropic : peu d'outils, noms parlants, `response_format` concis/détaillé, descriptions rédigées pour un nouvel arrivant, évaluation par transcripts | Meilleure fiabilité sans changer de modèle [S13] | Faible | v0 (en continu) |
| 21 | Politique de configuration en couches (défauts, utilisateur, projet, local, imposée) avec règles de sécurité non desserrables par un dépôt | Utile dès qu'un serveur sert plusieurs dépôts [S3, S10] | Moyen | Plus tard |
| 22 | Interruption : file de messages utilisateur lue entre deux appels d'outils, annulation propre de l'outil en cours | Ergonomie majeure de la TUI ; l'API serveur en a besoin pour le pilotage [S1] | Moyen | Plus tard (TUI) |

Idées volontairement **non** reprises en v0 : classifieur de permissions par modèle (mode `auto`), `Workflow` et équipes d'agents, plugins/marketplaces, mods, LSP, intégration IDE.

## 15. Limites et points d'attention

- **Boîte noire** : prompt système, heuristiques de compaction, seuil de déclenchement, politique de retry, format exact du protocole interne : non publics. Ne pas prétendre « reproduire Claude Code » ; reprendre les principes documentés.
- **Instructions non garanties** : CLAUDE.md est du contexte ; les instructions conflictuelles sont résolues arbitrairement, et les consignes anciennes peuvent disparaître à la compaction [S1, S7]. Il faut des hooks pour tout ce qui doit être appliqué.
- **Le sandbox a des angles morts documentés** : outils de fichiers, hooks, MCP hors sandbox ; lecture de `~/.ssh` possible par défaut ; secrets d'environnement hérités ; proxy sans inspection TLS (un hôte autorisé reste une voie d'exfiltration) ; échappatoire `dangerouslyDisableSandbox` ; `filesystem.disabled` ou `allowNestedUserNamespaces` affaiblissent le périmètre [S10].
- **Règles Bash contournables** : une règle ne couvre que la forme usuelle de la commande ; la doc elle-même l'admet [S3].
- **Fatigue d'approbation** : motif central du design (−84 % avec sandbox) ; le mode `auto` déplace la confiance vers un classifieur dont la fiabilité n'est pas mesurée dans les sources lues [S11, S3].
- **Fragilité du cache** : nombreux gestes anodins (changer de modèle, d'effort, ajouter un serveur MCP) coûtent un rechargement complet ; les passerelles qui suppriment `cache_control` font exploser la facture [S16].
- **Coût** : raisonnement étendu non désactivable sur les modèles récents, sous-agents et équipes multiplient les tokens, tâches planifiées et vérifications en arrière-plan consomment pendant l'inactivité [S15].
- **Effort de maintenance visible** : le CHANGELOG 2.1.325 compte 139 entrées sur un seul numéro (sessions, authentification, passerelles, rendu terminal), signe d'une surface très large [vérifié S17] ; la complexité du harnais croît vite.
- **Dépendance fournisseur** : la valeur de nombreuses fonctions (cache, repli de modèle, classifieur, effort) tient à l'API Anthropic. Un harnais multi-fournisseur via LiteLLM perdra une partie de ces mécanismes hors des modèles Claude [déduit].
- **Verrouillage de licence** : code propriétaire, marque non réutilisable (« Claude Code » interdit pour les produits bâtis sur le SDK) [vérifié S8].
- **Non vérifié ici** : détail de la hiérarchie des réglages (ordre de priorité complet), mécanisme exact de disponibilité de `Glob`/`Grep`, valeur par défaut du seuil d'auto-compaction, contenu de la fin des pages hooks, skills, sous-agents et sandboxing (lues sur les 100 000 premiers caractères seulement), article « Prompt caching is everything », notion de « mods ».
- Les extraits de pages ont été obtenus via un outil de résumé automatique (modèle rapide) pour plusieurs sources : les citations chiffrées (limites de tokens, versions) sont à re-vérifier avant de s'appuyer dessus pour une décision de conception.

## 16. Sources

Doc et articles (consultés le 2026-11-15) :

- S1 https://code.claude.com/docs/en/how-claude-code-works
- S2 https://code.claude.com/docs/en/tools-reference
- S3 https://code.claude.com/docs/en/permissions
- S4 https://code.claude.com/docs/en/hooks
- S5 https://code.claude.com/docs/en/skills
- S6 https://code.claude.com/docs/en/sub-agents
- S7 https://code.claude.com/docs/en/memory
- S8 https://code.claude.com/docs/en/agent-sdk/overview
- S9 https://code.claude.com/docs/en/agent-sdk/agent-loop
- S10 https://code.claude.com/docs/en/sandboxing
- S11 https://www.anthropic.com/engineering/claude-code-sandboxing
- S12 https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- S13 https://www.anthropic.com/engineering/writing-tools-for-agents
- S14 https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- S15 https://code.claude.com/docs/en/costs
- S16 https://code.claude.com/docs/en/prompt-caching

Dépôt public (clone `--depth 1`, rien exécuté), commit `0cb75cebcdfd767ee14cd06295f9bf4163274e79` :

- S17 `README.md`, `LICENSE.md`, `CHANGELOG.md` (tête : 2.1.325), `CLAUDE.md` (durcissement des workflows GitHub), `plugins/README.md`, `examples/gateway/` (AWS, GCP), `examples/{hooks,mdm,settings}/`, `mods/`. Clone local : `/private/tmp/claude-501/-Users-ismael-debbagh-Documents-code-harness-engineering-sandbox/b3891487-0e27-4a4e-88ab-5280896c0fcd/scratchpad/veille-src/claude-code/repo`.

Mentionnées par la doc mais non lues : https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything ; https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code ; dépôts `anthropics/claude-agent-sdk-python` et `claude-agent-sdk-typescript` ; `anthropic-experimental/sandbox-runtime`.

Observation directe : session Claude Code de l'agent rédacteur (outils, rappels système, catalogues de skills et d'agents, outils différés), sans recopie de prompt.
