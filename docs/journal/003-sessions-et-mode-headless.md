# Journal 003 — Sessions et mode headless

Fiches de notion associées : [`sessions-et-journal`](../notions/sessions-et-journal.md), [`mode-headless`](../notions/mode-headless.md) (génériques, sans référence au projet). Spec : `specs/003-sessions-et-mode-headless.md`. ADR : `docs/adr/0012-sessions-journal-et-mode-headless.md` (amende 0001, 0006, 0008, 0011). Tests : `TESTS.md` (T-0084 à T-0125). Contrat : Structurel, revues fusionnée, séparation test-writer en contexte neuf. État au 2026-11-16 : rien n'est commité, la revue fusionnée est lancée.

## Ce qui a été construit

- Journal JSONL en ajout seul dans `<travail>/.harness/sessions/<id>.jsonl` : en-tête (format, dossier hôte, date, modèle), entrées `id`/`parentId` (`message`, `usage`, `file_seen`, `state`).
- Reprise (`--resume`, `/resume`), liste (`--sessions`), suppression (`--delete`), branches (`/branch`), purge à 30 jours au lancement.
- Verrou à bail (fichier `O_EXCL`, battement 10 s par un fil dédié, péremption 30 s ou pid mort sur le même hôte).
- Réparation à la reprise par ajouts : `skipped_line`, résultat d'erreur synthétique pour un appel sans résultat.
- Masquage de la clé API à l'écriture, dans le journal et dans les sorties enregistrées.
- Mode headless (`-p`, `--output-format text|jsonl`, `--no-session`) : stdout réservé par duplication du descripteur 1, flux JSONL vidé à chaque événement, codes 0/1/2/3/130, SIGINT et SIGTERM.
- `id` sur `ToolCallStarted` et `ToolCallFinished` ; `Journal.interrupted()` appelé par le noyau à l'annulation (vaut aussi pour le REPL).

## Décisions et leurs raisons

- **Journal dans le dossier de travail, pas dans un dossier central** (ADR-0012 §1) : un dossier central monté en plus rendrait tous les projets lisibles par le shell de l'agent et romprait « un seul chemin hôte visible » (ADR-0006).
- **Identité = chemin hôte d'origine**, passé par `HARNESS_HOST_WORKDIR` : dans le conteneur le dossier est toujours `/workspace`.
- **Verrou à bail plutôt que `flock` ou pid seul** (§3) : `flock` n'est pas vérifié sur Colima, le pid est faux entre conteneurs.
- **Réparation par ajouts, jamais par réécriture** (§4) : sans l'entrée `skipped_line`, une ligne tronquée refermée devient une « ligne invalide au milieu » à la reprise suivante.
- **Flux headless distinct du journal** (§8) : le contrat public ne gèle pas le format interne.
- **Stdout du mode texte vide pour tout code non nul** (confirmé avec le product owner) : précise la spec §4.8.3.
- **Création de la session à la première demande** : une ouverture sans demande ne laisse aucun fichier.

## Décisions prises seul, non revues

`tidy` public dans `outputs.py` ; `key_env(profile)` extrait de `litellm_client` ; message de purge sur stdout dans le REPL ; confirmation de `--delete` par `input()` ; headless : garde conteneur et config invalide = code 2 quand `-p` ; `--no-session` sans `-p` ou avec `--resume` = erreur d'usage (2) ; champs du `result` : status, reason, error_kind, answer, steps, tokens, cost_usd, session ; texte des événements sur stderr via `render` ; purge au lancement aussi en headless.

## Pièges rencontrés

À compléter avec les findings de la revue fusionnée. Aucun piège de revue consigné à ce jour.

## Non vérifié

- Atomicité de `rename` et `O_EXCL` sur le montage Colima, dérive d'horloge hôte/VM : non vérifiées en tant que telles (la validation manuelle n'a rien montré d'anormal).
- Clé coupée entre deux blocs de sortie : non testé. Échec de purge d'une session sans bloquer les autres : non testé.
- Headless : préfixe ambigu absent du test CA-S38 ; échec à la création du journal ambigu (code 1 ou 2).
- README (schéma du flux JSONL, codes de sortie, limite « journal en clair ») pas encore écrit (demandé par l'ADR-0012).
- Aucune revue indépendante des correctifs de revue : reviews `aucune` choisies par l'utilisateur pour ce correctif.

## Process : ce que l'itération a montré

- À compléter après la revue fusionnée et le grill.

## Grill de fin d'itération

À faire après la livraison.

## Validation manuelle

Faite par l'utilisateur le 2026-11-17 (CA-S40), dans le conteneur, avec un vrai modèle : lanceur (`HARNESS_HOST_WORKDIR`, `-t` conditionnel, stdout du mode `-p` propre dans un pipe), session multi-tours puis fermeture brutale et `docker stop`, reprise avec rejeu et coût cumulé, refus « occupée » et « autre dossier » (dossier déplacé), `/branch`, headless en script shell (pipe, codes de sortie, JSONL, reprise, `--no-session`, codes 2 et 3), signaux (`docker stop` et Ctrl+C, code 130, session reprenable), échec d'écriture du journal (avertissement, conversation conservée). L'utilisateur rapporte que tout est OK. Je n'ai rien exécuté moi-même ; les sorties exactes n'ont pas été consignées.

## Suite

Itération 4 (feuille de route) : sécurité et permissions. Le mode headless y réclame une politique d'approbation sans humain (refus par défaut).
