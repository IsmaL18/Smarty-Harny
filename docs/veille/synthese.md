# Synthèse comparative des harness étudiés

Panorama du 2026-11-15. Sources détaillées dans les fiches :

| Harness | Fiche | Version étudiée | Langage | Nature |
|---|---|---|---|---|
| Claude Code (Anthropic) | [claude-code.md](claude-code.md) | 2.1.325 (dépôt public `0cb75ce`) | propriétaire | agent de code, référence du marché |
| Codex CLI (OpenAI) | [codex.md](codex.md) | commit `ee344ca` | Rust | agent de code open source |
| Hermes Agent (Nous Research) | [hermes-agent.md](hermes-agent.md) | commit `77a30e9` | Python | agent généraliste, mémoire, skills, multi-plateforme |
| Pi (Mario Zechner) | [pi.md](pi.md) | commit `04fd089` (v1.5.2) | TypeScript | agent de code minimaliste |

Les points marqués [déduit] ou non vérifiés dans les fiches le restent ici. Ces outils évoluent chaque mois : cette synthèse est datée.

## 1. Ce sur quoi les quatre convergent

Ces points font consensus ; on les prend comme principes de conception dès la v0.

1. **La boucle est simple.** Appel du modèle → exécution des outils demandés → résultats renvoyés → nouvel appel, jusqu'à une réponse sans appel d'outil. Aucun ne repose sur un planificateur explicite. La complexité vit autour de la boucle (contexte, outils, sécurité), pas dedans.
2. **Le noyau émet des événements typés, les interfaces les consomment.** CLI, TUI, IDE, API serveur et mode headless lisent le même flux. C'est ce qui permet notre trajectoire CLI → TUI → API sans réécrire le noyau.
3. **Une erreur d'outil est un résultat, pas une exception.** Outil inconnu, arguments invalides, échec, annulation : le modèle reçoit un message d'erreur exploitable, et chaque appel d'outil reçoit exactement un résultat, sinon l'historique est corrompu.
4. **Peu d'outils, bien décrits.** Le noyau commun est lire / écrire / éditer / shell ; la recherche passe souvent par `rg` dans le shell. Chaque outil ajouté coûte des tokens à chaque appel (Hermes en fait une règle de revue).
5. **Les sorties d'outils sont bornées.** Troncature avec un message qui dit quoi faire ensuite, et sortie complète conservée ailleurs (fichier ou journal de session).
6. **Les sessions sont des journaux JSONL en ajout seul.** Reprise, audit, rejeu, évaluation hors ligne.
7. **Les instructions projet viennent de fichiers** (`AGENTS.md`, `CLAUDE.md`), concaténés du global vers le projet, avec un budget.
8. **Le préfixe de la requête est sacré pour le prompt caching.** Prompt système et outils stables, conversation en ajout seul ; ce qui change (environnement, rappels, mémoire) passe par des messages, jamais par une réécriture du préfixe. Hermes et Claude Code l'énoncent explicitement, Codex l'applique par ses messages « contextuels ».
9. **La compaction commence par le gratuit.** D'abord élaguer les vieux résultats d'outils, ensuite seulement résumer avec un modèle.
10. **Les skills se chargent par divulgation progressive** (nom + description dans le contexte, corps à la demande) chez Claude Code, Hermes et Pi.

## 2. Ce sur quoi ils divergent

| Axe | Claude Code | Codex | Hermes Agent | Pi |
|---|---|---|---|---|
| **Philosophie** | produit complet, extensible par tout (hooks, skills, plugins, sous-agents) | agent de code sûr par défaut, réglé pour les modèles OpenAI | agent personnel de longue durée qui s'auto-améliore ; noyau étroit, capacités aux bords | minimalisme assumé, contrôle total par l'utilisateur |
| **Édition de fichiers** | remplacement exact de chaîne, unicité exigée, lecture préalable obligatoire | `apply_patch` (format de patch propre à OpenAI) avec correspondance dégradée | outil `patch` (format non vérifié) | liste de paires `{oldText, newText}` contre l'original, puis appariement flou de repli |
| **Sécurité** | règles `deny > ask > allow` + sandbox OS (seatbelt/bubblewrap) + proxy réseau | deux axes séparés : politique de sandbox × politique d'approbation ; escalade après refus ; règles de préfixes de commandes | approbation `manual/smart/off`, motifs interdits, backend `local` par défaut (sans isolation) mais backend Docker durci disponible | aucune permission dans le noyau : la frontière est l'environnement d'exécution |
| **Compaction** | automatique à l'approche de la limite, instructions configurables | résumé de passation très court + messages utilisateur conservés, sorties d'outils écartées | 4 phases (élagage, bornes, résumé structuré par modèle auxiliaire, recompression itérative) | seuil + résumé structuré itératif, entrée de compaction qui n'efface rien |
| **Mémoire long terme** | fichiers `CLAUDE.md` + mémoire automatique | non approfondie | deux fichiers plafonnés + recherche plein texte dans les sessions (SQLite FTS5) | aucune au-delà des sessions |
| **Sessions** | JSONL, reprise, fork | JSONL distinct de l'historique en mémoire | SQLite | JSONL en arbre (`id`/`parentId`), branches |
| **Providers** | Anthropic | OpenAI (couplage fort) | multi-provider, profils en plugins | multi-provider, abstraction maison (`ai`) |
| **Extensibilité** | hooks, skills, sous-agents, MCP, plugins | hooks, MCP, sous-agents | registre d'outils auto-découvert, toolsets, skills auto-créés, plugins, MCP | hooks de boucle, extensions, skills ; MCP ajouté tardivement |
| **Interfaces** | TUI, headless, SDK, IDE, web | TUI cliente d'un app-server, exec, serveur MCP | CLI, TUI, desktop, web, passerelles de messagerie | TUI, print, JSONL, RPC stdio |
| **Taille** | très large (139 entrées de changelog sur une version) | `turn.rs` 3 800 lignes, session 248 Ko | `agent/` ≈ 146 000 lignes | le plus petit, mais a beaucoup grossi depuis 2025 |

## 3. Le meilleur de chacun, pour notre harness

| Harness | Ce qu'on lui prend | Ce qu'on ne lui prend pas |
|---|---|---|
| **Pi** | la boucle minimale à événements et hooks (`beforeToolCall`, `afterToolCall`, `transformContext`) ; le prompt court en sections nommées ; les opérations d'outils pluggables (point d'insertion du conteneur) ; la normalisation des arguments ; l'échec des appels d'un message coupé par `length` ; les sessions en arbre | l'absence totale de garde-fous ; la dérive récente vers une dizaine de paquets |
| **Claude Code** | l'édition par remplacement exact ; les erreurs et troncatures qui guident le modèle ; les règles `deny > ask > allow` ; les modes de permission (`dontAsk` pour l'API) ; la hiérarchie `AGENTS.md` ; les sous-agents à contexte isolé ; les plafonds de tours et de coût | la dépendance aux fonctions propres à l'API Anthropic ; le classifieur de permissions par modèle |
| **Codex** | les deux axes sandbox × approbation ; l'escalade après refus ; les chemins protégés en lecture seule (`.git` monté `:ro`) ; le verrou lecteurs/écrivain pour le parallélisme ; la troncature au milieu avec en-tête ; le résumé de passation ; la politique de retry par type d'erreur | `apply_patch` ; la compaction distante opaque ; la structure monolithique de `turn.rs` |
| **Hermes** | l'invariant de préfixe stable et le test de « surface du prompt » ; le registre d'outils, les toolsets et les postures ; l'ABC `BaseEnvironment` et la recette Docker durcie ; la compaction en 4 phases ; le débordement des sorties sur disque ; la mémoire plafonnée et la recherche FTS5 ; le gel des drapeaux de contournement | l'architecture d'ensemble (trop grosse) ; la boucle à threads ; l'auto-création de skills sans curator |

## 4. Tensions à arbitrer au fil des itérations

- **Minimalisme ou garde-fous ?** Pi délègue toute la sécurité à l'environnement, Codex et Claude Code l'intègrent au noyau. Notre choix (harness entier dans Docker) rejoint Pi pour la v0 ; les permissions arrivent dans une itération dédiée, sous forme de hooks pour ne pas alourdir la boucle.
- **Multi-provider ou fonctions propres à un fournisseur ?** Le prompt caching, le thinking et certains formats d'outils diffèrent selon les fournisseurs. LiteLLM masque le transport, pas ces différences : la classification d'erreurs, la table des capacités par modèle et le marquage `cache_control` restent à notre charge.
- **Clé API dans le conteneur.** Claude Code et Hermes insistent sur l'absence de secrets dans l'environnement d'exécution (proxy d'identifiants, liste blanche `forward_env`). Risque accepté pour démarrer, à traiter dans l'itération sécurité.
- **Synchrone ou `asyncio` ?** Hermes paie cher sa boucle à threads (interruptions, timeouts). Une boucle `asyncio` dès le départ facilite parallélisme, interruption et API serveur, au prix d'une marche d'apprentissage un peu plus haute.

## 5. Principes de conception retenus pour la v0

Issus des convergences, à respecter dès la première ligne de code même quand la fonctionnalité complète vient plus tard :

1. Boucle bornée (`max_turns`, budget) qui rend un résultat typé.
2. Noyau sans dépendance à l'interface : il émet des événements typés.
3. Un résultat par appel d'outil, erreurs renvoyées au modèle.
4. Exécution des outils derrière une interface d'environnement (`BaseEnvironment`), pour pouvoir changer de backend.
5. Historique en ajout seul, jamais réécrit (prépare le prompt caching et la compaction).
6. Coût et tokens comptés à chaque appel (LiteLLM les fournit).
