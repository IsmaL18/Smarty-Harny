# ADR-0006 — Conteneur et dossier de travail monté

Statut : proposé · Spec : §3 (risque accepté), §4.1, CA-4, CA-25 · Notion : `conteneur-frontiere`

## Contexte

Le harness s'exécute entièrement dans un conteneur Docker (Colima). Seul le dossier de lancement est visible de l'agent, et ses modifications sont réelles sur l'hôte. La clé API est lisible dans le conteneur (risque accepté, it. 15). La sécurité de la v0 repose sur cette frontière (ADR-0002 §5) : pas de permissions applicatives avant l'it. 4.

## Décision

1. **Une image** (`docker/Dockerfile`) : Python 3.12, `uv`, `bash`, `git`, `ripgrep`, outils usuels ; le code du harness y est installé (`uv sync --frozen`, versions du `uv.lock`). Variable `HARNESS_IN_CONTAINER=1` définie dans l'image.
2. **Un lanceur sur l'hôte** (`bin/harness`, script shell) : c'est la « commande documentée » de CA-25. Il lance :
   `docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD":/workspace -w /workspace --add-host=host.docker.internal:host-gateway -e ANTHROPIC_API_KEY (et les autres clés nommées par la config) -e HARNESS_CONFIG_TOML="$(cat <config>)" harness "$@"`
   - **un seul montage** : le dossier courant, sur `/workspace` (chemins relatifs et dossier de travail = `/workspace`) ;
   - utilisateur de l'hôte (UID/GID) pour que les fichiers créés ne appartiennent pas à root ; `HOME` pointe vers un dossier temporaire du conteneur ;
   - clés transmises par `-e NOM` (sans valeur sur la ligne de commande) ;
   - configuration transmise **par variable d'environnement** et non par montage, pour que le dossier de travail reste le seul chemin de l'hôte visible, comme l'énonce la spec (ADR-0007) ;
   - réseau ouvert (nécessaire pour les API et `pip`/`npm` ; restriction à l'it. 4) ; pas d'options de durcissement en v0 (`cap-drop`, `no-new-privileges`, limites : it. 4).
3. **Garde au démarrage** : `cli.main` refuse de s'ouvrir si `HARNESS_IN_CONTAINER` est absente (message en français pointant vers `bin/harness`). Cela réalise « ne fonctionne que dans le conteneur » (CA-25). La garde n'est **que** dans `main` : le noyau et le REPL, appelés directement par les tests, ne la connaissent pas.
4. **Modèle local** : le profil utilise `http://host.docker.internal:<port>/v1`.
5. **Pas de montage de `.git` en lecture seule, de `~` ou du socket Docker** ; pas de privilèges.

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. Image avec le code + lanceur qui monte `$PWD`** (retenue) | simple, un montage, reproductible via `uv.lock` | reconstruire l'image à chaque changement de code |
| B. Image générique + code du harness monté | pas de rebuild pendant le développement | deuxième chemin hôte visible par l'agent (viole CA-25) ; agent peut modifier le harness |
| C. `docker compose` | déclaratif | surcouche inutile pour un seul service interactif |
| D. Exécution sur l'hôte avec contrôle de chemins | pas de Docker | contredit CLAUDE.md et la spec ; `shell` non confinable |

## Conséquences

- Le dossier de travail est **modifiable sans retour arrière** ; si l'utilisateur lance depuis un dossier sensible (`~`), l'agent y a plein accès : à documenter dans le README. Le harness affiche le dossier de travail au démarrage (CA-1).
- Pendant le développement, un `docker build` précède chaque essai ; un script `bin/dev` (ou une cible de lancement) peut le faire, hors décision d'architecture.
- **Non vérifié** (à confirmer à la session réelle) : `host.docker.internal` + `host-gateway` sous Colima ; l'écoute de `mlx_lm.server` sur une adresse atteignable depuis le conteneur ; les droits d'écriture des fichiers créés par l'UID de l'hôte sur le montage Colima.
- Les tests automatisés n'utilisent pas Docker : CA-25 reste de la validation humaine.
