# Fiche de veille : Nodecode

Convention : **[vérifié]** = lu dans le code ou la doc officielle (chemin relatif au dépôt cloné, commit `fed3cb7`, ou URL) ; **[déduit]** = interprétation ou source secondaire.
Les chemins sont ceux du dépôt `nodecode-ai/nodecode` au commit `fed3cb71523c36f2afe4207b7d981fb454264ff1` (dernier commit du 2026-11-19). Seul le code utile a été lu ; le code des cellules externes (dont `guard`, `mcp`, `team`, `web`) n'a pas été audité.

## 1. Identité

- Éditeur : Nodecode AI, associé à Foresight Labs (Pays-Bas) ; le site cite NVIDIA Inception, Daytona, UpCloud et CASD comme soutiens ou partenaires. [vérifié : https://nodecode.ai/, `LICENSE`, `docs/models.mdx`]
- Licence : MIT, copyright 2025-2026 Nodecode AI. [vérifié : `LICENSE`]
- Langage : Common Lisp, image SBCL unique. [vérifié : `nodecode.asd`, `docs/README.md`]
- Version étudiée : commit `fed3cb7` du 2026-11-19, 579 fichiers suivis, 161 fichiers de test. [vérifié : `git ls-files`, `find test`]
- Date de l'étude : 2026-11-20.
- Le même éditeur vend aussi des modèles hébergés (Cyber v1, un DeepSeek sans refus orienté sécurité offensive, 1 M de contexte). Hors périmètre de cette fiche : seul le harness est analysé. [vérifié : `docs/models.mdx`, site]
- Dépôt public : https://github.com/nodecode-ai/nodecode (281 étoiles au moment de l'étude). [vérifié : site]

## 2. Philosophie et positionnement

- Pitch : « un agent vivant qui devient le vôtre et évolue avec le temps » : un seul processus Lisp que le modèle réécrit en cours de route. [vérifié : `README.md:21-23`]
- Trois partis pris assumés : auto-modification en direct (définitions gardées, mise à jour à chaud, générations et rollback) ; « tout est cellule » (un dossier avec un `.asd`) ; l'agent édite lui-même son contexte, les vieux tours sont évincés entiers et jamais résumés. [vérifié : `README.md:77-130`]
- Un seul outil exposé au modèle : `eval`. Tout le reste (shell, édition, lecture d'image, fork) est une fonction Lisp appelée dans `eval`. [vérifié : `src/engine/exec.lisp:2754-2780`, `docs/eval.mdx`]
- Pas de sandbox par défaut, assumé : `eval` a tous les droits de l'utilisateur, conseil conteneur ou VM. [vérifié : `README.md:224-227`, `docs/security.mdx:6`]
- Ton de produit de startup (code promo dans le README, modèles maison vendus sur le site), pas de projet communautaire pur. [vérifié : `README.md:19`]
- Importe la configuration d'autres agents (Claude Code, Codex, Hermes, OpenCode, Cursor CLI, Gemini CLI et autres) : clés, instructions, mémoire, skills, MCP. [vérifié : `README.md:35`]

## 3. Architecture globale

- Un organisme = un processus Nodecode par home (`~/.nodecode/`), propriétaire unique du store (verrou sur `history.db.lock`) ; les shells s'y attachent. [vérifié : `docs/organism.mdx:6-12`]
- Découpage de `src/` [vérifié : `docs/README.md:36-66`] :
  - `lib/` : macros déclaratives (erreurs, records, JSON, config) ;
  - `store/` : journal d'événements et état (SQLite) ;
  - `session/` : sessions, tours, snapshots d'espace de travail, recall ;
  - `organism/` : auto-modification (layer, cellules, connaissances, mise à jour) ;
  - `engine/` : boucle de tour, moteur de contexte, fournisseurs (un fichier par dialecte), exécution ;
  - `gateway/` : serveur HTTP et WebSocket local ;
  - `client/`, `cli/`, `tui/` : clients de la gateway.
- Tous les clients (TUI, web, téléphone, bots, RPC) parlent à la même gateway, écoute sur `127.0.0.1`. [vérifié : `docs/gateway.mdx:6`]
- Flux : client, WebSocket avec jeton opérateur, gateway, boucle de tour, fournisseur, flux de `stream parts`, événements durables dans le store, frames renvoyées aux clients. [déduit de `src/engine/provider.lisp:1-20` et des docs]
- Fichiers très gros (`turn.lisp` 4 791 lignes, `gateway.lisp` 5 778, `provider.lisp` 5 853), avec un plafond de lignes imposé par `just check`. [vérifié : `wc -l`, `docs/README.md:11`]
- Piège : tas SBCL de 8 Go requis, un défaut de 1 Go a planté en production. [vérifié : `docs/README.md:24-27`]

## 4. Boucle agent

- La boucle `agent-loop` est récursive, un appel par tour de modèle (round suivant = appel récursif), pas un `while`. [vérifié : `src/engine/turn.lisp:4393`, `:4535-4570`]
- Déroulé d'un round : plier le journal durable en un contexte compilé immuable, appeler le fournisseur, enregistrer le message assistant, exécuter les appels d'outils, ajouter les résultats, recommencer. [vérifié : `turn.lisp:4393-4560`]
- Arrêt : un message assistant sans appel d'outil. Si des `eval` d'arrière-plan se sont terminés, un round du harness les lit d'abord et le modèle reparle. Un « steer » de l'utilisateur en attente arrête aussi le tour à la frontière du lot d'outils. [vérifié : `turn.lisp:4537-4570`]
- Pas de plafond de rounds. Seul un budget de tour optionnel (`:SECONDS`, `:CALLS`, `:TOKENS`), désactivé par défaut ; passé le budget, un appel est refusé, et un round qui rappelle un outil après refus termine le tour. Un avertissement apparaît à 4/5. [vérifié : `src/engine/meter.lisp:79-84`, `turn.lisp:3907-3932`]
- Appels parallèles : la requête annonce toujours que le parallèle est permis, mais le harness exécute les appels d'un round en séquence dans l'ordre du modèle. La vraie concurrence vient des `eval` d'arrière-plan. [vérifié : `turn.lisp:3355-3364`, `:3921-3925`]
- Pré-vol : chaque appel est décodé et validé (JSON, type, champs requis) avant tout effet ; un refus est un JSON structuré avec un champ de réparation et `"retryable": true`. [vérifié : `turn.lisp:561-590`]
- Streaming : parts émises au fil de l'eau ; chaque requête écrit un fait durable `turn.provider_request` (empreinte SHA-256 du corps, contexte estimé, octets de préfixe partagés avec la requête précédente pour diagnostiquer les fuites de cache). [vérifié : `turn.lisp:3350-3370`, `:2660-2670`]
- Retries : deux budgets (échecs de requête, échecs de flux), `Retry-After` respecté, chaque retry journalisé ; un message vide ou un appel sans nom devient une erreur de contrat renvoyée dans le retry ; ensuite bascule sur une chaîne de modèles de repli. [vérifié : `turn.lisp:714-717`, `:3408-3530`]
- Débordement de contexte : un gouverneur avant l'appel (jusqu'à 8 réductions) et, sur une erreur 400 reconnue, jusqu'à 8 éviction supplémentaires ; le plafond évite qu'un faux positif vide la session. [vérifié : `turn.lisp:70-75`, `:719-745`, `:3415-3433`]
- Garde de boucle : détecte le modèle qui se répète pendant le flux (cycle exact, paragraphes quasi identiques, absence de nouvel identifiant), échoue la tentative et la rejoue ou bascule. Ce n'est pas une garde contre la répétition d'appels d'outils. Désactivée pour Claude, sémantique pour Gemini, DeepSeek et Grok. [vérifié : `src/engine/loop-guard.lisp:1-60`]
- Interruption : Échap n'est honorée qu'une fois le round fermé durablement ; les appels ouverts reçoivent « interrupted by user ». Après un crash, le tour ouvert reprend au démarrage suivant (3 reprises au plus). [vérifié : `turn.lisp:3798-3900`, `docs/sessions.mdx`]
- Sous-agents : `(fork "t1" "t2")`, 4 forks au plus, chacun avec tout le contexte, 900 s max. [vérifié : `docs/eval.mdx`]

## 5. Prompt système

- Minuscule : 4 phrases (environ 120 mots) qui disent : image Lisp vivante, `eval` exécute des formes, les définitions persistent, `(help)` est le manuel, dépenser les tokens une seule fois. [vérifié : `turn.lisp:54-69`]
- Le texte est dans un `defparameter` modifiable ; l'agent peut le réécrire, et `~/.nodecode/SYSTEM.md` le remplace (relu au premier round de chaque tour). [vérifié : `turn.lisp:4086-4096`, `docs/instructions.mdx`]
- Parties dynamiques : le message système porte les sections « dossier » (cwd, home) et « aide » ; les sections permanentes (règles de l'opérateur, fichiers d'instructions, index des mémoires et définitions, notices) voyagent dans le premier message utilisateur en blocs `<harness>`. [vérifié : `src/engine/context.lisp:1854-1932`]
- Figé par tour, épinglé par conversation : une modification en cours de session arrive sous forme de diff `<system-reminder>` après le message utilisateur, ce qui préserve le préfixe en cache. La section d'index est placée en dernier pour que ses changements ne cassent pas le préfixe. [vérifié : `context.lisp:1906-1925`, `turn.lisp:4109-4144`]
- Pas de date dans le prompt : la ligne de dépense ajoutée à chaque résultat d'outil porte l'horloge. Pid, port et autres valeurs volatiles sont exclus pour le cache. [vérifié : `context.lisp:1817-1845`, `meter.lisp:20-30`]

## 6. Outils

- Un seul outil enregistré par le noyau, `eval` (les cellules peuvent en ajouter). Arguments : `form` (obligatoire), `yield_time_ms` (10 000 par défaut, 600 000 max), `strings` (textes lus via `($ "nom")`). [vérifié : `exec.lisp:2754-2780`, `docs/eval.mdx`]
- Helpers dans `eval` : `sh` (`bash -c`, sortie fusionnée, 1 M de caractères max), `edit` (remplacement d'une occurrence), `write-file`, `patch` (sur des définitions gardées), `look` (image jusqu'à 5 Mo). Pas d'outil de recherche dédié : `grep` via `sh` ou du Lisp. Appeler un helper comme un outil est refusé avec un indice de réparation. [vérifié : `docs/eval.mdx`]
- Résultat plafonné à 32 000 caractères ; une ligne `=>` par forme, seule la dernière valeur en entier ; une ligne `;;` en tête devient une note conservée dans le stub d'éviction. [vérifié : `docs/eval.mdx`]
- Détails inhabituels : une forme en échec se nomme et les précédentes restent acquises ; les parenthèses non fermées sont complétées par l'indentation ; les avertissements du compilateur ouvrent le résultat. [vérifié : `docs/eval.mdx`]
- Persistance : chaque forme de définition au niveau racine (`defun`, `defvar`, `defclass`, `define-*`...) est gardée dans un fichier par définition sous `~/.nodecode/cells/<user>/`, avec un commit git par écriture nommant les définitions et la session, rechargé au démarrage. Les formes imbriquées sont « un essai » et ne sont pas gardées. [vérifié : `docs/eval.mdx`, `src/organism/scribe.lisp:242`]
- Filet de sécurité : redéfinir une fonction qui tourne dans la pile (comme `agent-loop`) est « retenu » : actif immédiatement, écrit dans le layer seulement après le premier retour réussi ; si elle lève une erreur, l'ancienne définition revient. Le paquet noyau est verrouillé au démarrage, mais le modèle peut abaisser le verrou (tracé). [vérifié : `docs/eval.mdx`, `docs/security.mdx:42-43`]
- Garde de dérive : un fil surveille les `eval` toutes les 0,2 s (pile au-delà de 4 Mo sur 8, part de tas) et les interrompt en erreur ordinaire, car un débordement de page de garde pendant l'allocation tuerait toute l'image. [vérifié : `exec.lisp:552-562`, `:700-737`]
- Éditer un fichier que l'image charge (source livrée, cellule, layer) est réévalué aussitôt : le code livré est modifiable en direct. [vérifié : `docs/eval.mdx`]

## 7. Gestion du contexte

- Fichiers d'instructions : un seul par dossier parmi `AGENTS.md`, `CLAUDE.md`, `.cursorrules` (si `CLAUDE.md` et `AGENTS.md` coexistent, seul `AGENTS.md` est lu), remontée jusqu'à `/` ou 64 dossiers, le plus lointain d'abord, plus `~/.nodecode/AGENTS.md`. Pas de mécanisme `@import` trouvé. [vérifié : `docs/instructions.mdx`, `context.lisp:1686-1690` ; absence d'import : déduit]
- Budget de 65 536 caractères pour les fichiers de projet ; un fichier qui dépasse est refusé en entier, jamais tronqué. [vérifié : `context.lisp:1690`]
- Éviction, jamais de résumé : déclenchée à 0,85 de la fenêtre estimée, jusqu'à 0,50 ; dans un tour vivant, les 8 derniers rounds restent entiers et les plus anciens sont réduits à 300 caractères. Fenêtre inconnue = pas d'éviction. [vérifié : `context.lisp:30-51`, `:1527-1545`]
- Un stub adressable liste les notes `;;`, les définitions enregistrées et l'état, et renvoie vers le rappel. [vérifié : `context.lisp:20-24`]
- Rappel : `(recall-log ...)` fait un `LIKE` SQL sur des lignes tronquées, `(recall-entry N)` rend un corps entier. Pas d'index de pertinence, volontairement ; le journal est sans perte, l'éviction ne déplace qu'un plancher de visibilité. [vérifié : `src/session/recall.lisp:1-45`]
- Édition de son propre contexte : `(context)` exporte la fenêtre en `context.txt` éditable (blocs balisés), la requête suivante applique les suppressions, remplacements et notes ; ou `(context :drop ... :keep ... :note ...)`. Les blocs non édités restent identiques à l'octet pour garder le cache. [vérifié : `src/engine/working-context.md`, `docs/context.mdx`]
- Ligne de dépense en fin de chaque résultat d'outil (horloge, rounds, appels, budget, remplissage du contexte), rendue seulement dans la copie du modèle. Un test A/B annoncé dans le code ne montre pas de changement de fréquence d'édition. [vérifié : `meter.lisp:20-35`, `:280-290`]
- Cache de prompt : points d'arrêt `cache_control`, préfixe stable. Réchauffage : à 0,9 du TTL (5 min ou 1 h), renvoi exact de la requête avec `max_tokens` à 1 quand l'économie attendue le justifie (écriture 1,25 x contre lecture 0,1 x chez Anthropic), arrêt après 60 min (tour ouvert) ou 30 min, ou si l'économie passe sous 5 centimes. [vérifié : `src/engine/cache-warming.lisp:1-45`]
- Pas de compaction par résumé (explicite). Un modèle auxiliaire sert seulement à titrer les sessions. [vérifié : `context.lisp:23`, `docs/sessions.mdx`]

## 8. Mémoire et persistance

- Tout est un journal d'événements SQLite en ajout seul (`~/.nodecode/history.db`) ; le contexte est un pli pur du journal vers une requête. [vérifié : `context.lisp:1-20`, `docs/sessions.mdx`]
- Sessions `s-XXXXXXXX`, reprise (`resume`, `-c`), `/fork`, `/tree`, `/undo` et `/redo` (déplacent la tête sans rien effacer), restauration de fichiers via des snapshots d'espace de travail (dépôt git nu dans `<cwd>/.nodecode/workspace_snapshots`, non ignoré par git : piège). Les écritures hors du dossier de session ne sont pas annulables. [vérifié : `docs/sessions.mdx`, `docs/security.mdx:56`]
- Mémoire = définitions : `(define-memory nom "une phrase" :type :feedback|:user|:project|:reference|:lesson)` écrit un fichier dans un dépôt git dédié, jamais chargé, lu comme donnée ; `define-skill` de même pour les skills. Les mémoires `:project` ne s'affichent que sous leur dépôt. [vérifié : `src/organism/knowledge.lisp:1-30`]
- Index dans le prompt : définitions classées par un registre d'usage (`usage.jsonl`), dans un budget « chaud », figé à la racine de la conversation et rafraîchi seulement quand le préfixe casse déjà. Récupération à la demande par `(help 'nom)` et `(index "texte")`, sans embeddings. [vérifié : `knowledge.lisp:19-30`, `:651-672` ; absence d'embeddings : déduit]
- L'apprentissage est donc du code et des fichiers sous git, avec générations et `rollback`, pas une base de mémoire séparée. [déduit]

## 9. Permissions et sandbox

- Docs : « pas de sandbox ». Protections réelles : écoute loopback, contrôle des en-têtes Host et Origin, jeton opérateur Bearer, fichiers en 0600/0700, verrou du noyau, masquage des secrets dans les sorties, liste d'autorisation obligatoire pour Discord, Slack et Telegram. [vérifié : `docs/security.mdx:8-40`]
- Limites avouées : `eval` a l'autorité totale, les cellules sont du code plein pouvoir chargé sans demander, le masquage des secrets est une « courtoisie » (`eval` peut lire `auth.json`), les messages de salon ont l'autorité de l'hôte. [vérifié : `docs/security.mdx:41-56`]
- Cellule `guard` : refuse des commandes shell listées avant exécution (avec demande « Allow once / Deny »), documentée comme « pas une frontière de sécurité » (une édition de fichier mentionnant `rm -rf` n'est pas refusée). Son code est dans un dépôt externe épinglé et n'a pas été lu. [vérifié : `docs/security.mdx:52`, `cells/bundle.json:3`]
- Un `--sandbox` existe dans le code mais n'apparaît dans aucune doc : `src/gateway/sandbox.lisp` (562 lignes) lance l'organisme dans une prison via sandbox-runtime d'Anthropic (bubblewrap, seccomp, proxy d'autorisation de domaines sous Linux), shell hors prison en mode pristine, réseau cloisonné, domaines par défaut très limités. [vérifié : `sandbox.lisp:1-45`, recherche vide dans `README.md` et `docs/`]
- Secrets en prison : chaque clé d'API est remplacée par une sentinelle dans la prison, le proxy ne remet la vraie clé qu'à la sortie vers l'hôte du fournisseur. Un home qui a tourné en prison refuse d'être rechargé dehors tant que `nodecode sandbox review` puis `release --yes` n'ont pas eu lieu. [vérifié : `sandbox.lisp:21-33`, `src/gateway/secrets.lisp:1-14`]
- Chaîne de résolution des clés : config (valeur `!cmd`), `auth.json`, hooks, variable d'environnement, clé « public ». [vérifié : `proofs/CredentialChain.lean:4-12`]
- Fonctionnement sous macOS du mode `--sandbox` : non précisé. [déduit]

## 10. Extensibilité

- Cellule = dossier sous `~/.nodecode/cells/` avec un `.asd`, « présence = activé », chargé au démarrage ; deux formes : layer (définitions accumulées) et périphérique (système qui exporte `START-CELL`). [vérifié : `docs/CELLS.md:1-40`]
- Le DSL `define-cell` ouvre un scope d'enregistrement pour que l'arrêt d'une cellule retire tout ce qu'elle a ajouté (corrige un défaut où des commandes slash n'étaient jamais retirées). [vérifié : `src/organism/cell-dsl.lisp:1-35`]
- Une cellule peut définir, surcharger, ou conseiller une fonction par `hook` ; redéfinir un nom du noyau est verrouillé (piège : peut empêcher le démarrage, remède `nodecode --pristine`). Hooks nommés : `:tool`, `:frame`, `:credential`, `:round`. [vérifié : `docs/cell-api.mdx:327-345`, `:478-505`]
- Cellules livrées (20 entrées, dans un dépôt externe) : board, channels (discord, kit, slack, telegram), chrome, context, cron, cyber-security, experience, goal, guard, link, mcp, prs, qa, team, template, web, websearch. Hub : `nodecode add nc://NOM`. [vérifié : `cells/bundle.json`, `README.md:70`]
- MCP via la cellule `mcp` ; limites : pas de `cwd`, pas d'expansion `${VAR}`, pas d'autorisation par outil, pas d'OAuth. [vérifié : `README.md:164`, `docs/support.mdx:66-68`]
- Skills : définitions gardées comme les mémoires ; hooks de style Claude Code (JSON) : absents, les hooks sont du Lisp. [déduit]
- Sous-agents : `fork` ; cellule `team` (plusieurs sessions sur une tâche, `flock`), `board`, `goal` (boucle jusqu'à ce qu'un contrôle passe). [vérifié : `README.md:166-168`, `docs/eval.mdx:38-40`]
- Environ 38 commandes slash intégrées. [vérifié : `docs/slash-commands.mdx`]

## 11. Providers et modèles

- Quatre dialectes : `openai-completions`, `openai-responses`, `anthropic`, `google` ; champ `sdk` explicite, jamais deviné par sondage ; local via `base_url` (mlx_lm, Ollama). [vérifié : `README.md:218`, `docs/models.mdx:35-52`]
- Abstraction : une « taille unique » : la boucle ne consomme que des `STREAM-PART` et un message assemblé, seuls `provider.lisp` et les quatre fichiers de `engine/providers/` lisent le wire. L'usage distingue l'inconnu du zéro ; un flux sans marqueur de fin est une erreur, jamais un succès tronqué. [vérifié : `provider.lisp:1-22`]
- Spécificités : effort de raisonnement envoyé tel quel pour OpenAI, plafonné à `high` pour Google, budget ou adaptatif pour Anthropic ; transport WebSocket en plus ; catalogue de modèles via models.dev ; défauts sur un palier gratuit OpenCode Zen. [vérifié : `docs/models.mdx:241-246`, `provider.lisp:27-29`]
- Retries par fournisseur : 4 pour la requête, 5 pour le flux, délai d'inactivité 120 s, au plus 30 requêtes par appel (borne démontrée en Lean). [vérifié : `docs/models.mdx:250-262`, `proofs/RetryLadder.lean`]
- Bascule de modèle : chaîne partagée, déclencheurs `rate_limit`, `outage`, `slow_start`, `broken_answer`, `refusal`, avec « maintien après refus » en puissances de 2 plafonnées. [vérifié : `docs/models.mdx:280-300`]

## 12. Interfaces

- CLI `nodecode` (TUI natif maison issu de `cl-tuition`), plus `update`, `login`, `add`, `profile`, `gateway`, `web`, `resume`, `import`, `rpc`, `serve`, `generations`, `rollback`, `secrets`. [vérifié : `docs/cli.mdx`]
- Headless : `nodecode rpc [SESSION-ID]`, une commande JSON par ligne sur stdin, une frame par ligne sur stdout, schéma dans `src/gateway/protocol.schema.json`, reprise avec `--cursor`. WebSocket direct documenté mais RPC recommandé. [vérifié : `docs/rpc.mdx:6-33`]
- Web (`nodecode web`, jeton après `#` dans l'URL), accès distant via la cellule `link` (relais externe), bots Discord, Telegram, Slack. [vérifié : `README.md:131-158`, `docs/security.mdx:32`]
- Plateformes : Linux x86_64 (glibc 2.34+), macOS 15+ Apple Silicon, Windows x86_64 ; pas d'arm64 Linux ni de Mac Intel. [vérifié : `README.md:231-235`]
- Pas de SDK ni d'extension d'IDE documentés. [déduit]

## 13. Observabilité et évaluation

- Pas de traçage distribué. Observabilité par le journal d'événements durable, `/status`, `/context`, `/gc`, `/doctor`, `/usage` (aujourd'hui, 7 et 30 jours, appels annexes inclus) et un compteur de tour visible aussi du modèle. [vérifié : `docs/slash-commands.mdx`, `meter.lisp:1-12`, `docs/troubleshooting.mdx`]
- 7 preuves Lean 4 (2 706 lignes) en CI : paires d'événements et messages (jamais de résultat d'outil orphelin), borne de retries, ordre des clés, maintien après refus, sûreté de l'auto-édition, budget des fichiers d'instructions, délais d'ajout de cellule. Elles prouvent des modèles abstraits des politiques, pas le code Lisp ; le lien code-modèle n'est pas vérifié. [vérifié : `proofs/`, `.github/workflows/ci.yml` ; limite : déduit]
- Tests : 161 fichiers Lisp en miroir de `src/`, `just check` (lint, plafond de lignes, build, tests) ; CI avec portes de performance (instructions, octets alloués, CPU) et de passage à l'échelle (coût de chaque chemin chaud à 250, 1 000 et 4 000, pente bornée), plus un job nocturne de latence et de mémoire. [vérifié : `docs/README.md:11-17`, `perf/scaling.lisp:1-30`, `.github/workflows/`]
- Évaluation de l'agent : seul ARC-AGI-3, hors dépôt. Revendication du README : 25 jeux publics, 183 niveaux, score identique, 181 M de tokens (124 $) contre 393 M (210 $) pour Claude Code avec Opus 5.5, soit -54 % de tokens ; -66 % contre Codex avec GPT-6.1. [vérifié : `README.md:137-146`]
- Ce qui l'appuie : un texte du même éditeur (Foresight Labs FL-2026-006) ; dans le dépôt, uniquement les SVG des barres, aucun script de run ni log. Réserves du README : meilleur run retenu quand un jeu est rejoué, passage par une passerelle LiteLLM et un relais tiers, Codex joué via un adaptateur tiers. [vérifié : recherche dans tout le dépôt, `README.md:143-146`]
- La mesure porte sur les tokens, pas sur la réussite (égale) ; le gain vient probablement de l'édition du contexte et du cache. [déduit]

## 14. Idées à reprendre

| Idée | Pourquoi elle est bonne | Coût | Moment |
|---|---|---|---|
| Journal de requête avec empreinte du corps et octets de préfixe partagés | diagnostique les ruptures de cache de prompt au lieu de les deviner | faible | plus tard |
| Ligne de dépense ajoutée à chaque résultat d'outil, dans la copie du modèle seulement | le modèle voit budget et remplissage sans casser le préfixe en cache | faible | plus tard |
| Éviction par tours entiers avec stub et rappel exact (`recall-entry`) | pas de perte d'information, pas d'appel de résumé ; compatible journal en ajout seul | moyen | plus tard |
| Refus d'outil structuré (JSON avec indice de réparation et `retryable`) | le modèle corrige au lieu de réessayer à l'aveugle | faible | v0 |
| Budget de tour optionnel (secondes, appels, tokens) avec avertissement à 4/5 | borne le coût d'un tour sans plafond de rounds codé en dur | faible | v0 |
| Clés remplacées par des sentinelles dans l'environnement isolé, remises à la sortie réseau | répond au risque « clé API lisible depuis le conteneur » | élevé | plus tard (itération sécurité) |
| Section volatile du prompt placée en dernier et changements par diff de rappel | préserve le préfixe en cache | faible | v0 |
| Réchauffage du cache quand l'économie dépasse le coût | utile pour les sessions interactives à pauses | moyen | plus tard |
| Portes de passage à l'échelle en CI (coût d'un chemin chaud à 3 tailles) | attrape les régressions de complexité tôt | moyen | plus tard |
| Définition retenue puis validée au premier retour, sinon retour arrière | modèle sûr d'auto-modification | élevé | non prioritaire |

## 15. Limites et points d'attention

- Sécurité : `eval`, cellules plein pouvoir et messages de salon donnent l'autorité de l'hôte ; `guard` n'est pas une frontière ; le masquage des secrets est cosmétique. Le mode `--sandbox` existe mais n'est pas documenté, et la doc répète « no sandbox ». [vérifié : `docs/security.mdx:44-56`, `sandbox.lisp`]
- Le chiffre ARC-AGI-3 est auto-déclaré, non reproductible depuis le dépôt, et ne dit rien de la qualité en génie logiciel. [vérifié et déduit : voir section 13]
- Ces points ont été vérifiés dans le code, et non lus dans la doc : appels d'un round exécutés en séquence malgré l'annonce du parallèle ; aucun plafond de rounds par défaut ; garde de boucle absente pour Claude ; un seul fichier d'instructions lu par dossier, un fichier de plus de 64 Ko ignoré en entier. [vérifié : `turn.lisp:3921-3925`, `meter.lisp:79-84`, `loop-guard.lisp`, `context.lisp:1686-1690`]
- Auto-modification : un layer défectueux peut empêcher le démarrage (remède `--pristine`) ; les fichiers de layer qui échouent au démarrage lancent une session `layer` qui consomme des tokens ; le prompt système et la boucle sont modifiables par l'agent. [vérifié : `docs/cell-api.mdx:500`, `docs/eval.mdx`]
- Rollback d'une mise à jour après migration du schéma du store : manuel (copie de `history.db`). [vérifié : `docs/updates.mdx:174-180`]
- Dépendances à des services de l'éditeur : flux de versions, hub de cellules, relais `link`, catalogue models.dev, modèles maison. [vérifié : `README.md:239`, `docs/support.mdx:62-73`]
- Plateformes limitées, suite Windows avec rouges connus, `team` non vérifié hors Linux. [vérifié : `docs/support.mdx`, `.github/workflows/ci.yml`]
- Projet très jeune et rapide : dates du README d'octobre et novembre 2026, rubriques « Unfinished » dans les docs. [vérifié : `README.md:19`, `docs/changelog.mdx`]
- Code des cellules (dont `guard`, `mcp`, `team`, `web`) hors de ce dépôt, non audité. [vérifié : `cells/bundle.json`]

## 16. Sources

- https://nodecode.ai/ et https://nodecode.ai/agent (lus le 2026-11-20).
- https://github.com/nodecode-ai/nodecode, commit `fed3cb71523c36f2afe4207b7d981fb454264ff1`, fichiers : `README.md`, `LICENSE`, `cells/bundle.json`, `docs/{README,eval,context,sessions,instructions,security,models,gateway,organism,CELLS,cell-api,rpc,updates,support,slash-commands,cli,changelog,troubleshooting}.mdx|md`, `src/engine/{turn,exec,context,working-context,loop-guard,cache-warming,meter,provider}.lisp`, `src/engine/working-context.md`, `src/organism/{scribe,knowledge,cell-dsl}.lisp`, `src/session/recall.lisp`, `src/gateway/{sandbox,secrets}.lisp`, `proofs/*.lean`, `perf/scaling.lisp`, `.github/workflows/`.
