# Spécification 001 — v0 : la boucle d'agent

Statut : brouillon validé en entretien avec l'utilisateur, à relire avant l'ADR.
Branche : `feat/it1-v0-boucle-agent`.

## 1. Contexte et problème

Ce projet est un harness d'agent LLM personnel, construit par itérations pour apprendre le harness engineering. Son utilisateur est un consultant IA : il s'en sert lui-même et en relit le code pour apprendre.

Il n'existe encore aucun agent. La v0 est la première itération : **le plus petit agent de code utilisable**. Elle doit déjà servir pour de vrai (demander une tâche de code et l'obtenir), tout en restant assez simple pour être relue et comprise.

## 2. Résultat attendu

> En tant que consultant IA, je lance une session dans un terminal, depuis un dossier de travail. J'écris des demandes en langage naturel. L'agent lit, écrit des fichiers et exécute des commandes pour y répondre, enchaîne plusieurs actions avant de répondre, et je vois ce qu'il fait et ce que ça coûte. Il s'arrête de lui-même quand il dépasse ses limites, et une erreur d'action ne fait pas planter la session.

## 3. Périmètre

### Dans le périmètre

- Une session conversationnelle en terminal (ligne par ligne).
- Trois actions pour l'agent : lire un fichier, écrire un fichier, exécuter une commande shell.
- Plusieurs fournisseurs de modèles : Anthropic et tout serveur compatible OpenAI, dont un modèle local sur le Mac.
- Désignation du modèle par configuration, surcharge au lancement et changement en cours de session.
- Limites : nombre maximal d'étapes et budget de coût, avec question « continuer ? ».
- Retour des erreurs d'action à l'agent.
- Affichage des actions en titres, avec un mode détaillé.
- Coût de la session visible.
- Exécution isolée dans un conteneur.

### Hors périmètre (confirmé)

- Édition partielle de fichiers (seule l'écriture complète existe).
- Reprise d'une session fermée : une session fermée est perdue.
- Permissions et approbations avant action. Seule la question « continuer ? » aux limites existe.
- Mémoire entre sessions.
- Compaction du contexte.
- Interface plein écran, dépliage interactif sur place.
- API serveur.

### Risque accepté

La clé API est lisible depuis le conteneur. À traiter dans une itération dédiée.

## 4. Comportement attendu

### 4.1 Session

- Le harness se lance depuis un dossier de l'hôte. Ce dossier, et lui seul, est visible de l'agent. Il en est le dossier de travail, et les chemins relatifs partent de là.
- Au démarrage, le harness affiche le dossier de travail, le modèle actif et les limites.
- L'utilisateur écrit une demande ; l'agent agit puis répond ; l'utilisateur écrit la suivante. La conversation conserve l'historique pendant la session.
- Les modifications faites dans le dossier de travail sont réelles et persistent sur le poste. Le reste du poste est inaccessible à l'agent.
- `/quit` ou Ctrl+D à l'invite quitte la session et affiche le coût total.
- Ctrl+C pendant un tour interrompt l'action en cours (une commande shell en cours est tuée). Le modèle est informé de l'interruption, la session reste ouverte et l'invite revient. Ctrl+C à l'invite, sans rien en cours, ne quitte pas.

### 4.2 Actions de l'agent

L'agent enchaîne autant d'actions que nécessaire avant de répondre, dans la limite des étapes.

| Cas | Comportement |
|---|---|
| Lecture d'un fichier absent ou illisible | L'erreur est renvoyée au modèle, qui peut se corriger. |
| Lecture d'un fichier binaire | Refus explicite renvoyé au modèle. |
| Fichier ou sortie de commande plus long que la taille maximale (config) | Tronqué, avec mention explicite de la troncature au modèle. |
| Écriture dans un dossier inexistant | Le dossier est créé. |
| Écriture sur un fichier existant | Écrasé sans demander. |
| Commande en erreur | Code de sortie et sortie renvoyés au modèle. |
| Commande qui dépasse le délai maximal (config) | Arrêtée ; le modèle est informé du dépassement et reçoit la sortie obtenue jusque-là. |
| Toute autre erreur d'action | Renvoyée au modèle ; la session ne plante pas. |

### 4.3 Affichage

- Chaque événement (action de l'agent, son résultat ou son erreur, réponse) apparaît sur **une ligne-titre**, par exemple « appel de l'outil lecture de fichier : `src/main.py` ».
- Un **mode détaillé**, qu'une commande de session bascule, affiche à la place le détail complet (arguments, résultat ou erreur complets). Le mode reste actif jusqu'à un nouveau basculement.
- Le coût cumulé de la session est visible, et le total s'affiche à la sortie.

### 4.4 Limites

- Deux limites, fixées dans un fichier de configuration : nombre maximal d'étapes par tour, et budget de coût de la session.
- Quand une limite est atteinte, l'agent s'arrête, un message dit laquelle et où il en était, puis il demande « continuer ? ».
  - **Oui** : accorde une nouvelle tranche identique (le même nombre d'étapes, ou le même budget en plus) et l'agent reprend.
  - **Non** : l'agent rend la main ; la session reste ouverte.

### 4.5 Fournisseurs et modèles

- Le modèle par défaut est fixé dans le fichier de configuration. Pour un serveur compatible OpenAI, la configuration porte aussi son adresse.
- Une option de lancement remplace le modèle pour la session.
- Une commande de session change de modèle en cours de session.
- Au démarrage, clé manquante ou serveur injoignable : message clair en français, qui nomme la cause et la correction ; aucune session ne s'ouvre.
- En cours de session, fournisseur injoignable : message clair ; la conversation est conservée et le message suivant de l'utilisateur réessaie.
- Changement de modèle qui échoue (modèle inconnu, clé absente, serveur injoignable) : message clair ; l'ancien modèle reste actif.

## 5. Critères d'acceptation

Chaque critère décrit ce que voient l'utilisateur ou le modèle, sans dépendre de l'organisation interne du code. Les tests utilisent un modèle simulé pour piloter la boucle ; la validation avec de vrais fournisseurs relève de la validation humaine (voir §8).

### Session

- **CA-1** Au lancement depuis un dossier, le harness affiche le dossier de travail, le modèle actif et les limites, puis une invite.
- **CA-2** Après une première demande qui crée un fichier, une seconde demande qui y fait référence (« modifie ce fichier ») est comprise : l'historique est conservé dans la session.
- **CA-3** `/quit` termine la session et affiche le coût total. Ctrl+D à l'invite fait de même.
- **CA-4** Une action ne peut ni lire ni écrire hors du dossier de travail depuis la session isolée : un chemin extérieur au dossier ne donne accès à aucun fichier de l'hôte.

### Actions

- **CA-5** Sur une demande qui exige de lire un fichier, d'en écrire un puis d'exécuter une commande, l'agent enchaîne les trois actions avant de répondre ; le fichier écrit existe ensuite dans le dossier de travail de l'hôte.
- **CA-6** La lecture d'un fichier absent n'arrête pas la session : le modèle reçoit l'erreur, et la réponse suivante du modèle tient compte de cette erreur.
- **CA-7** La lecture d'un fichier binaire est refusée : le modèle reçoit un refus explicite, pas le contenu brut.
- **CA-8** La lecture d'un fichier plus long que la taille maximale, ou une commande à sortie plus longue que cette taille, donne au modèle un contenu tronqué qui mentionne explicitement la troncature.
- **CA-9** L'écriture dans un dossier inexistant crée le dossier et le fichier. L'écriture sur un fichier existant l'écrase.
- **CA-10** Une commande en erreur renvoie au modèle son code de sortie et sa sortie ; la session continue.
- **CA-11** Une commande qui ne termine pas est arrêtée au délai maximal ; le modèle est informé du dépassement et reçoit la sortie partielle ; la session continue.

### Affichage

- **CA-12** Par défaut, chaque événement d'outil s'affiche en une ligne-titre, sans arguments ni résultat complets. **Exception : la réponse du modèle (texte adressé à l'utilisateur) s'affiche toujours en entier, dans les deux modes** (amendé après usage réel : une réponse tronquée est illisible).
- **CA-13** Après la commande de basculement, les événements suivants s'affichent avec leur détail complet ; après un second basculement, on revient aux titres.
- **CA-14** Le coût cumulé de la session est visible à la fin de chaque tour et à la sortie.

### Limites

- **CA-15** Quand le nombre maximal d'étapes est atteint au milieu d'un tour, l'agent s'arrête, un message nomme la limite, puis demande « continuer ? ».
- **CA-16** Répondre « oui » à cette question reprend la tâche pour une tranche d'étapes supplémentaire identique. Répondre « non » rend la main, session ouverte.
- **CA-17** Quand le coût cumulé atteint le budget, aucun nouvel appel au modèle n'est fait avant la réponse à « continuer ? ». « Oui » accorde un budget supplémentaire égal à celui de départ.

### Interruption

- **CA-18** Ctrl+C pendant une commande longue la tue, l'invite revient, la session reste ouverte, et la demande suivante est traitée avec un modèle informé de l'interruption.
- **CA-19** Ctrl+C à l'invite ne quitte pas la session.

### Fournisseurs et modèles

- **CA-20** Au lancement avec une clé manquante, un message en français nomme la clé manquante et la correction ; aucune session ne s'ouvre.
- **CA-21** Au lancement avec un serveur compatible OpenAI injoignable, un message en français nomme le serveur et la cause ; aucune session ne s'ouvre.
- **CA-22** Fournisseur injoignable en cours de session : un message clair s'affiche ; la conversation est conservée ; le message suivant de l'utilisateur réessaie.
- **CA-23** L'option de lancement remplace le modèle de la configuration pour la session ; sans elle, le modèle de la configuration est utilisé.
- **CA-24** La commande de changement de modèle bascule le modèle actif ; les tours suivants l'utilisent et l'historique est conservé. Si le changement échoue, un message clair s'affiche et l'ancien modèle reste actif.

### Isolation (validation humaine)

- **CA-25** Le harness ne fonctionne que dans le conteneur : lancé depuis la commande documentée, l'agent n'a accès qu'au dossier de travail, et une commande de l'agent qui tente d'atteindre un autre dossier de l'hôte n'y parvient pas.

## 6. Cas limites à couvrir

- Réponse de l'utilisateur à « continuer ? » autre que oui/non : la question est reposée.
- Le modèle demande une action inconnue ou avec des arguments invalides : l'erreur lui est renvoyée comme les autres.
- Contexte plus grand que la fenêtre du modèle (pas de compaction en v0) : l'erreur du fournisseur est affichée clairement, la conversation est conservée, la session reste ouverte.
- Modèle local ou autre dont le prix est inconnu : le coût s'affiche comme non estimé et ne consomme pas le budget ; il n'est jamais affiché comme 0 de façon trompeuse.
- Ctrl+C pendant un appel au modèle (pas pendant une commande) : le tour est interrompu proprement, la session reste ouverte.

## 7. Règles métier

- Une **étape** est un aller-retour avec le modèle qui peut déclencher des actions. La limite d'étapes s'applique **par tour** (une demande de l'utilisateur).
- Le **budget** s'applique à toute la session et se cumule sur tous les tours et tous les modèles utilisés.
- Les limites, la taille maximale de lecture, la taille maximale de sortie et le délai maximal de commande sont dans la configuration ; leur valeur n'est pas figée par cette spec.
- Aucune action n'est soumise à approbation en v0.

## 8. Preuve de done

Le contrat de l'itération fixe : tests ciblés, lint, typecheck, build, et validation humaine.

- Tests automatisés : CA-1 à CA-24 avec un modèle simulé et les vrais outils, sur des comportements visibles.
- Validation humaine : CA-25, et une session réelle de bout en bout avec Anthropic et avec un modèle local ou compatible OpenAI.

## 9. Questions ouvertes (non bloquantes pour l'architecte)

1. Valeurs par défaut des limites : nombre d'étapes par tour, budget de session, taille maximale de lecture et de sortie, délai maximal d'une commande. À fixer à l'implémentation ou par l'architecte ; la spec ne les impose pas.
2. La **définition d'une étape** (§7) et la limite **par tour** sont une hypothèse non contestée en entretien : à confirmer à la relecture.
3. Nom exact des commandes de session (`/quit`, bascule de mode détaillé, changement de modèle) : à choisir à l'implémentation.
4. Que fait le harness quand un serveur compatible OpenAI est joignable mais ne publie pas le prix des appels ? Hypothèse retenue en §6 : coût « non estimé ». À confirmer.
