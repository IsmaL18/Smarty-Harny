# Spécification 002 — Concevoir de bons outils

Statut : brouillon validé en entretien avec l'utilisateur, à relire avant l'ADR.
Branche : `feat/it2-conception-outils`.
Relation avec la 001 : cette spec **remplace CA-8** et la ligne « Fichier ou sortie de commande plus long que la taille maximale » du §4.2 et du §6 de la 001. Tous les autres critères de la 001 restent en vigueur.

## 1. Contexte et problème

La v0 donne à l'agent trois actions : lire un fichier, écrire un fichier entier, lancer une commande shell. Elles suffisent pour travailler, mais mal :

- pour changer une ligne dans un gros fichier, l'agent doit le réécrire en entier : lent, coûteux, et risque d'altérer ce qu'il ne voulait pas toucher ;
- une sortie trop longue est coupée à la fin, alors que l'information utile (le résumé d'une erreur de commande) est souvent à la fin ;
- les erreurs de forme des modèles (un nombre écrit en texte, une liste oubliée) font échouer des appels par ailleurs justes ;
- le modèle n'a aucun moyen d'être restreint à la lecture seule.

L'itération 2 concerne la **qualité de l'interface entre le modèle et la machine** : ce que les outils acceptent, refusent, répondent, et comment ils guident le modèle quand il se trompe.

## 2. Résultat attendu

> En tant que consultant IA, je demande à l'agent de modifier un point précis d'un fichier : il désigne le texte exact à remplacer, sans réécrire le fichier. S'il se trompe (texte introuvable, ambigu, fichier jamais lu ou changé entre-temps), le fichier reste intact et le message lui dit comment se corriger. Les sorties longues gardent leur début et leur fin, l'agent peut consulter le reste, et je peux restreindre l'agent à la lecture seule par la configuration.

## 3. Périmètre

### Dans le périmètre

- Un outil de modification partielle d'un fichier existant, par remplacement de texte exact, avec plusieurs remplacements possibles en une action.
- Refus sans effet, avec message qui guide, des modifications ambiguës ou impossibles.
- Règle « lu avant de modifier » et détection d'un fichier changé depuis sa lecture.
- Tolérance aux petites différences quand le texte exact est introuvable.
- Lecture d'une partie d'un fichier (à partir d'une ligne, sur un nombre de lignes).
- Troncature au milieu des sorties longues (fichier ou commande), avec en-tête, et sortie complète consultable.
- Corrections indulgentes de certaines erreurs de forme des arguments.
- Descriptions d'outils retravaillées.
- Ensembles d'outils activables, choisis dans la configuration.

### Hors périmètre (confirmé)

- Permissions et approbation des modifications (It. 4).
- Retour arrière sur les fichiers (réserve d'idées).
- Reprise de session (It. 3).
- Outil dédié de recherche dans le code : le modèle passe par le shell.
- Changement d'ensemble d'outils en cours de session ou par option de lancement : la configuration seule le choisit.
- Création d'un fichier par l'outil de modification : la création reste le rôle de l'écriture.
- Affichage riche des diffs (It. 12) : seul un diff simple en mode détaillé est demandé ici.

## 4. Comportement attendu

### 4.1 Modifier une partie d'un fichier

- L'agent désigne un fichier existant et une ou plusieurs paires « texte à remplacer / nouveau texte ». Le texte à remplacer doit apparaître **exactement une fois** dans le fichier.
- Quand plusieurs remplacements sont donnés dans une action, **tout ou rien** : s'il y en a un qui échoue, aucun n'est appliqué et le fichier reste intact. Le message nomme celui qui a échoué (son rang) et la raison. Chaque texte à remplacer est cherché dans le fichier tel qu'il était avant l'action ; deux remplacements ne peuvent pas porter sur des zones qui se chevauchent.
- Le résultat renvoyé au modèle confirme la modification et le nombre de remplacements appliqués.

| Cas | Comportement |
|---|---|
| Texte à remplacer introuvable | Refus, fichier intact. Le message dit que le texte n'a pas été trouvé et invite à relire le fichier et à recopier le texte exactement. |
| Texte trouvé plusieurs fois | Refus, fichier intact. Le message donne le nombre d'occurrences et invite à agrandir le texte avec des lignes voisines pour le rendre unique. |
| Texte à remplacer vide | Refus, fichier intact, message explicite. |
| Texte à remplacer identique au nouveau texte | Refus, fichier intact : aucune modification demandée. |
| Fichier absent, illisible ou binaire | Même traitement que la lecture (erreur ou refus explicite renvoyé au modèle). Un fichier absent n'est jamais créé par cet outil ; le message oriente vers l'écriture. |
| Plusieurs remplacements dont un échoue | Tout ou rien, voir plus haut. |

### 4.2 « Lu avant de modifier » et fichier changé depuis la lecture

- L'agent ne modifie un fichier que s'il l'a **lu** pendant la session. Toute lecture compte : fichier entier, fichier tronqué, plage de lignes.
- Un fichier **écrit en entier** par l'agent, ou **modifié** par l'agent avec l'outil de modification, compte comme lu (l'agent en connaît le contenu).
- Un fichier **modifié depuis sa lecture** par un changement extérieur à l'agent (éditeur de l'utilisateur, autre processus) est refusé : le message demande de relire le fichier.
- Un fichier modifié par une **commande shell de l'agent** n'est pas refusé pour cette raison (choix assumé : le texte à remplacer doit de toute façon correspondre exactement au contenu réel, donc un contenu périmé dans la tête du modèle se manifeste par un texte introuvable).
- Un fichier jamais lu : refus, fichier intact, le message demande de le lire d'abord.

### 4.3 Tolérance aux petites différences

- L'appariement exact est toujours tenté en premier. Quand il échoue, un appariement tolérant est tenté. Il ignore les différences de :
  - fins de ligne (CRLF/LF) ;
  - espaces ou tabulations en fin de ligne ;
  - guillemets, apostrophes et tirets typographiques par rapport à leurs formes ASCII ;
  - indentation (espaces contre tabulations, ou niveau d'indentation).
- La modification est appliquée silencieusement : le résultat renvoyé au modèle est le même qu'après un appariement exact (pas de note sur la tolérance).
- Les fins de ligne propres du fichier sont conservées : une modification ne convertit pas les fins de ligne du reste du fichier.
- Si l'appariement tolérant donne plusieurs correspondances, la modification est refusée comme une ambiguïté (voir §4.1). Si l'exact donne une seule correspondance, il l'emporte toujours.
- Si même l'appariement tolérant échoue : refus « introuvable » (voir §4.1).

### 4.4 Lire une partie d'un fichier

- L'outil de lecture accepte, en plus du chemin, une ligne de départ et un nombre de lignes. Sans eux, il lit le fichier depuis le début, dans la limite de la taille maximale.
- Le résultat indique la plage renvoyée et le nombre total de lignes du fichier, pour que le modèle sache s'il reste du contenu.
- Plage hors du fichier : message clair renvoyé au modèle, qui donne le nombre total de lignes.

### 4.5 Sorties longues : coupe au milieu, en-tête, sortie complète

- Quand une sortie (contenu d'un fichier ou sortie de commande) dépasse la taille maximale de la configuration, le modèle reçoit le **début et la fin**, et le milieu est omis. Le début et la fin sont assez longs pour porter un message d'erreur final ou un résumé.
- Un **en-tête** placé dans la sortie dit ce qui est omis (quantité omise) et comment consulter la sortie complète.
- **Sortie de commande** : la sortie complète est enregistrée dans un fichier du dossier de travail, dans un dossier réservé au harness. Le chemin figure dans l'en-tête. L'agent la consulte avec l'outil de lecture, y compris par plage de lignes.
- **Contenu d'un fichier** : le fichier lui-même est la version complète ; l'en-tête invite à lire la zone omise par plage de lignes. Aucune copie n'est faite.
- Le modèle ne rencontre jamais la sortie complète par défaut : seule l'action explicite de lire le fichier de sortie l'y expose, et cette lecture est elle aussi soumise à la coupe au milieu.
- Pour l'utilisateur : les sorties enregistrées sont de simples fichiers de son dossier de travail pendant la session, et le chemin est visible dans l'en-tête (affiché en mode détaillé).
- **Fin de session** : à la sortie (`/quit`, Ctrl+D), les sorties enregistrées sont supprimées.
- Les comportements de la 001 sur le code de sortie, l'erreur et le dépassement de délai restent valables ; la coupe au milieu s'applique à la sortie renvoyée dans ces cas aussi.

### 4.6 Erreurs de forme des arguments

- Sont corrigées sans échec, pour tous les outils :
  - un nombre ou un booléen donné sous forme de texte (« 10 » pour 10, « true » pour vrai) ;
  - une liste donnée sous forme d'un seul élément (un remplacement seul, sans liste) ou sous forme de texte JSON.
- Restent des erreurs, renvoyées au modèle comme en 001 : argument manquant, argument inconnu, type non convertible (« beaucoup » pour un nombre), texte JSON invalide. Le message nomme l'argument fautif et la forme attendue.
- Aucune correction ne change le sens de l'appel : en cas de doute, l'appel échoue.

### 4.7 Descriptions d'outils

- La description de chaque outil dit ce qu'il fait, quand l'utiliser plutôt qu'un autre (par exemple : modifier plutôt qu'écrire pour un changement partiel), et ses contraintes visibles (lire avant de modifier, texte unique, sortie coupée au milieu). Ces descriptions sont une partie du produit : leur qualité se juge à l'usage par un vrai modèle (voir §8).

### 4.8 Ensembles d'outils

- Un **ensemble d'outils** est un groupe nommé d'outils. Le fichier de configuration choisit l'ensemble actif ; sans choix, l'ensemble par défaut est « complet ».
- Deux ensembles en v1 :
  - **complet** : lecture, écriture, modification, commande shell ;
  - **lecture seule** : lecture uniquement (la commande shell en est exclue, car elle peut tout écrire).
- Le modèle ne voit que les outils de l'ensemble actif.
- Si le modèle appelle un outil hors de l'ensemble actif, l'appel échoue avec une erreur renvoyée au modèle qui nomme l'outil et liste les outils disponibles ; la session continue.
- Ensemble inconnu dans la configuration : message clair en français au lancement, qui nomme l'ensemble et liste les ensembles existants ; aucune session ne s'ouvre.
- Le lancement affiche aussi l'ensemble actif.

### 4.9 Affichage

- Une modification de fichier s'affiche, par défaut, en une ligne-titre qui nomme le fichier et le nombre de remplacements.
- En mode détaillé, elle affiche en plus un diff simple des lignes modifiées (comme les autres événements, voir 001 §4.3).

## 5. Critères d'acceptation

Même principe que la 001 : comportements visibles par l'utilisateur ou par le modèle, modèle simulé, outils réels. La numérotation continue celle de la 001.

### Modification partielle

- **CA-26** Un remplacement unique : le fichier contient ensuite le nouveau texte à la place de l'ancien, le reste du fichier est identique octet pour octet, le modèle reçoit une confirmation.
- **CA-27** Plusieurs remplacements en une seule action sur des zones distinctes : tous sont appliqués, le résultat indique leur nombre.
- **CA-28** Texte introuvable (ni exact ni tolérant) : le fichier reste intact ; le message au modèle dit que le texte n'a pas été trouvé et comment se corriger ; la session continue.
- **CA-29** Texte trouvé plusieurs fois : le fichier reste intact ; le message donne le nombre d'occurrences et dit d'agrandir le texte pour le rendre unique.
- **CA-30** Plusieurs remplacements dont l'un échoue (introuvable, ambigu, ou en chevauchement avec un autre) : aucun n'est appliqué, le fichier reste intact, le message nomme le remplacement fautif.
- **CA-31** Texte à remplacer vide, texte identique au nouveau, fichier absent, fichier binaire : refus avec message explicite, fichier intact (rien n'est créé pour un fichier absent).

### Lu avant de modifier

- **CA-32** Un fichier jamais lu pendant la session ne peut pas être modifié : refus, fichier intact, message qui demande de le lire d'abord.
- **CA-33** Une lecture tronquée ou par plage suffit : le fichier peut ensuite être modifié.
- **CA-34** Un fichier écrit en entier par l'agent, ou déjà modifié par lui avec l'outil de modification, peut être modifié sans relecture.
- **CA-35** Un fichier lu puis changé par un acteur extérieur à l'agent est refusé à la modification : fichier intact, message qui demande de relire. Après relecture, la modification passe.
- **CA-36** Un fichier lu puis changé par une commande shell de l'agent n'est pas refusé pour ce motif : la modification est appliquée si le texte correspond au contenu réel du fichier.

### Tolérance

- **CA-37** Quand le texte exact est introuvable mais qu'il ne diffère que par les fins de ligne, les espaces de fin de ligne, les guillemets/tirets typographiques ou l'indentation, la modification est appliquée, sans mention de tolérance dans le résultat.
- **CA-38** La tolérance conserve les fins de ligne du fichier : un fichier CRLF modifié reste entièrement CRLF.
- **CA-39** Une correspondance exacte unique l'emporte sur une tolérante. Si l'appariement tolérant trouve plusieurs correspondances, la modification est refusée comme ambiguë, fichier intact.

### Lecture partielle et troncature

- **CA-40** La lecture avec ligne de départ et nombre de lignes renvoie exactement cette plage et indique le nombre total de lignes du fichier. Une plage hors du fichier renvoie une erreur claire.
- **CA-41** Un fichier plus long que la taille maximale est renvoyé coupé au milieu : le début et la fin du fichier sont présents, un en-tête dit ce qui est omis et invite à lire par plage ; une lecture par plage de la zone omise renvoie bien son contenu.
- **CA-42** Une commande dont la sortie dépasse la taille maximale et qui échoue avec un message final (code de sortie non nul) : le modèle reçoit le début, la fin (donc le message final) et l'en-tête, ainsi que le code de sortie.
- **CA-43** Pour cette commande, l'en-tête indique un chemin dans le dossier de travail ; l'agent lit ce fichier (y compris par plage) et y retrouve la sortie complète, y compris la partie omise.
- **CA-44** À la sortie de la session (`/quit` ou Ctrl+D), les fichiers de sortie enregistrés ont disparu du dossier de travail.
- **CA-45** Une commande interrompue au délai maximal, ou en erreur, avec une sortie plus longue que la taille maximale conserve les comportements de CA-10 et CA-11 de la 001 (code de sortie, information du dépassement) avec une sortie coupée au milieu.

### Arguments

- **CA-46** Un nombre ou un booléen donné en texte, un remplacement seul sans liste, une liste donnée en texte JSON valide : l'action réussit comme si la forme était correcte.
- **CA-47** Un argument manquant, un argument inconnu, un nombre non convertible, un texte JSON invalide : l'action échoue avec un message qui nomme l'argument et la forme attendue ; la session continue.

### Ensembles d'outils

- **CA-48** Avec l'ensemble par défaut, le modèle dispose des quatre outils (lecture, écriture, modification, commande).
- **CA-49** Avec l'ensemble « lecture seule » dans la configuration, le modèle ne voit que la lecture ; s'il appelle un autre outil, il reçoit une erreur qui nomme l'outil et liste les outils disponibles, aucun fichier n'est écrit ni aucune commande lancée, la session continue.
- **CA-50** Une configuration qui nomme un ensemble inconnu : message en français qui nomme l'ensemble et liste les ensembles existants ; aucune session ne s'ouvre.
- **CA-51** Au lancement, l'ensemble d'outils actif est affiché avec le dossier, le modèle et les limites.

### Affichage

- **CA-52** Une modification réussie affiche par défaut une ligne-titre avec le nom du fichier et le nombre de remplacements. En mode détaillé, elle affiche en plus les lignes modifiées sous forme de diff.

### Qualité des descriptions (validation humaine)

- **CA-53** Avec un vrai modèle, sur une série de tâches de modification (changer une ligne, plusieurs endroits, un fichier long), l'agent choisit la modification partielle plutôt que la réécriture complète, lit avant de modifier, et les échecs d'appel liés à une mauvaise utilisation des outils sont rares. Le résultat est noté à la relecture, pas assuré par un test automatique.

## 6. Cas limites à couvrir

- Le texte à remplacer contient des fins de ligne : il est apparié sur plusieurs lignes.
- Fichier vide, ou sans fin de ligne finale : la modification conserve cette caractéristique.
- Fichier très gros dont la lecture est coupée au milieu, puis modifié dans la zone omise après lecture par plage : autorisé (une lecture quelconque suffit).
- Deux remplacements qui visent le même texte ou des zones qui se chevauchent : refus de l'action entière (CA-30).
- Fichier supprimé par une commande après sa lecture, puis modification demandée : erreur « fichier absent ».
- Les fichiers de sortie enregistrés vivent dans le dossier de travail : l'agent peut les lire, mais ils ne sont jamais traités comme des fichiers du projet de l'utilisateur à modifier (hypothèse : à confirmer à l'ADR).
- Sortie complète volumineuse : voir questions ouvertes.
- La commande shell reste accessible dans l'ensemble complet : l'ensemble « lecture seule » n'est pas une sécurité (voir It. 4), c'est une restriction de ce que le modèle voit et peut appeler.

## 7. Règles métier

- Un texte à remplacer doit être unique dans le fichier ; en cas de doute, la modification est refusée plutôt que devinée.
- Une modification refusée ne laisse aucune trace sur le fichier.
- Un message d'erreur d'outil dit toujours **quoi** a échoué et **comment se corriger**.
- Les tailles de coupe (taille maximale, répartition début/fin) sont dans la configuration ; leur valeur n'est pas figée par cette spec.
- La suppression des sorties enregistrées est liée à la fin de session, pas à un délai.

## 8. Preuve de done

Le contrat fixe : tests ciblés, lint, typecheck, build, et validation humaine. Tests : comportements uniquement.

- Tests automatisés : CA-26 à CA-52 avec un modèle simulé et les vrais outils, au niveau le plus haut possible (peu de tests, un par comportement observable).
- Validation humaine : CA-53, et une session réelle de bout en bout avec un modèle réel (modification, tolérance, sortie longue de commande, ensemble lecture seule).

## 9. Questions ouvertes (non bloquantes pour l'architecte)

1. **Pas de « remplacer partout »** : la spec ne prévoit pas de paramètre pour renommer toutes les occurrences d'un texte ; le modèle doit lister chaque occurrence en remplacement distinct, avec assez de contexte. À confirmer à l'usage.
2. **Tolérance silencieuse et indentation** : l'indentation tolérée sans avertissement peut produire un fichier mal indenté (ex. Python) si le nouveau texte garde l'indentation du modèle. Choix assumé par l'utilisateur ; l'architecte décide si le nouveau texte est réindenté. Les deux autres hypothèses (priorité de l'exact, refus si l'appariement tolérant est ambigu) viennent de ce cadrage et sont à valider à la relecture.
3. **Sorties laissées par un arrêt brutal** (crash, conteneur tué) : elles restent dans le dossier de travail. Hypothèse : nettoyage au lancement suivant. À confirmer, ainsi que l'emplacement exact du dossier et son éventuelle exclusion de Git.
4. **Taille et répartition de la coupe** (début/fin) : valeurs par défaut à fixer à l'implémentation.
5. **Ensemble « lecture seule » sans shell** : l'agent ne peut alors ni chercher dans le code (pas de grep) ni lancer des vérifications. Acceptable en v1 ? À réévaluer quand l'outil de recherche sera décidé.
