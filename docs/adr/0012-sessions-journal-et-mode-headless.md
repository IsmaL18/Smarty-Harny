# ADR-0012 — Sessions durables (journal en ajout seul) et mode headless

Statut : proposé (à valider par l'utilisateur) · Spec : `specs/003-sessions-et-mode-headless.md` (§4, CA-S1 à CA-S39, §9 q.1 à q.7) · Notions : `sessions-et-journal`, `mode-headless` · Amende : ADR-0001 §7, ADR-0006 §2, ADR-0008 §5, ADR-0011 §9, §11, §12

## Contexte

La conversation vit aujourd'hui en mémoire : fermer le terminal la perd. L'itération 3 la rend durable (journal en ajout seul, reprise, branches) et ajoute une entrée scriptable (headless). Cinq contraintes structurent le choix :

- le conteneur est éphémère (`--rm`) et ne voit que le dossier de travail monté sur `/workspace` (ADR-0006) ;
- le processus peut mourir à tout instant (SIGKILL, `docker stop` sans gestionnaire de signal, ADR-0011) ;
- le noyau n'écrit pas dans le terminal et émet des événements typés (ADR-0001, 0008) ;
- l'historique est au format OpenAI chat et chaque appel d'outil a exactement un résultat ;
- plusieurs conteneurs peuvent viser le même dossier, et l'état de `flock` sur un montage Colima n'est pas vérifié (ADR-0011).

## Décision

### 1. Stockage : dans le dossier de travail, sous `.harness/`

1. Journal : `<travail>/.harness/sessions/<id>.jsonl`. Sorties enregistrées : `<travail>/.harness/outputs/<id>/` (même `<id>`, ce qui remplace l'identifiant aléatoire d'ADR-0011 §9). Verrou : `<travail>/.harness/sessions/<id>.lock`. Le `.harness/.gitignore` (`*`) d'ADR-0011 §10 couvre le tout.
2. Le dossier de travail est monté depuis l'hôte : le journal survit à l'arrêt et à la suppression du conteneur, sans second montage (le principe « un seul chemin hôte visible » d'ADR-0006 reste vrai).
3. **Rattachement au dossier** : dans le conteneur le dossier est toujours `/workspace`, donc inutilisable comme identité. Le lanceur passe le chemin hôte (`-e HARNESS_HOST_WORKDIR="$PWD"`) ; l'en-tête le consigne. Une session n'est listée et reprenable que si le chemin de son en-tête égale le chemin courant ; sinon refus « autre dossier », message nommant le chemin d'origine (§4.4 et cas limite « dossier déplacé » de la spec). Sans la variable (tests), le chemin de l'`Environment` sert d'identité.
4. Identifiant : 8 caractères hexadécimaux aléatoires, le fichier est créé en `O_EXCL` (deux sessions dans la même seconde obtiennent des identifiants distincts). Pas de préfixe daté : il rendrait les préfixes ambigus (CA-S13). La date est dans l'en-tête.
5. La session est créée à la **première demande** : l'en-tête et la première entrée partent dans une seule écriture.

### 2. Format et schéma du journal

JSON Lines, UTF-8, une entrée par ligne, `ensure_ascii` laissé à l'implémentation mais retours à la ligne toujours échappés par JSON (CA : texte multiligne).

- **Ligne 1, en-tête** : `{"type":"header","format":1,"session":"<id>","workdir":"<chemin hôte>","created":"<ISO 8601 UTC>","model":"<alias>"}`.
- **Entrées** : `{"id":<entier>,"parentId":<entier|null>,"ts":"<ISO>","type":...}`. `id` est un entier croissant par journal (un seul auteur à la fois, §3). `parentId` désigne l'entrée précédente **de la branche** ; la première a `null`.
- **Types** :

  | `type` | Contenu |
  |---|---|
  | `message` | un message OpenAI chat tel que présenté au modèle (`user`, `assistant` avec `tool_calls` et `finish_reason`, `tool`) ; le modèle utilisé figure sur les messages `assistant` |
  | `usage` | tokens et coût de l'appel ; `cost_usd: null` = non estimé (jamais 0, ADR-0004) |
  | `file_seen` | chemin et empreinte SHA-256 d'un fichier lu, écrit ou modifié par l'outil |
  | `state` | `kind` ∈ `model_changed`, `display_mode`, `interrupted`, `grant` (tranche de budget ou d'étapes), `branch`, `retract`, `skipped_line` |

- **Branche active** : on part de la **dernière entrée écrite** et on remonte par `parentId` jusqu'à la racine. L'historique envoyé au modèle est la liste des entrées `message` de cette chaîne, dans l'ordre. Les entrées `usage`, `file_seen` et `state` font partie de la chaîne mais n'entrent pas dans l'historique.
- **Changer de branche ne réécrit rien** : on écrit une entrée `state/branch` dont `parentId` est l'entrée située juste avant la demande choisie. Les entrées suivantes se chaînent à elle. La même mécanique remplace le « retrait d'une demande sans réponse » d'ADR-0001 §7 : un `state/retract` dont le parent est l'entrée précédant la demande ; en mémoire le retrait de queue continue, le journal enregistre seulement un nouveau point de départ. L'ADR-0001 §7 reste vrai en mémoire ; le journal, lui, ne perd rien.
- **Cumuls et état de session**, calculés sur **tout** le journal, toutes branches comprises : coût (somme des `usage`, CA-S23), tranches de budget accordées, dernier `model_changed` (alias), dernier `display_mode`. Restauration des fichiers lus : `file_seen` de la branche active, depuis la dernière entrée `branch` incluse (CA-S22).
- **Après un changement de branche** : l'interface affiche l'avertissement ; le noyau ajoute un message `user` « le dossier peut différer de ce que cette branche a vu : relis avant de modifier » (précédent : ADR-0005 §2, message d'interruption).
- **Les `file_seen` restaurés n'ont pas de `stat`** : après reprise, `FileTracker` ne sait pas qu'un fichier est « propre » ; une commande shell qui le modifie le laisse donc signalé périmé (comportement prudent, ADR-0010 §5).
- **Version** : `format` entier. Version inconnue ou en-tête illisible = refus (CA-S14). Pas de migration (spec). À l'intérieur d'une version, on peut ajouter des champs et des `type` : le lecteur ignore les champs et les types inconnus mais conserve le chaînage. Tout changement incompatible incrémente `format`.
- **Secrets** : la clé n'est jamais une donnée du journal (l'en-tête ne porte que l'alias). Au moment d'écrire, la valeur exacte des variables nommées par `api_key_env` est remplacée par `[REDACTED]` dans les valeurs texte de l'entrée, avant sérialisation (couvre `env` lancé par le modèle). Le masquage ne touche ni l'en-tête ni les champs de structure (`type`, `ts`, `kind`, `id`…) : un secret très court (`"`, `1`) ne peut donc pas rendre une ligne illisible. Même remplacement dans les sorties enregistrées, avec un tampon de chevauchement de la longueur de la clé pour ne pas rater une clé coupée entre deux blocs. Limite : une clé transformée (base64) n'est pas reconnue.
- **Écriture** : une ligne = un seul `write` sur un descripteur `O_APPEND`, fait **avant** d'exécuter l'étape suivante : la demande avant l'appel au modèle, le message assistant (avec ses `tool_calls`) avant l'exécution des outils, chaque résultat dès qu'il existe. Pas de `fsync` par entrée (un `write` survit à SIGKILL ; le `fsync` ne protège que d'une coupure du VM) ; `fsync` à la fin de chaque tour et à la fermeture.
- **Échec d'écriture** (disque plein, droits) : le magasin lève `JournalError` (sous-classe de `StoreError`, définie côté noyau pour ne pas dépendre de `sessions/`) ; `Session` désactive l'enregistrement, garde la conversation en mémoire et émet `RecordingFailed` (l'interface avertit une fois ; le headless sort en code 1 avec un `result` de statut `error`, la réponse finale n'est alors pas donnée, comme pour tout statut non `ok`). La perte du verrou (§3) suit le même chemin : le journal vérifie qu'il le détient avant chaque écriture.

### 3. Un seul auteur : verrou à bail

1. Prise : création en `O_EXCL` de `<id>.lock` contenant `{token aléatoire, hostname, pid}`. Échec = session occupée, message nommant la session.
2. Un **fil dédié** (pas la boucle `asyncio`, qui peut être bloquée) touche le fichier toutes les 10 s (`os.utime`) tant que la session est ouverte, et vérifie que le jeton est toujours le sien. Si le verrou a été pris par un autre, l'écriture est désactivée comme en cas de `JournalError`.
3. **Verrou périmé** si sa date de modification a plus de `lock_stale_s` (30 s) **ou** si le `hostname` est celui du processus courant et que son `pid` n'existe plus (reprise immédiate après un SIGKILL dans le même conteneur, sans attendre le bail). Entre conteneurs, le hostname diffère : c'est le bail qui joue, au pire 30 s d'attente après un crash.
4. **Reprise d'un verrou périmé** : renommage atomique du fichier vers un nom unique (un seul gagnant), suppression, puis création `O_EXCL`. Le perdant voit « occupée ».
5. La liste, la suppression et la purge testent le même verrou (une session occupée est signalée, non supprimable, non purgeable).
6. Libération normale : suppression du fichier de verrou.

### 4. Réparation à la reprise, sans réécriture

La lecture est la seule étape qui interprète les anomalies ; elle ne modifie rien ; les réparations sont des **ajouts**.

| Anomalie | Traitement |
|---|---|
| Dernière ligne non terminée par `\n` ou illisible | ignorée, avertissement nommant la ligne. Avant le premier ajout, on écrit `\n` (ferme la ligne) puis une entrée `state/skipped_line {line: N}`. |
| Ligne invalide au milieu | refus **sauf** si une entrée `skipped_line` la désigne. C'est ce qui garde un journal réparé relisible : sans cette règle, la ligne tronquée fermée par `\n` deviendrait une « ligne invalide au milieu » à la reprise suivante. |
| `parentId` désignant une entrée inexistante | refus nommant la ligne. |
| Appel sans résultat | pour chaque appel de la dernière entrée `assistant`, une entrée `message`/`tool` « error: action interrompue, état inconnu », chaînée à la fin. L'historique du modèle reçoit ce résultat : le modèle est informé par le texte même. |
| Dernier message `assistant` coupé par la longueur sans appel d'outil | conservé tel quel avec son `finish_reason: "length"` ; le rejeu l'affiche comme coupé (jamais comme complet). |

Journal vide ou en-tête seul : ni listé ni repris comme conversation.

### 5. Durée de vie des sorties longues (remplace ADR-0011 §11)

- Une session enregistrée possède `outputs/<id>/` : plus de suppression à la sortie ; suppression avec la session.
- **Ordre de suppression** : sorties d'abord, journal ensuite. Une interruption au milieu laisse un journal dont les sorties ont disparu (cas déjà toléré, spec §4.4) ; l'ordre inverse laisserait un dossier orphelin. `.harness/` est nettoyé s'il ne contient plus que son `.gitignore`.
- **Run non enregistré** (`--no-session`) : le comportement d'ADR-0011 §11 reste valable (dossier éphémère supprimé à la fin) ; la purge à 24 h d'ADR-0011 §12 reste en place pour les dossiers `outputs/` **sans journal** (restes d'un run non enregistré mort brutalement). Elle ne touche jamais le dossier d'une session qui a un journal.
- **Purge à N jours** : au lancement, toutes les sessions du dossier courant dont le journal n'a pas été modifié depuis `retention_days` (défaut **30**) sont supprimées, sauf si occupées. La date de modification du journal est la date de dernière activité (et rien d'autre ne le touche : le verrou est un autre fichier). La purge ne lit pas le contenu : un journal d'un format inconnu est purgé selon l'âge. L'échec sur une session est signalé sur stderr et n'arrête ni la purge ni le lancement. Limite : on ne purge que le dossier lancé ; un dossier jamais relancé garde ses sessions (elles sont dans le projet, donc supprimées avec lui).

### 6. Interface : options, commandes, configuration

- **Lancement** : `--sessions` (liste du dossier), `--resume <id|préfixe>`, `--delete <id|préfixe>` (confirmation), `-p/--prompt <texte>` (headless), `--output-format text|jsonl` (défaut `text`), `--no-session` (headless seulement). `--model` reste valable à la reprise.
- **REPL** : `/resume [id|numéro]` (sans argument : liste numérotée des sessions du dossier), `/branch` (liste numérotée des demandes de la branche active ; choisir repart d'avant la demande). Les commandes inconnues restent traitées comme dans ADR-0008 §5.
- **Configuration** : `[sessions] retention_days = 30`, `lock_stale_s = 30` (ADR-0007, `config.example.toml`).

### 7. Mode headless

**Architecture.** Le noyau reste inchangé dans sa forme : `cli/headless.py` consomme `Session.run_turn` comme le REPL ; il n'appelle jamais `resume_turn` (donc jamais de question). Le statut vient de `TurnEnded` :

| `TurnEnded` / cas | Statut JSONL | Code |
|---|---|---|
| `done` | `ok` | 0 |
| `provider_error`, `RecordingFailed` | `error` | 1 |
| option invalide, prompt absent, config, clé, serveur injoignable, session introuvable/ambiguë/autre dossier/corrompue/occupée | (aucune ligne JSONL) | 2 |
| `step_limit`, `budget_limit` | `limit` | 3 |
| `interrupted` (SIGINT ou SIGTERM) | `interrupted` | 130 |

- **Résultat final** (texte et JSONL) : l'unique « réponse finale » est le texte du message assistant qui termine le tour (sans appel d'outil), donc seulement quand le statut est `ok`. Pour tout autre code, stdout du mode texte est vide : lecture retenue de §4.8.3 de la spec (voir « Points à confirmer »).
- **Séparation des flux** : au démarrage du headless, le descripteur 1 d'origine est dupliqué pour le seul protocole, puis `sys.stdout` et le descripteur 1 sont redirigés vers stderr. Toute impression parasite (bibliothèque, avertissement) va sur stderr ; aucun texte étranger n'entre dans stdout.
- **Signaux** : SIGINT et SIGTERM annulent la tâche du tour (ADR-0005) ; le noyau ferme l'historique ; l'état `interrupted` est écrit ; code 130. Le processus du conteneur est le PID 1 : sans gestionnaire explicite SIGTERM serait ignoré, donc le gestionnaire est installé pour le headless.
- **Lanceur** (amende ADR-0006 §2) : `-t` n'est passé que si stdin **et** stdout sont des terminaux ; un run piloté par un script n'a pas de pty (un pty fusionnerait stdout et stderr et transformerait les fins de ligne). Le code de sortie du conteneur est celui de `docker run`.
- **Flux JSONL** : un objet par ligne, écrit et vidé à chaque événement. Lignes : `run_started` (session, modèle, dossier, `resumed`), `tool_call` (id, nom, arguments), `tool_result` (id, contenu tel que reçu, `is_error`), `assistant_message`, `warning`, puis `result` (statut, raison, réponse finale, étapes, tokens, coût cumulé de la session, session). `ToolCallStarted` gagne un champ `id` pour relier appel et résultat. Le schéma est documenté dans le README et porte un champ `schema` (entier, démarre à 1) sur `run_started`.

### 8. Schéma du flux et schéma du journal : distincts (spec §9 q.4)

Deux formats, deux contrats, **une source commune** : le noyau émet les événements typés ; le journal enregistre ce que le modèle a reçu (messages, chaînage) ; le flux projette les événements pour un lecteur externe. Aucun code ne convertit l'un en l'autre.

### 9. Réponses aux questions ouvertes

- **q.1 Retour à une branche abandonnée** : pas de commande en itération 3 (confirme la spec). Le format le permet sans changement : revenir à une branche = écrire une entrée `branch` dont le parent est la pointe de l'ancienne. Aucune migration à prévoir.
- **q.2 Valeurs** : N = 30 jours ; bail de verrou 30 s, battement 10 s ; tous trois en configuration.
- **q.3 Noms** : voir §6.
- **q.4** : schémas distincts (§8).
- **q.5 Codes** : retenus tels quels ; 0/1/2/3/130 (§7).
- **q.6 Création à la première demande** : retenue (§1.5).
- **q.7 Purge au lancement** : retenue ; la purge se fait aussi en headless, avec son message sur stderr (§5).

## Options considérées

| Sujet | Option | Pour | Contre |
|---|---|---|---|
| **Stockage** | **A. `<travail>/.harness/sessions/` (retenue)** | aucun montage ajouté (ADR-0006 intact), cohabite avec les sorties enregistrées (même cycle de vie), supprimé avec le projet, verrou partagé entre conteneurs par le même montage | journaux dans le projet (ignorés par Git, mais vus par les outils de synchronisation ou de recherche) ; l'agent peut les lire ou les altérer par le shell ; un dossier déplacé emporte ses journaux mais les refuse (identité = chemin d'origine) |
| | B. Dossier central `~/.local/share/harness/` monté en plus | purge globale, aucune trace dans le projet | second chemin hôte visible, **tous les projets lisibles et modifiables par l'agent** ; viole le principe « un seul chemin hôte » d'ADR-0006 et CA-25 de la 001 |
| | C. Volume Docker nommé | invisible de l'agent hors montage | pas de rattachement au dossier, invisible de l'utilisateur, détruit avec Colima |
| **Format** | **A. JSONL avec `id`/`parentId` entiers (retenue)** | ajout seul natif, un seul auteur rend l'entier sûr, branches gratuites, un arrêt brutal ne perd que la dernière ligne | lecture complète pour reconstituer ; tolérance aux anomalies à coder |
| | B. Un fichier JSON complet réécrit à chaque tour | simple à lire | réécriture : un arrêt brutal peut tout corrompre ; contredit « ajout seul » |
| | C. SQLite | requêtes, transactions | binaire opaque pour l'utilisateur, branches et reprise plus lourdes, cohérence sur montage virtiofs à vérifier |
| | D. JSONL, `id` aléatoires (hex) | fusion possible de journaux | inutile avec un seul auteur ; plus de vérifications d'unicité |
| **Verrou** | **A. Fichier `O_EXCL` + bail renouvelé + test pid/hostname (retenue)** | survit au SIGKILL, ne dépend pas de la sémantique des verrous du montage, tient entre conteneurs | jusqu'à 30 s d'attente après un crash entre conteneurs ; dépend d'une horloge raisonnablement commune |
| | B. `flock` | libération exacte à la mort du processus | sémantique non vérifiée sur Colima (ADR-0011) ; à reconsidérer si une vérification la confirme |
| | C. PID seul | intuitif | faux entre conteneurs (espaces de PID séparés) |
| | D. Verrou sans expiration | simple | un crash bloque la session pour toujours (contredit §4.6) |
| **Réparation** | **A. Lecture tolérante + ajouts (`skipped_line`, résultat d'erreur) (retenue)** | respecte CA-S5, journal relisible après réparation | une règle de plus dans le lecteur |
| | B. Tronquer le fichier / réécrire | journal propre | contredit « rien n'est modifié » |
| | C. Fichier annexe de réparations | pas de ligne spéciale | journal et annexe à garder cohérents |
| **Flux headless** | **A. Schéma distinct du journal (retenue)** | contrat public stable indépendant du format interne ; peut porter `warning` et `result` qui ne sont pas du journal | deux formats à documenter et à tester |
| | B. Flux = lignes du journal | un seul schéma | l'API publique du headless gèle le format interne (chaînage, `usage`, `retract`) ; les lignes de début et de fin n'existent pas dans le journal ; la rédaction des secrets modifierait ce que le script reçoit |
| **Sorties longues** | **A. `outputs/<id>/` lié à la session ; purge 24 h conservée pour les orphelins (retenue)** | simple, cohérent avec la spec | deux règles de vie selon que la session est enregistrée |
| | B. Garder la purge 24 h pour tout | aucun changement | contredit la spec (sorties vivant autant que leur session) |

## Justification

Le journal est la source de vérité (spec §7) : on retient le format le plus simple qui soit **réellement** en ajout seul. Les branches, la restauration du modèle, du coût et des fichiers lus sont des projections de cette même liste d'entrées, sans second état à garder cohérent. Le stockage dans le dossier de travail est le seul choix qui ne rouvre pas la frontière de sécurité d'ADR-0006 : un dossier central rendrait lisible, par le shell de l'agent, le contenu en clair de tous les projets. Pour le verrou, on choisit de ne dépendre d'aucune sémantique de système de fichiers non vérifiée ; le bail est la seule notion qui survive aux espaces de PID séparés. Des schémas distincts pour le flux évitent qu'un script d'utilisateur gèle le format interne.

## Conséquences

- **Démarrage partagé** : `cli/startup.py` porte l'ouverture de session (reprise ou neuve, modèle, `check`) et la purge au lancement, communes au REPL et au headless ; chaque interface décide de l'affichage et du code de sortie d'après le refus rendu.
- **Modifications** : `Session` reçoit un magasin (protocole défini côté noyau, adaptateur dans un module `sessions/` ; `cli` câble) ; l'historique passe par un point unique de mutation qui journalise. Nouveaux événements : `RecordingFailed`, champ `id` sur `ToolCallStarted`. `OutputStore` prend l'identifiant de session et ne se nettoie plus lui-même pour une session enregistrée. `FileTracker` accepte une restauration depuis les `file_seen`.
- **Testabilité** : les tests de SIGKILL lancent un vrai sous-processus qui appelle `cli.main.main(argv, client_factory=...)` avec un modèle simulé fourni par le test (le point d'entrée accepte une fabrique de client ; la garde conteneur reste dans `main`). Le contrat headless (flux, codes) se teste en appelant `main` avec des flux capturés ; l'isolation stdout/stderr, elle, exige un sous-processus.
- **README** : documenter `.harness/sessions/`, le format du flux JSONL, les codes de sortie, la limite « journal en clair » et l'ajout du fichier au `.gitignore` interne.
- **Limites acceptées** : le journal peut être lu ou modifié par l'agent via le shell (comme le reste du dossier, ADR-0002 §5) ; le journal est en clair (spec §4.7) ; jusqu'à 30 s d'attente après un crash entre conteneurs ; une clé transformée n'est pas masquée ; un dossier jamais relancé n'est jamais purgé.
- **Non vérifié** : l'atomicité de `rename` et `O_EXCL` sur le montage Colima, la dérive d'horloge entre l'hôte et le VM (le bail de 30 s la tolère jusqu'à quelques secondes), le comportement de SIGTERM transmis par `docker run` sans pty. À contrôler à la validation humaine (CA-S40).
- **Assertions à tester** (celles de la spec, CA-S1 à CA-S39) ; en plus de la spec, trois points propres à cet ADR : un journal réparé (ligne tronquée) se reprend une seconde fois sans refus ; un `--no-session` laisse `.harness/outputs/` nettoyé ; stdout du mode texte reste vide pour un code non nul.

## Points confirmés avec le product owner (2026-11-16)

1. **Secret masqué dans le journal** : confirmé. La valeur de la clé API est remplacée par `[REDACTED]` à l'écriture ; CA-S4 prime sur « tel que reçu ». Limite acceptée : une clé encodée n'est pas reconnue.
2. **Dossier déplacé** : confirmé. L'identité d'une session est le chemin d'origine ; après un déplacement elle est refusée (« autre dossier »), comme l'écrit la spec.
3. **Stdout du mode texte en code non nul** : confirmé, toujours vide. Cela précise la spec §4.8.3 (qui admettait une réponse déjà produite) : la réponse finale n'existe que pour le statut `ok`.
