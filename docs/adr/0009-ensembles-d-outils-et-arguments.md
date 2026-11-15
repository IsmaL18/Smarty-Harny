# ADR-0009 — Ensembles d'outils et normalisation des arguments

Statut : proposé · Spec : 002 §4.6, §4.8, CA-46 à CA-51 · Amende : ADR-0002 (§2), ADR-0007 (§2, §4)

## Contexte

La 002 ajoute un quatrième outil, des ensembles d'outils choisis par la configuration, et une tolérance aux erreurs de forme des arguments. Le registre de l'ADR-0002 (`ToolRegistry`) valide déjà les arguments avec `jsonschema` et renvoie toute erreur comme résultat.

## Décision

### Ensembles d'outils

1. **Catalogue et ensembles en code** (`tools/toolsets.py`) : `TOOLSETS = {"full": [read_file, write_file, edit_file, shell], "read_only": [read_file]}`. Les noms d'ensembles utilisés dans la configuration sont `full` (défaut) et `read_only`.
2. **Configuration** : clé `[tools] toolset = "full"` (ADR-0007). Un nom inconnu est refusé au chargement de la config avec un message en français qui nomme l'ensemble et liste ceux qui existent ; aucune session ne s'ouvre (CA-50). Le lancement affiche l'ensemble actif (CA-51).
3. **Le registre n'expose que l'ensemble actif** : `specs()` ne liste que ces outils ; un appel hors ensemble tombe dans la branche existante « outil inconnu » (`error: unknown tool 'x' (available: …)`), sans exécution (CA-49). Aucun changement de contrat.
4. **État de session par injection** : `main.py` construit le suivi des fichiers lus (ADR-0010) et le magasin de sorties (ADR-0011), et les passe aux constructeurs des outils. Le protocole `Tool` ne change pas.

### Normalisation des arguments

5. **Coercition pilotée par le schéma**, dans le registre, entre le décodage JSON et `jsonschema.validate` : une fonction `coerce_arguments(args, schema)` (`tools/arguments.py`), valable pour tous les outils, récursive sur les objets et les éléments de tableau.
6. **Règles strictes** (en cas de doute, l'appel échoue) :
   - entier : texte conforme à `^-?\d+$` ; nombre : `^-?\d+(\.\d+)?$` ;
   - booléen : `true` ou `false` seulement, sans tenir compte de la casse (ni `1`, ni `yes`) ;
   - tableau : un texte qui s'évalue en liste JSON devient cette liste ; un objet seul est enveloppé dans une liste ; un autre texte n'est pas deviné ;
   - objet : un texte JSON valide qui s'évalue en objet.
7. **Erreurs conservées** : argument manquant, argument inconnu (`additionalProperties: false`), type non convertible, JSON invalide. Le message nomme l'argument et la forme attendue, par exemple `error: invalid argument 'limit': expected integer, got "beaucoup"`. Les marqueurs de l'ADR-0002 restent stables.

## Options considérées

| Sujet | Option | Pour | Contre |
|---|---|---|---|
| Ensembles | **A. En code, choix par la config** (retenue) | aucune abstraction nouvelle | un nouvel ensemble demande une modification du code |
| | B. Étiquettes portées par chaque outil | extensible | indirection inutile pour deux ensembles |
| | C. Ensembles définis dans le TOML | flexible | combinaisons absurdes ; la spec n'en veut que deux |
| Arguments | **A. Coercition générique pilotée par le schéma** (retenue) | une seule règle pour tous les outils ; testable par comportement | un petit module à maintenir |
| | B. Correction dans chaque outil | proche de l'outil | répétée, cas oubliés |
| | C. Validation tolérante Pydantic | peu de code | dépendance ajoutée (rejet de l'option B de l'ADR-0002) ; conversions trop larges |

## Conséquences

- **`read_only` n'est pas une sécurité** : c'est une restriction de ce que le modèle voit et peut appeler (spec §6, It. 4). Sans shell, l'agent ne peut ni chercher (pas de grep) ni lancer de vérifications ; acceptable en v1 (spec §9 q.5), à réévaluer avec l'outil de recherche.
- **« Remplacer partout » écarté en v1** (spec §9 q.1) : le modèle liste chaque occurrence. Un paramètre booléen pourra être ajouté plus tard sans casser le contrat.
- `config.example.toml` et le README documentent la clé `toolset`.
- Comportements à tester (CA-46 à CA-51) : mêmes résultats avec les formes corrigées, erreurs nommées pour les formes non convertibles, ensemble inconnu refusé au lancement, appel hors ensemble sans effet.
