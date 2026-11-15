---
title: "Conception des outils d'un agent LLM"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: concept
date: 2026-11-15
---

## Définition exacte & périmètre

Les outils sont l'interface entre un agent et la machine. Chaque outil est un contrat en trois parties : un nom, une description en langage naturel, un schéma JSON des arguments. Le modèle ne voit que ce contrat. Il décide seul quand et comment l'appeler. Le harness valide, exécute, borne la sortie et renvoie un résultat.

Principe central : le lecteur de l'interface est un LLM, pas un développeur. Il ne lit pas la documentation à côté. Il n'a que la description, le schéma et les messages d'erreur. Concevoir un outil, c'est concevoir du prompt.

Ce que ce n'est pas : un mécanisme de sécurité. Choisir quels outils le modèle voit façonne son comportement. Cela ne limite pas ce que le processus peut faire. Les permissions, le sandbox et l'isolation relèvent d'autres couches.

## Mécanismes

### Description et schéma comme prompt

Le noyau commun des harness est court : lire, écrire, éditer, exécuter une commande shell. La recherche passe souvent par `rg` dans le shell. Chaque outil ajouté coûte des tokens à chaque appel et élargit le choix du modèle. Peu d'outils à fort impact valent mieux que des enveloppes fines d'API.

Les principes publiés par Anthropic tiennent en quelques règles. Des noms clairs et des espaces de noms. Des réponses lisibles (noms plutôt qu'identifiants opaques). Un paramètre de verbosité (concis ou détaillé) quand la sortie peut être grosse. Une pagination et une troncature qui disent comment affiner. Une description rédigée comme pour un nouvel arrivant.

Le contenu de la description change le comportement. Écrire « lire le fichier avant de l'éditer » dans la description de l'outil d'édition suffit à orienter les appels. Les prérequis, les cas d'usage et les alternatives vont dans la description, pas dans le prompt système seul. Une description ne doit jamais nommer un outil absent de l'ensemble actif : le modèle pourrait appeler un outil qui n'existe pas.

Le schéma déclare les types, les champs obligatoires et, idéalement, `additionalProperties: false`. Ainsi un argument inconnu est rejeté au lieu d'être ignoré en silence. Un modèle qui invente un champ apprend tout de suite qu'il s'est trompé.

### Une erreur est un résultat

Un appel mal formé ne lève jamais d'exception dans la boucle. Outil inconnu, JSON illisible, argument manquant, mauvais type, échec à l'exécution : tout devient un résultat marqué en erreur, renvoyé au modèle. Chaque appel reçoit exactement un résultat, sinon l'historique devient invalide pour l'API.

Le message d'erreur est le seul guide du modèle. Il doit nommer l'argument fautif, dire la forme attendue et, si possible, donner un exemple. « Argument invalide » force un nouvel essai à l'aveugle. « `timeout` doit être un entier en secondes, reçu "abc" » se corrige au coup suivant. Le même principe vaut pour les troncatures : dire quoi faire ensuite (lire par pages avec `offset` et `limit`, restreindre la recherche).

### Normalisation et coercition

Les modèles se trompent de façon régulière sur la forme des arguments. Quelques défauts sont fréquents : un nombre envoyé comme chaîne, un booléen envoyé comme chaîne, un tableau ou un objet envoyé sérialisé en texte JSON, un objet seul là où un tableau est attendu. Pi normalise les arguments avant la validation (chaîne JSON vers tableau, objet seul vers liste). Cela absorbe les défauts connus sans coût pour le modèle.

La coercition est pilotée par le schéma, pas devinée. Le schéma dit ce que le champ doit être. La normalisation convertit seulement ce qui a une lecture non ambiguë.

| Valeur reçue | Type attendu | Résultat |
|---|---|---|
| `"5"` | entier | `5` |
| `"true"` / `"false"` | booléen | `true` / `false` |
| `"[1, 2]"` (texte JSON) | tableau | `[1, 2]` |
| `"{\"a\": 1}"` (texte JSON) | objet | `{"a": 1}` |
| objet seul | tableau d'objets | tableau d'un élément |
| `"1"`, `"yes"`, `"oui"` | booléen | erreur |
| `"5.5"` | entier | erreur |

La règle : en cas de doute, l'appel échoue. Une coercition trop généreuse transforme une erreur du modèle en action exécutée avec une valeur imprévue. Pour un outil qui écrit ou supprime, mieux vaut un échec explicite qu'une interprétation optimiste. La normalisation s'applique avant la validation, la validation reste stricte.

### Ensembles d'outils (toolsets)

Un toolset est un ensemble nommé d'outils actifs. Il sert à adapter l'agent à une tâche ou à un contexte : un profil de code (noyau sans messagerie, sans génération d'image, sans planification), un profil lecture seule, un profil pour un canal peu fiable. Hermes déclare des toolsets nommés qui s'incluent entre eux et des postures. Un outil n'est exposé que si un toolset le nomme et si sa condition de disponibilité passe.

Un outil hors de l'ensemble actif est traité comme un outil inconnu. Même branche d'erreur, même message : le modèle ne peut pas distinguer « n'existe pas » de « désactivé ». C'est cohérent et simple, et cela évite une seconde voie d'erreur à maintenir.

Changer d'ensemble en cours de conversation modifie la liste des outils envoyée au modèle. Cela casse le préfixe du prompt caching. Fixer l'ensemble au démarrage de la session.

## Implémentation & patterns

Un registre unique. Chaque outil s'enregistre avec son nom, sa description, son schéma et son handler. Le registre est le seul point d'exécution : il résout le nom, normalise, valide contre le schéma, exécute, convertit toute exception en résultat d'erreur et borne la sortie. Seule l'annulation le traverse.

Valider le schéma à l'enregistrement. Un schéma invalide fait échouer toute la requête au fournisseur, sans nommer le coupable. Détecter l'erreur au démarrage, avec le nom de l'outil.

Ordre du pipeline : outil connu et actif, texte JSON décodé, normalisation guidée par le schéma, validation stricte (types, champs obligatoires, champs inconnus), exécution, troncature de la sortie. Chaque étape qui échoue produit un message qui nomme l'argument et la forme attendue.

```python
def coerce(value, schema):
    # Coercition guidée par le schéma, stricte : None = impossible, l'appel échoue.
    t = schema.get("type")
    if t == "integer" and isinstance(value, str):
        return int(value) if value.strip().lstrip("-").isdigit() else None
    if t == "boolean" and isinstance(value, str):
        return {"true": True, "false": False}.get(value.strip().lower())
    if t in ("array", "object") and isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if t == "array" and isinstance(value, dict):
        return [value]
    return value
```

Sorties bornées. Tronquer avec un message qui dit quoi faire, et conserver la sortie complète ailleurs (fichier, journal de session). Le modèle choisit parfois lui-même son budget de sortie, comme dans le shell de Codex.

Outils d'édition. Le remplacement exact d'une chaîne, avec unicité exigée, est le plus robuste. Pi ajoute un appariement flou de repli (normalisation Unicode, fins de ligne). Une lecture préalable obligatoire, énoncée dans la description et vérifiée à l'exécution, évite les éditions à l'aveugle.

Testabilité. Tester à la frontière observable : ce que le modèle reçoit comme résultat pour un appel mal formé, pour un outil inconnu, pour un argument inconnu. Pas la fonction de coercition en soi.

## Limites & anti-patterns

> [!warning] Un toolset restreint n'est pas une sécurité
> Retirer les outils d'écriture ne rend pas l'agent inoffensif. S'il garde un shell, il écrit, supprime et appelle le réseau par ce biais. Un ensemble « lecture seule » limite ce que le modèle voit et propose. Il ne protège rien. La protection exige un sandbox, des permissions appliquées par le système ou un conteneur sans accès sensible.

Le coût inverse existe aussi. Un ensemble restreint prive l'agent de recherche et de vérification : sans moyen de lancer les tests ou de chercher dans le code, il travaille à l'aveugle et affirme sans contrôler. Restreindre sans mesurer ce que cela retire dégrade la fiabilité.

Coercition trop permissive. Accepter `1`, `yes` ou `oui` pour un booléen, tronquer `5.5` en `5`, deviner un type : l'appel devient ambigu et l'erreur du modèle se transforme en action. Garder la liste des conversions courte et sans ambiguïté.

Erreurs muettes. Ignorer un argument inconnu, renvoyer « erreur » sans détail, lever une exception qui traverse la boucle. Le modèle ne peut ni corriger ni comprendre.

Descriptions qui contredisent l'ensemble actif. Une description qui renvoie à un outil absent pousse le modèle à l'appeler. Construire les renvois dynamiquement selon l'ensemble actif.

Trop d'outils. Chaque définition consomme du contexte à chaque appel et dilue le choix. Certains harness différent le chargement des schémas rarement utilisés et ne gardent que les noms dans le contexte.

Compter sur un mock pour valider le contrat. Un faux outil prouve l'orchestration, jamais que l'outil réel accepte les arguments décrits par son schéma. Garder au moins un test qui exerce le vrai chemin de validation et d'exécution de chaque outil réel.

Description jamais évaluée. La qualité d'un outil se mesure sur des tâches réalistes à plusieurs appels, en lisant les transcripts en entier. Une description qui paraît claire à son auteur peut être mal comprise par le modèle.

## État de l'art & références

Convergences : noyau court (lecture, écriture, édition, shell), schémas JSON, erreurs renvoyées au modèle, sorties bornées avec indication de suite, outils différés pour les gros catalogues, schémas versionnés en test pour détecter les dérives. Hermes maintient un instantané du prompt et de la liste des outils, et casse la CI si les schémas changent sans mise à jour volontaire. Codex déclare `additionalProperties: false` et un schéma de sortie sur ses outils.

Divergences : format d'édition (remplacement de chaîne, patch propre au fournisseur, liste de paires), niveau de normalisation des arguments (Pi la fait avant validation, d'autres rejettent), granularité des ensembles (profils nommés chez Hermes, liste plate ailleurs), chargement des schémas (immédiat ou différé).

Débats ouverts : un outil par action ou un outil généraliste (shell seul) ; coercition tolérante ou stricte selon la capacité du modèle ; outils exprimés en code que le modèle écrit plutôt qu'en appels JSON ; la place des descriptions longues quand le préfixe doit rester stable et court.

#### Ressources utiles :
- [Writing tools for agents (Anthropic)](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Pi coding agent — article de conception](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)
- [Codex (outils et schémas)](https://github.com/openai/codex)
- [Hermes Agent (registre d'outils et toolsets)](https://github.com/NousResearch/hermes-agent)
