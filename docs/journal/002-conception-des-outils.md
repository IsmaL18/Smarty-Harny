# Journal 002 — Conception des outils

Branche `feat/it2-conception-outils`, commit `0310965`, fusionné dans `main` (`6b1c2e9`). Fiches de notion associées : [`conception-outils`](../notions/conception-outils.md), [`edition-de-fichiers`](../notions/edition-de-fichiers.md), [`troncature-des-sorties`](../notions/troncature-des-sorties.md) (génériques, sans référence au projet). Spec : `specs/002-conception-des-outils.md`. ADR : `docs/adr/0009` à `0011`. Tests : `TESTS.md` (jusqu'à T-0083).

## Ce qui a été construit

- `edit_file` : remplacements exacts puis tolérants, plusieurs par appel, tout ou rien, sur un fichier lu au préalable (`FileTracker`, empreinte SHA-256 du contenu).
- Sorties longues coupées au milieu (40 % début / 60 % fin pour une commande, 50 / 50 pour un fichier), en-tête en numéros de ligne, débordement sur disque dans `.harness/outputs/<session>/` (plafond 50 Mo, purge à 24 h, exclu de Git).
- Ensembles d'outils (`full`, `read_only`) choisis par `[tools] toolset`, et coercition stricte des arguments pilotée par le schéma.

## Décisions et leurs raisons

- **Empreinte du contenu, pas `mtime`** (ADR-0010 §4) : un `touch` ne doit pas refuser l'édition ; le `stat` ne sert qu'à savoir si le shell a touché un fichier.
- **Ré-enregistrement autour du shell** (ADR-0010 §5) : seuls les fichiers « propres » avant la commande sont absorbés ; un changement extérieur antérieur reste signalé.
- **Une normalisation unique avec table de positions** (ADR-0010 §8) plutôt qu'une cascade de stratégies : une seule règle de comptage des occurrences.
- **Écriture sur disque seulement au dépassement du budget** (ADR-0011 §6) : pas de fichier pour une commande courte.
- **`read_only` n'est pas une sécurité** (ADR-0009) : restriction de ce que le modèle voit ; le shell est absent, donc plus de recherche ni de vérification.

## Pièges rencontrés

| Piège | Découvert par | Correctif / test |
|---|---|---|
| Appariement tolérant d'un `old_text` multi-ligne en milieu de ligne : le remplacement recolle les lignes voisines et corrompt le fichier (`"ab = 2\n  c = 3\n"` + `"b = 2\nc = 3"` donnait `"aX\n"`) | revue fusionnée (Major) | alignement exigé sur des lignes entières (ADR-0010 §8, amendé) ; T-0081 à T-0083 |
| Annulation ou exception pendant `run` : fichier de sortie non fermé, bloc `except` limité à `CancelledError` | revue (Minor) | `except BaseException` + `capture.close()` ; pas de test |
| Plafond disque en octets : coupe au milieu d'un caractère UTF-8, fichier illisible | revue (Minor) | coupe sur frontière de caractère ; pas de test |
| `purge_stale` : course avec une session concurrente qui nettoie (`OSError`) | revue (Minor) | `OSError` ignorée ; pas de test |

## Minor acceptés sans correction

- Message « absent » après suppression par le shell : `edit_file` lit les octets avant de consulter le suivi, l'erreur système « No such file » sort donc avant ; l'`except` de `absorb` ne change que l'état interne.
- Fins de ligne en fichier mixte : le fichier suit sa convention dominante ; limite connue.
- Validation de `max_saved_output_mb` : `config.py` impose déjà un entier strictement positif.

## Process : ce que l'itération a montré

- La revue fusionnée a trouvé un défaut qui corrompait le fichier, sans qu'aucun test existant ne le voie : un test par critère d'acceptation ne couvre pas les interactions entre règles (tolérance × multi-ligne).
- La séparation a tenu : le Major a été corrigé en production, et le test de régression est revenu au test-writer.
- Le test-writer a relevé que la règle « lignes entières » n'était écrite nulle part dans l'ADR : un comportement affirmé doit avoir sa trace dans la décision.
- Les corrections de robustesse (annulation, UTF-8, purge) sont livrées sans test : à décider si elles méritent un test de comportement.

## Grill de fin d'itération (2026-11-15)

Huit questions à choix : 5 justes sur 8. Acquis : empreinte du contenu plutôt que `mtime` (pas de faux refus), coupe au milieu parce que le résumé et la dernière erreur d'une commande sont à la fin, positions stables pour les éditions multiples (recherche dans le fichier d'avant l'appel, application de la fin vers le début), coercition stricte (`"yes"` refusé avec une erreur qui nomme l'argument).

Lacunes, déjà reprises dans les fiches :
- **Alignement sur des lignes entières** : le défaut évité est le recollage des lignes voisines et la corruption du fichier, pas une ambiguïté de comptage (`edition-de-fichiers`).
- **`read_only` n'est pas une sécurité** : réponse donnée « oui, hors shell » ; c'est une restriction de vue, pas une garantie, et elle prive l'agent de recherche et de vérification (`conception-outils`).
- **Plafond disque** : il borne le disque (une commande bavarde le remplit en minutes), il ne limite pas les tokens (`troncature-des-sorties`).
- **Coupe d'un flux en octets** : le risque est de trancher un caractère UTF-8 multi-octets et de rendre le fichier illisible (`troncature-des-sorties`).

Le grill n'a pas couvert la réindentation, le nettoyage des restes après arrêt brutal, ni l'absorption des changements du shell.

## Non vérifié

- Les trois corrections de robustesse (voir ci-dessus) n'ont aucun test.
- ADR-0011 : un `docker stop` (SIGTERM sans gestionnaire) ne passe pas par le `finally` ; seule la purge à 24 h nettoie. À essayer à la validation humaine.
- Répartition 40 / 60 et budgets : réglages de départ, jamais ajustés à l'usage sur un vrai modèle.
- `edit_file` n'a pas été exercé par un modèle réel (Anthropic ni local) ; les tests passent par `Session.run_turn` avec un modèle simulé.
- Un `old_text` multi-ligne dont la dernière ligne est tronquée en milieu de ligne est maintenant refusé : un modèle qui copie mal une fin de ligne doit relire, ce qui peut coûter un aller-retour.

## Suite

Itération 3 (feuille de route) : sessions et mode headless. Piste héritée : sortie partielle à l'interruption.
