# ARCHITECTURE

Orientation durable du harness. Le détail et les alternatives écartées sont dans `docs/adr/`.

## Frontières

- **Noyau** (`session`, `tools`, `models.base`, `cost`) : boucle agent `asyncio`, historique en ajout seul, outils, limites. Il émet des événements typés ; il n'écrit pas dans le terminal et ne pose pas de question (ADR-0001, 0008).
- **Interfaces** (`cli` aujourd'hui, TUI et API serveur ensuite) : consomment le flux d'événements ; seules à interagir avec l'utilisateur.
- **Fournisseurs** : derrière le protocole `ModelClient` ; LiteLLM n'est importé que par son adaptateur (ADR-0003).
- **Système** : les outils n'agissent que par l'interface `Environment` (ADR-0002).
- **Sécurité** : la frontière est le conteneur Docker, dont le seul chemin hôte visible est le dossier de travail ; pas de permissions applicatives avant l'it. 4 (ADR-0006).

## Dépendances

`cli → session → {models.base, tools, cost}` ; jamais l'inverse. Seul `cli/main.py` lit l'environnement et câble les implémentations réelles.

## Principes

1. Une erreur d'outil est un résultat renvoyé au modèle ; chaque appel d'outil reçoit exactement un résultat (ADR-0002).
2. L'historique est au format OpenAI chat, indépendant du fournisseur, en ajout seul (ADR-0001).
3. Les limites sont vérifiées avant chaque appel au modèle ; l'interface pose « continuer ? » (ADR-0001).
4. Un coût inconnu n'est jamais 0 (ADR-0004).
5. La configuration vit hors du dossier de travail de l'agent (ADR-0007).
6. Le modèle ne voit que les outils de l'ensemble actif, choisi par la configuration ; les arguments sont normalisés selon le schéma de l'outil, en cas de doute l'appel échoue (ADR-0009).
7. Une modification de fichier est refusée sans effet si elle est ambiguë ou périmée : fichier lu au préalable, empreinte du contenu, tout ou rien (ADR-0010).
8. Une sortie trop longue garde son début et sa fin ; la version complète d'une commande vit dans `.harness/` du dossier de travail, ignoré par Git et supprimé en fin de session (ADR-0011).
