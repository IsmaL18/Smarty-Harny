# ADR-0011 — Sorties longues : coupe au milieu et sorties enregistrées

Statut : proposé · Spec : 002 §4.4, §4.5, §6, §9 q.3 et q.4, CA-40 à CA-45 · Remplace : ADR-0002 §3 (lignes « contenu > max_read_chars » et « sortie > max_output_chars ») et §8 ; amende ADR-0007 §2

## Contexte

La v0 garde le début d'une sortie trop longue. Or l'information utile d'une commande en échec (résumé, dernière erreur) est à la fin. Il faut garder le début et la fin, dire ce qui est omis, rendre la sortie complète consultable, sans saturer la mémoire ni le disque, et sans laisser de traces durables dans le projet de l'utilisateur.

## Décision

### Coupe au milieu

1. `max_read_chars` et `max_output_chars` restent des **budgets totaux** (ADR-0007). La coupe se fait **à la limite d'une ligne** : début et fin sont composés de lignes entières. Répartition : **40 % début / 60 % fin** pour une sortie de commande (l'erreur est à la fin), **50 / 50** pour un fichier. Ce sont des constantes de code, pas des clés de configuration.
2. **En-tête** placé dans la sortie, expression en **numéros de ligne**, par exemple `[TRUNCATED: lines 412-9870 of 10120 omitted — read them with read_file(path, offset=412, limit=...)]`. Pour une commande, le chemin du fichier enregistré y figure (CA-43). Les marqueurs sont stables : amender cet ADR pour les changer.
3. **Ligne géante** : si une seule ligne dépasse le budget (fichier minifié), elle est coupée au caractère et l'en-tête le dit en caractères.
4. Une lecture d'une plage hors du fichier renvoie une erreur qui donne le nombre total de lignes (CA-40). La coupe s'applique aussi à la lecture d'un fichier de sortie enregistré, qui est un fichier comme un autre (aucune copie n'est faite).

### Capture de la sortie d'une commande

5. `Environment.run` lit la sortie au fil de l'eau et ne garde en mémoire que le début (budget début) et une fenêtre glissante pour la fin (budget fin), en comptant caractères et lignes. `RunOutcome` porte `head`, `tail`, nombre total de lignes, nombre omis et `saved_path`.
6. **L'écriture sur disque ne commence que si le budget est dépassé** : on tamponne jusqu'au dépassement, puis on ouvre le fichier et on y vide le tampon. Une commande courte n'écrit rien.
7. **Plafond disque** `max_saved_output_mb = 50` (clé `[tools]`, ADR-0007). Au-delà, l'écriture s'arrête, la fenêtre de fin continue de suivre la vraie fin, et l'en-tête signale que le fichier est incomplet. Sans plafond, une commande bavarde remplit le disque en 120 s.
8. Les comportements d'ADR-0002/0005 sur code de sortie, délai dépassé et interruption sont conservés ; la sortie renvoyée est coupée au milieu dans ces cas aussi (CA-42, CA-45).

### Emplacement, cycle de vie, Git

9. **Emplacement** : `<dossier de travail>/.harness/outputs/<id-session>/cmd-<n>.txt` (spec : dossier réservé du dossier de travail). `<id-session>` est un identifiant aléatoire court.
10. **Exclusion de Git** : un fichier `.harness/.gitignore` contenant `*` est créé avec le dossier. Le `.gitignore` de l'utilisateur et `.git/` ne sont jamais touchés.
11. **Fin de session** : un `finally` autour du REPL (`/quit`, Ctrl+D, exception) supprime le dossier de session, puis `.harness/` s'il ne contient plus que son `.gitignore` (CA-44).
12. **Arrêt brutal** (spec §9 q.3) : au lancement, on supprime les dossiers de session dont le fichier le plus récent a plus de 24 h. Une session concurrente dans le même dossier n'est pas touchée. Constante de code. Le dossier de session voit son `mtime` rafraîchi à chaque enregistrement.
13. **Garde de commodité** : `write_file` et `edit_file` refusent un chemin sous `.harness/` avec un message clair. Ce n'est pas une sécurité : le shell peut toujours y écrire (ADR-0002 §5 reste vrai).
14. **Affichage** : le chemin est visible dans l'en-tête, donc en mode détaillé.

## Options considérées

| Sujet | Option | Pour | Contre |
|---|---|---|---|
| Emplacement | **A. `<travail>/.harness/` avec `.gitignore` interne `*`** (retenue) | visible pour l'utilisateur (spec), Git l'ignore sans toucher à ses fichiers | dossier caché dans le projet pendant la session |
| | B. `/tmp` du conteneur | rien dans le projet | invisible côté hôte, contraire à la spec |
| | C. Ligne ajoutée au `.gitignore` de l'utilisateur | explicite | modifie un fichier versionné |
| Arrêt brutal | **A. Purge à 24 h au lancement** (retenue) | aucun mécanisme fragile, sans danger pour une session concurrente | les restes d'un crash survivent jusqu'au prochain lancement (ignorés par Git) |
| | B. `flock` tenu par la session | détection exacte d'une session morte | sémantique non vérifiée sur un montage Colima |
| | C. Purge totale au lancement | simple | casse une seconde session dans le même dossier |
| | D. PID vivant | intuitif | faux entre conteneurs (espaces de PID séparés) |
| Écriture | **A. Seulement si le budget est dépassé** (retenue) | pas de fichiers pour les commandes courtes | tampon en attente |
| | B. Toujours enregistrer | plus simple | disque bruité |
| Plafond | **A. 50 Mo configurables** (retenue) | borne le disque | fichier incomplet pour une sortie énorme |
| | B. Aucun plafond | sortie complète | `yes` remplit le disque |

## Conséquences

- **Vérifié le 2026-11-16, limite acceptée** : un `docker stop` ne passe pas par le `finally` (le harness est le processus 1 du conteneur, sans gestionnaire de SIGTERM) ; `.harness/outputs/` reste après l'arrêt avec la sortie enregistrée. Seule la purge à 24 h au lancement suivant nettoie. Décision : ne pas ajouter de gestionnaire de signal ; les restes sont ignorés par Git et sans danger. À reprendre si le coût disque devient un problème. Aucun test ne couvre ce comportement : l'ADR ne l'affirme pas comme garanti.
- La répartition 40/60 et les budgets sont des réglages de départ, ajustés à l'usage (spec §9 q.4).
- La limite « ligne géante » ne peut pas se lire par plage de lignes : le modèle doit passer par le shell (`cut`, `head -c`).
- `config.example.toml` gagne `max_saved_output_mb` ; le README documente le dossier `.harness/`.
- Assertions à tester : fin et début présents ; zone omise lisible par plage ; fichier de sortie lisible ; dossier supprimé à la sortie ; aucune écriture sous `.harness/` par `write_file`/`edit_file`.
