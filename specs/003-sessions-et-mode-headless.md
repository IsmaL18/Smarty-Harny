# Spécification 003 — Sessions et mode headless

Statut : brouillon validé en entretien avec l'utilisateur, à relire avant l'ADR.
Itération : 3 de `docs/ROADMAP.md`.
Relation avec les specs précédentes :

- remplace la mention « Reprise d'une session fermée : une session fermée est perdue » du hors-périmètre de la 001 ;
- adapte **CA-3** et **CA-14** de la 001 : le coût affiché est le coût cumulé de la **session** (reprises comprises), pas celui du seul lancement ;
- **remplace** la règle de la 002 « à la sortie, les sorties enregistrées sont supprimées » (§ fin de session, CA-44) : ces sorties vivent désormais autant que leur session (voir 4.7) ;
- tous les autres critères des 001 et 002 restent en vigueur.

## 1. Contexte et problème

Aujourd'hui, fermer le terminal perd toute la conversation : l'agent oublie la tâche, ce qu'il a lu, ce que ça a coûté. Une tâche longue ne peut pas être reprise le lendemain, une erreur de départ ne peut pas être rattrapée sans tout recommencer, et rien ne reste pour comprendre après coup ce que l'agent a fait.

Par ailleurs, l'agent n'est utilisable qu'à la main, dans un terminal interactif. Il ne peut pas être appelé depuis un script, un enchaînement de commandes ou un outil tiers.

L'itération 3 donne à l'agent **une mémoire de conversation durable** (les sessions) et **une porte d'entrée scriptable** (le mode non interactif, dit « headless »).

## 2. Résultat attendu

> En tant que consultant IA, chaque conversation que j'ouvre est enregistrée au fil de l'eau. Je peux fermer le terminal, revenir plus tard, retrouver la conversation, voir ce qui s'est passé et continuer comme si je ne l'avais pas quittée, avec le même coût cumulé et le même modèle. Je peux aussi repartir d'une demande antérieure pour essayer une autre voie sans rien perdre. Et je peux lancer l'agent depuis un script avec un prompt, récupérer sa réponse (ou le flux détaillé de ce qu'il a fait) et savoir par le code de sortie si ça s'est bien passé.

## 3. Périmètre

### Dans le périmètre

- Enregistrement automatique de chaque session, au fil de l'eau, en ajout seul.
- Contenu enregistré : en-tête, messages, appels et résultats d'actions, usage et coût, changements d'état.
- Liens entre entrées permettant des branches.
- Lister les sessions du dossier de travail ; reprendre une session par identifiant ; reprendre depuis une commande du REPL ; supprimer une session ; purge automatique des anciennes sessions.
- Restauration à la reprise : historique, coût cumulé, modèle actif, fichiers déjà lus, mode d'affichage ; rejeu complet de la conversation.
- Branches : repartir d'une demande antérieure de la même session.
- Détection de session corrompue, d'appel sans résultat, de session occupée.
- Mode non interactif : prompt en argument, sortie texte ou JSONL, codes de sortie, reprise d'une session, option « ne rien enregistrer ».

### Hors périmètre (confirmé)

- Reprise de « la dernière session du dossier » sans id (seules la reprise par id, par liste et par commande du REPL sont retenues).
- Lecture du prompt depuis l'entrée standard.
- Fork vers une nouvelle session (une session = un journal ; les branches vivent dans le même journal).
- Retour arrière des fichiers du dossier de travail (réserve d'idées) : changer de branche ne restaure pas les fichiers.
- Commande pour revenir à une branche abandonnée (elle reste dans le journal, voir questions ouvertes).
- Navigation en arbre complète, résumés de branche, migration de formats de journal.
- Recherche plein texte dans les sessions (It. 10), mémoire entre sessions.
- Compaction (It. 6) : le journal conserve tout, rien n'est jamais réécrit.
- Chiffrement ou masquage des échanges enregistrés (limite documentée en 4.7).
- Fork et branches en mode headless : le headless reprend la branche active uniquement.
- Permissions et approbations (It. 4) ; serveur HTTP (It. 13).

## 4. Comportement attendu

### 4.1 Session et enregistrement

- Chaque lancement du REPL ouvre une **nouvelle session**, avec un identifiant court et unique, affiché au démarrage.
- Une session est rattachée au **dossier de travail** où elle a été ouverte. Elle est enregistrée sur le poste de l'utilisateur, hors du conteneur éphémère : elle survit à l'arrêt et à la suppression du conteneur.
- Une session n'existe qu'à partir de la **première demande** de l'utilisateur : ouvrir le REPL puis quitter aussitôt ne laisse aucune session.
- L'enregistrement est **fait au fil de l'eau** : chaque entrée est écrite dès qu'elle se produit, pas à la sortie. Un arrêt brutal du processus perd au plus l'entrée en cours d'écriture.
- Le journal est **en ajout seul** : rien n'est jamais modifié ni supprimé dans un journal existant, pas même à la reprise, au changement de branche ou quand une anomalie est réparée.
- Ce qui est enregistré :

| Élément | Détail |
|---|---|
| En-tête (première ligne) | version du format, identifiant, dossier de travail, date, modèle de départ |
| Demandes de l'utilisateur | texte complet |
| Réponses du modèle | texte et appels d'actions demandés, avec le modèle utilisé |
| Résultats d'actions | tels que le modèle les a reçus (donc déjà tronqués) ; une erreur d'action y figure comme n'importe quel résultat |
| Usage et coût | tokens et coût de chaque appel au modèle ; « non estimé » quand le prix est inconnu (jamais 0 trompeur) |
| Changements d'état | changement de modèle, bascule du mode d'affichage, interruption Ctrl+C, tranche supplémentaire accordée à « continuer ? », changement de branche |

- **La clé API et tout secret de configuration ne sont jamais écrits** dans le journal.
- Les entrées sont liées entre elles de façon à reconstituer, pour chaque point de la conversation, la suite exacte qui y mène. Cette structure autorise les branches (4.5).

### 4.2 Retrouver une session

- Une commande de lancement **liste** les sessions du dossier de travail courant, de la plus récente à la plus ancienne. Pour chacune : identifiant, date de dernière activité, début de la première demande, nombre de demandes, coût cumulé, modèle. Les sessions des autres dossiers n'apparaissent pas.
- La liste signale les sessions actuellement occupées (4.6).

### 4.3 Reprendre une session

- **Par identifiant** : une option de lancement prend l'identifiant d'une session du dossier de travail ; un préfixe suffit tant qu'il est non ambigu.
- **Depuis le REPL** : une commande de session ferme la session courante et ouvre la session choisie (par identifiant, ou depuis la liste) du même dossier.
- À la reprise, sont restaurés :
  - l'**historique** de la branche active : la conversation continue, le modèle comprend « modifie ce fichier » sur une demande d'avant la fermeture ;
  - le **coût cumulé** : le budget de session s'applique au cumul de tous les lancements ;
  - le **modèle actif** : le dernier modèle utilisé reste actif, sauf si l'option de lancement de modèle en demande un autre (qui devient alors le modèle actif et est enregistré) ;
  - les **fichiers déjà lus** : la règle « lu avant de modifier » et la détection de fichier changé depuis sa lecture (002) continuent de s'appliquer ; un fichier modifié sur le disque depuis sa lecture déclenche la même détection qu'au sein d'une session ;
  - le **mode d'affichage** (titres ou détaillé).
- La limite d'étapes s'applique par tour comme avant ; la reprise ne la réinitialise pas en cours de tour mais un nouveau tour repart d'un compteur neuf.
- **Rejeu** : à l'ouverture dans le REPL, la conversation complète de la branche active est réaffichée dans le mode d'affichage restauré (titres ou détail), puis l'invite apparaît. Un en-tête de reprise rappelle l'identifiant, la date de création, le modèle et le coût cumulé.
- Une session qui a été fermée par `/quit`, Ctrl+D, ou un arrêt brutal est reprenable de la même manière.

### 4.4 Échecs de reprise

Dans tous les cas ci-dessous, le message est en français, nomme la cause et la correction, **aucune session ne s'ouvre** (sauf mention) et **le journal n'est pas modifié**.

| Cas | Comportement |
|---|---|
| Identifiant inconnu | Refus ; propose de lister les sessions du dossier. |
| Préfixe ambigu | Refus ; nomme les sessions candidates. |
| Session d'un autre dossier de travail | Refus ; nomme le dossier auquel elle appartient. |
| Session occupée par un autre processus | Refus ; voir 4.6. |
| Dernière ligne du journal tronquée (arrêt brutal en pleine écriture) | La reprise **réussit** avec ce qui est lisible ; un avertissement nomme la ligne ignorée. Le fichier n'est pas réécrit : l'entrée tronquée n'est pas supprimée du journal. |
| Ligne invalide **au milieu** du journal, ou liens entre entrées cassés (entrée qui désigne une entrée inexistante) | Refus ; le message nomme la ligne et la cause. |
| En-tête absent, illisible ou d'une version de format inconnue | Refus ; le message nomme la cause. |
| Appel d'action sans résultat (arrêt brutal entre l'appel et son résultat) | La reprise **réussit** ; un résultat d'erreur « action interrompue, état inconnu » est ajouté à la fin du journal pour cet appel, de sorte que chaque appel a exactement un résultat. Le modèle en est informé. |
| Modèle de la session injoignable ou clé absente | Mêmes messages qu'au lancement (001 : CA-20, CA-21) ; la session n'est pas ouverte ; l'utilisateur peut reprendre avec l'option de modèle. |
| Fichiers de sortie enregistrés (002) disparus | La reprise réussit ; si le modèle renvoie vers un fichier disparu, il reçoit l'erreur de lecture habituelle. |

### 4.5 Branches

- Une commande de session **liste les demandes de l'utilisateur** de la branche active, numérotées. En choisir une repart de **juste avant cette demande** : l'historique envoyé au modèle s'arrête là, et l'utilisateur saisit une nouvelle demande, qui ouvre une nouvelle branche dans **le même journal**.
- L'ancienne branche reste intacte dans le journal : rien n'est supprimé ni réécrit.
- Le coût cumulé de la session **continue de s'additionner** : le coût dépensé sur une branche abandonnée reste compté.
- Les fichiers du dossier de travail ne sont **pas** remis dans l'état de l'époque. Au changement de branche :
  - un avertissement affiché à l'utilisateur le dit ;
  - la liste des « fichiers déjà lus » repart de zéro (le modèle doit relire avant de modifier) ;
  - un message informe le modèle que le dossier peut différer de ce que la branche a vu.
- La reprise d'une session rouvre toujours la **branche active** au moment de la fermeture (la dernière écrite).

### 4.6 Une session, un seul auteur à la fois

- Une session ouverte (REPL ou run headless) ne peut pas être ouverte en même temps par un second processus : le second lancement échoue avec un message qui nomme la session occupée, sans rien écrire. Cela vaut aussi pour la suppression.
- Une session laissée « occupée » par un processus arrêté brutalement ne bloque pas définitivement : elle redevient reprenable sans intervention manuelle.

### 4.7 Durée de vie, suppression et confidentialité

- Les **sorties longues enregistrées** (002) appartiennent à leur session : elles ne sont plus supprimées à la sortie, et existent tant que la session existe. Elles sont supprimées avec elle.
- Une commande de lancement **supprime une session** (journal et sorties enregistrées) après confirmation. Elle refuse si la session est occupée.
- **Purge automatique** : les sessions sans activité depuis plus de N jours (N dans la configuration) sont supprimées, avec leurs sorties enregistrées, au lancement du harness ; un message indique combien l'ont été. Une session occupée n'est jamais purgée. L'ancienneté se compte depuis la dernière activité, pas la création.
- **Limite connue, documentée** : le journal contient en clair tout ce qui a été échangé, y compris le contenu des fichiers lus et les sorties de commandes. Il n'est ni chiffré ni masqué.

### 4.8 Mode non interactif (headless)

- Une option de lancement donne le **prompt en argument** : une seule demande, puis le processus se termine. Aucune interaction : jamais de question posée à un humain, jamais d'attente de saisie.
- Un run headless crée une **session enregistrée** comme le REPL (4.1) ; l'identifiant est communiqué (voir sorties). Il peut **reprendre une session existante** avec la même option de reprise par identifiant (4.3) et les mêmes échecs (4.4, codes de sortie en 4.8.3). Une option de lancement permet de **ne rien enregistrer** : aucune session n'est créée.
- L'option de modèle, la configuration et les limites fonctionnent comme dans le REPL.

#### 4.8.1 Sortie texte (défaut)

- **stdout** : uniquement la réponse finale du modèle, rien d'autre — composable dans un pipe.
- **stderr** : tout le reste, destiné à un humain : lignes-titres des actions, avertissements, coût, identifiant de session, message d'erreur.

#### 4.8.2 Sortie JSONL

- **stdout** ne contient que du JSONL, **une ligne = un objet JSON valide**, émis **au fil de l'eau** (pas en bloc à la fin). Les diagnostics humains vont sur stderr.
- Chaque objet porte un champ `type`. Séquence :
  - première ligne : début de run (identifiant de session, modèle, dossier de travail, `resumed` vrai/faux) ;
  - ensuite, les événements du run : demande d'action, résultat ou erreur d'action, réponse du modèle, avertissement ;
  - dernière ligne : **résultat final** : statut (voir 4.8.3), raison en cas d'échec ou de limite, réponse finale du modèle s'il y en a une, nombre d'étapes, tokens, coût cumulé de la session, identifiant de session.
- Les mêmes informations (statut, cause) sont dans la ligne finale et dans le code de sortie.
- Le format des lignes est documenté.

#### 4.8.3 Codes de sortie

| Code | Signification | Cas |
|---|---|---|
| 0 | Succès | Le modèle a rendu une réponse finale. Une erreur d'action en cours de route (fichier absent, commande en échec) ne change pas le code, tant que le modèle répond. |
| 1 | Échec d'exécution | Fournisseur injoignable en cours de run, erreur de contexte ou de fournisseur qui empêche d'obtenir une réponse. La session est enregistrée jusque-là et reprenable. |
| 2 | Usage ou démarrage impossible | Option invalide, prompt absent, configuration invalide, clé manquante, serveur injoignable au lancement, session de reprise introuvable, ambiguë, d'un autre dossier, corrompue ou occupée. Rien n'a été exécuté. |
| 3 | Limite atteinte | Nombre maximal d'étapes ou budget atteint. Pas de question « continuer ? » : le run s'arrête, la limite et l'état d'avancement sont indiqués, la session est enregistrée et reprenable. |
| 130 | Interrompu | Signal d'interruption ou d'arrêt (Ctrl+C, SIGTERM) pendant le run : l'action en cours est arrêtée, l'interruption est enregistrée dans la session, qui reste reprenable. |

- En cas de code non nul, stdout du mode texte est vide sauf si le modèle avait déjà produit une réponse finale ; en mode JSONL la ligne finale est écrite chaque fois que le processus a pu démarrer le run (code 1, 3, 130 ; pas pour le code 2, où rien n'a démarré — l'erreur est sur stderr).

## 5. Critères d'acceptation

Même convention que les specs précédentes : ce que voit l'utilisateur ou le modèle, avec un modèle simulé pour piloter la boucle. Numérotation propre à cette spec (préfixe `S`).

### Enregistrement

- **CA-S1** Après une demande qui déclenche une action, le journal de la session existe sur le poste de l'utilisateur, hors du conteneur, et contient l'en-tête, la demande, la réponse du modèle, l'appel d'action, son résultat tel que reçu par le modèle, et l'usage/coût de l'appel.
- **CA-S2** Si le processus est tué brutalement (SIGKILL) en plein tour, tout ce qui précède l'entrée en cours est présent dans le journal ; la session est reprenable.
- **CA-S3** Un REPL ouvert puis fermé sans aucune demande ne laisse aucune session dans la liste.
- **CA-S4** La clé API (valeur lue de l'environnement) n'apparaît dans aucun fichier du journal ni dans les sorties enregistrées, après une session qui a utilisé le modèle.
- **CA-S5** Reprendre une session, changer de branche ou réparer une anomalie ne modifie aucun octet existant du journal : le contenu d'avant reste identique, les ajouts sont à la fin.

### Liste

- **CA-S6** La liste des sessions montre, pour chaque session du dossier courant, identifiant, date de dernière activité, début de la première demande, nombre de demandes, coût et modèle, de la plus récente à la plus ancienne ; une session d'un autre dossier n'y figure pas.

### Reprise

- **CA-S7** Après avoir créé un fichier dans une session fermée par `/quit`, reprendre la session par son identifiant et dire « modifie ce fichier » est compris : l'historique est restauré.
- **CA-S8** À la reprise, le coût cumulé affiché reprend au total d'avant, et un budget de session déjà consommé en partie ne repart pas de zéro.
- **CA-S9** À la reprise, le modèle actif est celui de la fin de la session précédente ; avec l'option de modèle au lancement, c'est le modèle demandé qui est actif et il est enregistré.
- **CA-S10** Après reprise, modifier un fichier lu avant la fermeture est accepté sans relecture ; si le fichier a changé sur le disque depuis sa lecture, la modification est refusée avec le message de détection habituel (002).
- **CA-S11** À la reprise dans le REPL, la conversation complète est réaffichée dans le mode d'affichage de la fermeture (lignes-titres si c'était le mode titres, détail sinon), précédée d'un en-tête (identifiant, date, modèle, coût cumulé), avant l'invite.
- **CA-S12** La commande de reprise du REPL ferme la session courante et ouvre la session choisie, avec les mêmes restaurations ; la session fermée reste reprenable.
- **CA-S13** Un préfixe d'identifiant non ambigu suffit ; un préfixe ambigu est refusé en nommant les candidates.
- **CA-S14** Un identifiant inconnu, une session d'un autre dossier, une version de format inconnue ou un en-tête illisible : message en français qui nomme la cause, aucune session ouverte, journal inchangé.
- **CA-S15** Journal dont la dernière ligne est tronquée : la reprise réussit, un avertissement nomme la ligne ignorée, le fichier n'est pas réécrit, la conversation reprend avec ce qui était lisible.
- **CA-S16** Journal avec une ligne invalide au milieu, ou une entrée dont le parent n'existe pas : refus qui nomme la ligne et la cause, journal inchangé, aucune session ouverte.
- **CA-S17** Journal avec un appel d'action sans résultat : la reprise réussit ; un résultat d'erreur « action interrompue, état inconnu » est ajouté pour cet appel ; le modèle reçoit un historique où chaque appel a un résultat, et sa réponse suivante en tient compte.
- **CA-S18** Reprise d'une session dont le modèle est injoignable ou la clé absente : mêmes messages qu'au lancement, aucune session ouverte, journal inchangé.
- **CA-S19** Un fichier de sortie enregistré (002) créé avant la fermeture existe toujours après `/quit` et après la reprise, et le renvoi du modèle vers ce fichier fonctionne.

### Branches

- **CA-S20** La commande de branche liste les demandes de la branche active, numérotées ; en choisir une puis saisir une nouvelle demande produit une réponse du modèle dont l'historique **ne contient pas** la demande choisie ni les suivantes de l'ancienne branche.
- **CA-S21** Après un changement de branche, l'ancienne branche est toujours entière dans le journal (aucune entrée supprimée ou modifiée).
- **CA-S22** Après un changement de branche, un avertissement dit que les fichiers ne sont pas restaurés ; le modèle reçoit le message correspondant ; modifier un fichier lu avant le changement est refusé tant qu'il n'est pas relu.
- **CA-S23** Le coût cumulé après changement de branche inclut le coût dépensé sur la branche abandonnée.
- **CA-S24** Fermer puis reprendre une session après un changement de branche rouvre la branche active (la nouvelle), pas l'ancienne.

### Concurrence, suppression, purge

- **CA-S25** Une session ouverte dans un REPL ne peut pas être reprise par un second processus (REPL ou headless) : le second échoue avec un message qui nomme la session occupée, et n'écrit rien dans le journal.
- **CA-S26** Après un arrêt brutal (SIGKILL) du processus qui tenait la session, une nouvelle reprise réussit sans intervention manuelle.
- **CA-S27** La commande de suppression, après confirmation, supprime le journal et les sorties enregistrées de la session ; elle disparaît de la liste. Sans confirmation, rien n'est supprimé. Sur une session occupée, elle refuse.
- **CA-S28** Une session sans activité depuis plus de N jours (N de la configuration) est supprimée au lancement suivant, avec ses sorties enregistrées, et un message indique le nombre de sessions purgées ; une session plus récente que N jours ou une session occupée n'est pas supprimée.

### Headless

- **CA-S29** `prompt en argument` : le run exécute la demande sans jamais poser de question ni attendre de saisie (le processus se termine sans entrée standard), et se termine avec le code 0 quand le modèle répond.
- **CA-S30** En sortie texte, stdout contient exactement la réponse finale du modèle (rien d'autre) ; les lignes-titres des actions, le coût, l'identifiant de session et les avertissements sont sur stderr.
- **CA-S31** En sortie JSONL, chaque ligne de stdout est un objet JSON valide avec un champ `type` ; la première ligne porte l'identifiant de session, le modèle, le dossier et si le run reprend une session ; la dernière porte statut, réponse finale, étapes, tokens, coût cumulé et identifiant ; aucune ligne de diagnostic humain n'est sur stdout.
- **CA-S32** En JSONL, les événements arrivent **avant** la fin du run (un appel d'action est lisible sur stdout alors que l'action n'a pas encore rendu son résultat).
- **CA-S33** Un run headless crée une session reprenable : reprendre son identifiant avec un second prompt headless voit l'historique du premier (la réponse du second en tient compte), et le coût cumulé du second inclut celui du premier.
- **CA-S34** Avec l'option « ne rien enregistrer », aucune session n'est créée : la liste des sessions est inchangée après le run.
- **CA-S35** Une erreur d'action (fichier absent) suivie d'une réponse du modèle : code de sortie 0 ; l'erreur est visible dans le flux JSONL.
- **CA-S36** Fournisseur injoignable en cours de run : code 1 ; la ligne finale JSONL donne le statut d'échec et la cause ; la session est enregistrée jusque-là et reprenable.
- **CA-S37** Limite d'étapes ou budget atteint : aucune question posée, code 3, la limite et l'état d'avancement sont indiqués (stderr en texte, ligne finale en JSONL), la session est reprenable.
- **CA-S38** Option invalide, prompt absent, clé manquante, serveur injoignable au lancement, session de reprise introuvable/ambiguë/corrompue/occupée/d'un autre dossier : code 2, message sur stderr, aucune ligne de run en JSONL à part l'erreur éventuelle sur stderr, aucune action exécutée, aucun journal créé ou modifié.
- **CA-S39** Signal d'interruption pendant une commande longue en headless : la commande est tuée, code 130, l'interruption est enregistrée dans la session, qui reste reprenable.

### Validation humaine

- **CA-S40** Session réelle de bout en bout avec un vrai modèle : travail sur plusieurs tours, fermeture du terminal, arrêt du conteneur, reprise le lendemain avec rejeu et coût cumulé corrects ; changement de branche ; un run headless appelé depuis un script shell qui pipe la réponse vers une autre commande et teste le code de sortie.

## 6. Cas limites à couvrir

- Reprise d'une session dont le coût cumulé dépasse déjà le budget : aucun appel au modèle avant la réponse à « continuer ? » dans le REPL ; en headless, code 3 sans appel au modèle.
- Dossier de travail déplacé ou renommé depuis la création de la session : la session n'est plus listée pour le nouveau chemin ; elle est refusée avec le message « autre dossier ».
- Journal vide ou contenant seulement l'en-tête : ni listé ni repris comme une conversation ; refus clair à la reprise par identifiant.
- Deux sessions démarrées dans la même seconde : identifiants distincts.
- Ctrl+C pendant un appel au modèle dans le REPL : l'interruption est enregistrée ; la reprise ne contient ni appel orphelin ni message incomplet.
- Réponse du modèle coupée (longueur maximale) ou fournisseur en erreur en plein tour : ce qui a été reçu avant l'erreur est enregistré ; la reprise ne présente pas de message incomplet comme complet.
- Branche choisie sur la première demande de la session : l'historique est vide avant elle ; la nouvelle branche repart de l'état initial.
- Liste de demandes vide (aucune demande dans la branche active) : la commande de branche le dit sans erreur.
- Disque plein ou journal non inscriptible en cours de session : message clair ; la conversation en mémoire n'est pas perdue ; l'utilisateur est averti que la suite n'est plus enregistrée. En headless : code 1.
- Texte de demande ou de sortie d'action contenant des retours à la ligne, guillemets ou caractères non ASCII : le journal et le flux JSONL restent valides (une ligne par entrée) et se relisent à l'identique.
- Purge : sessions et sorties enregistrées supprimées ensemble ; une purge qui échoue sur une session n'empêche ni le lancement ni la purge des autres.
- Les anciens journaux d'une version du format inconnue ne sont ni repris ni purgés par erreur : refus clair à la reprise, purge selon l'ancienneté comme les autres.

## 7. Règles métier

- Une session = une conversation durable, rattachée à un dossier de travail ; un journal = une session ; un journal peut contenir plusieurs branches ; une seule branche est active.
- Le journal est la source de vérité de la session : ce que le modèle voit à la reprise est reconstruit depuis lui.
- Ce qui est enregistré est ce que le modèle a effectivement reçu (résultats déjà tronqués) : la sortie complète d'une action tronquée vit dans le fichier de débordement (002), pas dans le journal.
- Une session a un seul auteur à la fois.
- Un résultat par appel d'action, y compris après un arrêt brutal.
- Le budget et le coût s'appliquent à la session entière, reprises et branches comprises ; la limite d'étapes s'applique par tour.
- En headless, le code de sortie et la ligne finale JSONL expriment la même chose ; stdout est réservé à la réponse (texte) ou au flux (JSONL).
- Les valeurs de configuration (N jours de la purge, etc.) ne sont pas figées par cette spec.

## 8. Preuve de done

Le contrat de l'itération fixe : tests ciblés, lint, typecheck, build, validation humaine.

- Tests automatisés : CA-S1 à CA-S39, avec un modèle simulé et les vrais outils, sur des comportements visibles (sorties, fichiers du journal, codes de sortie). Les comportements d'arrêt brutal sont testés en tuant réellement un processus.
- Validation humaine : CA-S40.

## 9. Questions ouvertes

Non bloquantes pour l'architecte ; décisions prises seul par le product owner, à confirmer à la relecture :

1. **Retour à une branche abandonnée.** L'entretien a dit « l'ancienne branche reste intacte et réutilisable », mais seul le changement de branche vers l'arrière est spécifié. Aucune commande pour revenir sur une branche abandonnée dans cette itération : à confirmer ou à ajouter.
2. **Valeur de N** (purge) et durée de verrou : non fixées ; à choisir à l'implémentation ou par l'architecte.
3. **Noms** des options de lancement et des commandes de session (reprise, liste, suppression, branche, « ne rien enregistrer ») : à choisir à l'implémentation.
4. **Flux JSONL de sortie et journal de session** : mêmes schémas ou schémas distincts ? Non tranché ; la spec exige seulement que le format du flux soit documenté et stable.
5. **Code 130** pour l'interruption et la distinction des quatre codes 0/1/2/3 sont une proposition retenue par l'utilisateur ; les cas aux frontières (ex. session corrompue en headless = 2) suivent l'esprit « rien n'a tourné ».
6. **Session créée à la première demande** (CA-S3) : hypothèse du product owner, non contestée en entretien.
7. **Purge au lancement** : hypothèse du product owner (pas de tâche de fond).
