# ADR-0002 — Contrat des outils et retour des erreurs au modèle

Statut : proposé · Spec : §4.2, CA-5 à CA-11 · Notion : `tool-calling`

## Contexte

Trois outils : lecture, écriture, commande shell. Toute erreur d'action doit être rendue au modèle sans faire planter la session (synthèse §1.3 : une erreur d'outil est un résultat, pas une exception). Les tests doivent pouvoir reconnaître sans ambiguïté les cas de troncature, délai dépassé, interruption.

## Décision

1. **Contrat** : un outil = nom, description, schéma JSON des paramètres (écrit à la main, visible dans le code), et `async run(args, env) -> ToolResult`. `ToolResult(content: str, is_error: bool)`, texte seul. Noms : `read_file(path)`, `write_file(path, content)`, `shell(command)`.
2. **Un point d'exécution unique** (`ToolRegistry.execute(tool_call) -> ToolResult`) qui garantit **exactement un résultat par appel** : outil inconnu, arguments JSON illisibles, arguments invalides (validation par la bibliothèque `jsonschema` contre le schéma de l'outil), exception quelconque de l'outil → `ToolResult(is_error=True)` avec un message qui dit quoi corriger. Seule `CancelledError` (Ctrl+C) traverse (ADR-0005).
3. **Langue des messages destinés au modèle : anglais**, avec des **marqueurs stables** entre crochets que les tests et le modèle reconnaissent. Les messages affichés à l'utilisateur restent en français.

   | Cas | `content` | `is_error` |
   |---|---|---|
   | lecture OK | contenu du fichier | non |
   | fichier absent / illisible | `error: <cause>` | oui |
   | fichier binaire (octet NUL dans les 8 premiers Ko, ou UTF-8 invalide) | `error: binary file, not read` | oui |
   | contenu > `max_read_chars` | début du contenu + `[TRUNCATED: showing first N of M characters]` | non |
   | écriture | `wrote N characters to <path>` (dossiers parents créés, fichier écrasé sans question) | non |
   | commande | sortie (stdout+stderr fusionnés) + `[exit code: N]` | oui si N ≠ 0 |
   | sortie > `max_output_chars` | début de la sortie + `[TRUNCATED: ...]` (avant `[exit code]`) | selon code |
   | délai dépassé | sortie partielle + `[TIMEOUT: killed after Ns]` | oui |
   | interruption | `[INTERRUPTED by user]` ; appels non exécutés : `[NOT RUN: turn interrupted by user]` | oui |
   | outil inconnu / arguments invalides | `error: unknown tool 'x'` / `error: invalid arguments: <détail>` | oui |

4. **Message coupé par `length`** (inspiration Pi) : si la réponse du modèle se termine par `finish_reason = length` et contient des appels d'outils, ils ne sont pas exécutés (arguments probablement tronqués) ; chacun reçoit `error: your message was cut off by the output limit; retry with smaller content`.
5. **Chemins** : relatifs au dossier de travail du processus ; absolus acceptés. **Aucun contrôle de confinement dans les outils** : la frontière est le conteneur (ADR-0006), comme chez Pi. Un contrôle applicatif sur `read_file`/`write_file` serait contourné par `shell` et donnerait une fausse impression de sécurité.
6. **Shell** : `bash -c <commande>`, répertoire = dossier de travail, `stdin` fermé (une commande interactive ne peut pas bloquer), stderr fusionné dans stdout, **pas d'état persistant entre deux appels** (un `cd` ne survit pas ; dit dans la description de l'outil). Lecture incrémentale de la sortie, tampon plafonné à `max_output_chars` + compteur de ce qui est écarté, pour qu'une commande bavarde (`yes`) ne sature pas la mémoire.
7. **Interface `Environment`** (Pi, Hermes `BaseEnvironment`) : les outils n'accèdent au système que par `read_bytes`, `write_bytes`, `run(command, timeout)`. Une seule implémentation en v0 (`LocalEnvironment`, qui s'exécute dans le conteneur), pour qu'une itération ultérieure change de backend sans toucher aux outils.
8. **Troncature en v0** : on garde le début, on dit combien est omis. Le « au milieu + débordement disque » est l'it. 2.

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. Registre maison + `jsonschema` + `ToolResult` texte** (retenue) | simple, lisible, erreurs uniformes | schémas écrits à la main |
| B. Pydantic pour schémas et validation | moins de répétition | magie cachée, moins pédagogique |
| C. Lever des exceptions, les capter dans la boucle | moins de code dans les outils | risque d'appel sans résultat → historique corrompu ; erreurs non uniformes |
| D. Contrôle de chemins dans les outils | défense en profondeur apparente | contourné par `shell` ; faux sentiment de sécurité |

## Conséquences

- Les marqueurs du tableau sont **le contrat** que les tests vérifient (comportement visible du modèle) ; les changer = amender l'ADR.
- **CA-4 n'est pas testable en automatique** au sens strict : sans conteneur, rien n'empêche de lire `/etc/passwd`. Testable : les chemins relatifs partent du dossier de travail. L'isolation réelle est validée avec CA-25 (humain). À signaler à la relecture de la spec (§8 la classe dans les tests automatisés).
- Le texte des messages d'erreur guide le modèle ; il sera retravaillé à l'it. 2.
- Une seule implémentation d'`Environment` est une abstraction « d'avance » assumée (principe v0 n°4 de la synthèse).
