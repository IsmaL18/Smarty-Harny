# Grille d'analyse commune des harness

Chaque fiche de `docs/veille/` suit cette grille, dans cet ordre, pour rendre les harness comparables.
Chaque affirmation est marquée **[vérifié]** (lu dans le code ou la doc officielle, avec source) ou **[déduit]** (interprétation, comportement observé, source secondaire).

1. **Identité** — éditeur, licence, langage, version ou commit étudié, date de l'étude.
2. **Philosophie et positionnement** — ce que le harness cherche à être, ses partis pris assumés.
3. **Architecture globale** — composants principaux, séparation noyau / interface, flux de données.
4. **Boucle agent** — déroulé d'un tour, condition d'arrêt, appels d'outils parallèles, streaming, gestion des erreurs et des retries, interruption par l'utilisateur.
5. **Prompt système** — taille, contenu, construction (statique ou dynamique), injection de l'environnement.
6. **Outils** — liste, définition des schémas, format d'édition de fichiers, outil shell, recherche dans le code.
7. **Gestion du contexte** — fichiers d'instructions projet (CLAUDE.md, AGENTS.md…), compaction, troncature des sorties d'outils, prompt caching, budget de tokens.
8. **Mémoire et persistance** — sessions, reprise, historique, mémoire long terme.
9. **Permissions et sandbox** — modèle d'approbation, règles, isolation (conteneur, seatbelt, landlock…), réseau, secrets.
10. **Extensibilité** — MCP, skills, hooks, plugins, sous-agents, commandes personnalisées.
11. **Providers et modèles** — fournisseurs supportés, abstraction, spécificités exploitées.
12. **Interfaces** — CLI, TUI, mode headless / non interactif, SDK, serveur, IDE.
13. **Observabilité et évaluation** — logs, traces, coûts, télémétrie, benchmarks publiés.
14. **Idées à reprendre** — tableau : idée, pourquoi elle est bonne, coût d'implémentation (faible / moyen / élevé), moment (v0 / plus tard).
15. **Limites et points d'attention** — faiblesses, critiques connues, risques.
16. **Sources** — URL et chemins de fichiers (avec commit) consultés.
