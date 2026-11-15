---
title: "Édition de fichiers par un agent LLM"
tags:
  - veille
  - tech-note
  - ai
  - software_engineering
type: tech-note
subject-type: technique
date: 2026-11-15
---

## Principe & cas d'usage

Le modèle doit modifier un fichier sans le réécrire en entier. Trois familles d'outils existent. Le remplacement de texte exact : le modèle donne un extrait à retrouver et son remplaçant. Le patch ou diff : le modèle émet un format structuré (blocs ancrés par contexte, diff unifié) que le harness parse et applique. La réécriture complète : le modèle renvoie tout le fichier.

La réécriture coûte des tokens en sortie, dérive sur les fichiers longs et risque de recopier faussement des zones intactes. Elle reste valable pour créer un fichier ou pour un fichier court. Le patch est compact, mais le format est une surface d'erreur et il se couple au modèle entraîné dessus. Le remplacement exact est le plus simple à valider : l'extrait existe ou n'existe pas.

L'idée centrale : transformer une édition mal localisée en erreur explicite plutôt qu'en corruption silencieuse. Tout le reste (unicité, lecture préalable, appariement tolérant) sert cet objectif.

## Implémentation

### Contrat de l'outil de remplacement

Le modèle fournit un chemin, un `old_text` et un `new_text`. Exact d'abord : pas de regex, pas de flou par défaut.

Unicité obligatoire. Plusieurs occurrences : refus, avec leur nombre, et consigne de fournir plus de contexte (ou d'utiliser un drapeau de remplacement global explicite). Aucune occurrence : refus qui demande de relire le fichier, car le modèle travaille probablement sur une version périmée ou mal recopiée. Le message d'erreur est le seul canal de correction : il doit dire quoi faire.

Un refus ne laisse aucune trace : fichier intact, aucun état modifié.

### Plusieurs éditions par appel

Un appel peut porter une liste de paires `{old_text, new_text}`. Quatre règles.

Chaque `old_text` est cherché dans le fichier tel qu'il était avant l'appel, jamais dans le résultat des éditions précédentes. Sinon une édition peut s'apparier sur du texte que l'appel vient de produire.

Tout ou rien. Une seule édition invalide et le fichier n'est pas touché.

Les chevauchements sont refusés. Le modèle doit fusionner les changements proches en une seule édition.

L'application se fait de la fin vers le début du fichier. Les décalages d'offsets causés par les premières éditions n'affectent alors pas les bornes des suivantes.

### Lecture préalable et fichier périmé

Le harness refuse d'éditer un fichier que le modèle n'a pas lu dans la session. Cela force le modèle à travailler sur le contenu réel. Toute lecture compte, y compris une lecture tronquée : le modèle a vu une partie du fichier et l'unicité protège le reste. Certains harness comptent aussi une lecture faite par le shell sur un seul fichier (`cat`, `head`, `grep`).

Détecter un fichier modifié depuis la lecture par une empreinte du contenu (SHA-256), pas par la date de modification. Un `touch` ou un outil de formatage qui réécrit le même contenu ne doit pas provoquer de refus. À l'inverse, un vrai changement de contenu doit en provoquer un.

Une politique plus souple existe : accepter l'édition si l'`old_text` correspond encore de façon exacte et unique, avec une note invitant à relire. Elle est défendable parce que l'unicité garantit déjà la localisation.

### Le shell modifie des fichiers suivis

L'agent a un shell. Une commande (`sed -i`, formateur, génération de code) peut changer un fichier déjà lu. Si l'empreinte reste celle de la lecture, la prochaine édition sera refusée à tort. Après la commande, ré-enregistrer l'empreinte, mais seulement pour les fichiers qui étaient propres (inchangés par rapport à leur dernière lecture) avant la commande. Ré-enregistrer un fichier déjà périmé masquerait un changement extérieur antérieur que le modèle n'a jamais vu.

### Appariement tolérant en une passe

Les modèles recopient mal : guillemets typographiques, tirets longs, espaces de fin, indentation, fins de ligne. L'exact d'abord. Si l'exact échoue, une seule passe tolérante.

Normaliser à la fois le fichier et l'`old_text` : CRLF vers LF, espaces de fin de ligne retirés, guillemets et tirets typographiques ramenés à l'ASCII, indentation ignorée. La normalisation construit une table de positions (indice normalisé vers indice original). La correspondance est trouvée dans le texte normalisé, puis ses bornes sont reportées sur l'original. L'édition s'applique sur le fichier d'origine, pas sur sa version normalisée.

L'unicité s'applique aussi à l'appariement tolérant.

### Alignement sur des lignes entières

> [!warning] Un `old_text` multi-ligne doit s'aligner sur des lignes entières
> Avec l'indentation ignorée, une correspondance qui commence en milieu de ligne recolle les lignes voisines et corrompt le fichier. Exemple : le fichier contient `ab = 2\n  c = 3` et le modèle envoie `b = 2\nc = 3`. Normalisé, l'extrait s'apparie à partir du `b` de la première ligne. Le remplacement coupe `a` de sa suite, et l'indentation de la seconde ligne est absorbée. Exiger que la correspondance multi-ligne commence au début d'une ligne et finisse à la fin d'une ligne.

Un `old_text` d'une seule ligne peut s'apparier en milieu de ligne. C'est l'usage normal : renommer un identifiant au milieu d'une expression.

### Reporter le new_text à la convention du fichier

Fins de ligne. Si le fichier utilise CRLF, convertir le `new_text` en CRLF avant l'insertion. Sinon le fichier devient mixte. Limite : un fichier déjà mixte suit la convention dominante, ce qui peut normaliser localement une zone.

Indentation. Quand l'appariement a eu lieu en ignorant l'indentation, le `new_text` du modèle porte l'indentation que le modèle croit exacte, pas celle du fichier. Construire une table indentation du modèle vers indentation réelle, déduite des lignes appariées (ligne à ligne entre `old_text` et zone appariée), puis réindenter le `new_text` avec cette table. Ne le faire qu'après un appariement tolérant : en appariement exact, l'indentation est déjà identique et le `new_text` est repris tel quel.

Limite : un nouveau niveau d'indentation absent des lignes appariées (une boucle imbriquée ajoutée) n'a pas de correspondance dans la table. Dans un fichier mixte tabs/espaces, le choix du caractère d'indentation du nouveau niveau est ambigu.

### Préserver les octets hors zones modifiées

Lire et écrire en octets. Ne traduire aucune fin de ligne, ne pas réencoder, ne pas retirer un BOM. Seule la zone remplacée change. Un diff qui touche des lignes non modifiées pollue la revue et casse les outils qui comparent le fichier.

Refuser les fichiers binaires (octet nul, UTF-8 invalide) : le remplacement de texte n'y a pas de sens.

## Pièges & limitations

Les pièges de l'appariement tolérant sont ci-dessus (milieu de ligne, indentation, fichier mixte). S'ajoutent les suivants.

Appariement flou par similarité (`difflib` ou distance d'édition). Il peut viser le mauvais endroit : deux blocs voisins ressemblent à l'`old_text`, le plus proche gagne sans que personne ne le sache. Une erreur d'édition vaut mieux qu'une édition au mauvais endroit. Écarté au profit d'une normalisation déterministe.

Cascade de stratégies (exact, puis rstrip, puis strip, puis flou, avec retombées successives). Chaque palier a sa propre règle d'ambiguïté. Elles se superposent et le comportement devient difficile à prédire et à tester. Une seule passe tolérante, avec une seule règle d'unicité, reste lisible.

Un patch invalide corrompt plus largement qu'un remplacement refusé. Les formats de patch exigent un parseur indulgent pour les modèles qui n'y ont pas été entraînés. Le format est souvent adapté à une famille de modèles.

Les arguments d'une réponse tronquée par la limite de tokens ne doivent jamais être appliqués : une écriture tronquée est pire qu'une erreur.

Les outils de fichiers intégrés peuvent tourner hors du sandbox du shell : leur périmètre d'écriture se contrôle par les permissions, pas par l'isolement du processus.

## Variantes & tooling

Remplacement exact avec unicité : Claude Code (`Edit` : `old_string`, `new_string`, remplacement global optionnel, lecture préalable obligatoire, refus des fichiers non UTF-8 sauf UTF-16 LE avec BOM). Un fichier modifié depuis la lecture reste éditable si l'extrait correspond exactement et de façon unique.

Liste de remplacements disjoints : Pi (`edit` avec `edits[]` de `{oldText, newText}`). Chaque `oldText` est apparié contre l'original, sans chevauchement. Exact d'abord, puis repli flou avec normalisation Unicode, retrait des espaces de fin, guillemets et tirets ramenés à l'ASCII, gestion de CRLF et du BOM. L'outil accepte aussi des arguments mal formés par certains modèles (liste sous forme de chaîne JSON, objet unique). Le résultat est scindé : un texte court pour le modèle, un diff pour l'interface.

Patch à blocs ancrés par contexte : Codex (`apply_patch`, grammaire Lark, format propre à OpenAI). Pas de numéros de ligne, blocs ancrés par contexte, recherche de séquence dégradée, parseur volontairement indulgent, parsing possible pendant le streaming pour afficher un diff en direct. Conçu avec les modèles de la famille.

Patch à correspondance floue : Hermes (outil `patch` avec module de correspondance floue et parseur dédié). Le format exact n'a pas été vérifié ligne à ligne. Il ajoute des garde-fous d'écriture, un suivi de lecture et un lint après édition. Des instantanés git invisibles du modèle précèdent les écritures pour permettre un retour arrière.

Choix pratique : pour un harness multi-modèles, le remplacement exact avec liste et appariement tolérant est le plus portable. Le patch convient quand le modèle a été entraîné sur ce format précis.

## Retours terrain

Les erreurs guidantes rapportent plus que la tolérance. Un modèle qui reçoit « 3 occurrences, ajoute du contexte » ou « introuvable, relis le fichier » corrige au coup suivant. Les harness matures ont convergé vers : exact, unicité, lecture préalable.

Le multi-édition par appel réduit le nombre d'appels et évite la dérive incrémentale (une édition qui s'appuie sur le résultat de la précédente). Le prix est la règle de non-chevauchement, que les modèles respectent bien quand le prompt de l'outil la formule.

La tolérance sert surtout à absorber les défauts de recopie (guillemets, espaces de fin, CRLF), pas la paresse du modèle. Plus la tolérance est large, plus il faut de règles de sécurité (alignement sur lignes entières, unicité, un seul passage).

Les gardes périphériques coûtent peu et évitent de lourds incidents : refus des binaires, empreinte plutôt que date, octets préservés, instantané avant écriture.

#### Ressources utiles :
- [Claude Code — référence des outils](https://code.claude.com/docs/en/tools-reference)
- [Pi coding agent — article de conception](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)
- [Pi monorepo (outil edit)](https://github.com/badlogic/pi-mono)
- [Codex (apply-patch)](https://github.com/openai/codex)
