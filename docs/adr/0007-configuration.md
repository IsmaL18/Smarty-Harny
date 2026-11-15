# ADR-0007 — Configuration (fichier et surcharge au lancement)

Statut : proposé · Spec : §4.4, §4.5, §7, §9 q.1, CA-1, CA-23

## Contexte

Les limites, tailles maximales, délai des commandes et modèles viennent d'un fichier de configuration ; le modèle peut être surchargé au lancement. L'agent écrit dans le dossier de travail : une configuration qui y vivrait lui permettrait de relever ses propres limites. La spec ne fige pas les valeurs.

## Décision

1. **Format TOML**, lu avec `tomllib` (bibliothèque standard), dans un fichier utilisateur **hors du dossier de travail** : `~/.config/harness/config.toml` sur l'hôte (surchargeable par `HARNESS_CONFIG` pour le lanceur). Le lanceur en transmet le **contenu** au conteneur par `HARNESS_CONFIG_TOML` (ADR-0006) ; le code Python ne lit que cette variable. Un exemple versionné : `config.example.toml`.
2. **Schéma et valeurs par défaut** (défauts = valeurs de repli quand une clé manque ; `[models]` n'a pas de défaut) :

   ```toml
   default_model = "sonnet"          # alias obligatoire

   [limits]
   max_steps_per_turn = 25           # étapes par tour (ADR-0001)
   budget_usd = 1.00                 # budget de session ; tranche accordée par « oui »

   [tools]
   max_read_chars = 40000            # lecture de fichier
   max_output_chars = 20000          # sortie de commande
   command_timeout_s = 120

   [models.sonnet]
   model = "anthropic/claude-sonnet-5-5"
   # api_key_env = "ANTHROPIC_API_KEY"   # défaut pour anthropic/
   # max_output_tokens = 8192
   # request_timeout_s = 300

   [models.local]
   model = "openai/<nom-du-modèle>"
   api_base = "http://host.docker.internal:8080/v1"
   # input_price_per_mtok / output_price_per_mtok : optionnels (ADR-0004)
   ```
3. **Surcharge au lancement : une seule option, `--model <alias>`** (CA-23). Pas d'option par limite : la spec ne le demande pas, et la configuration unique reste la source de vérité. Ordre : défauts du code < fichier < option.
4. **Configuration immuable** (`dataclass` figée) construite une fois ; une clé inconnue, un type faux, un alias `default_model` absent de `[models]` ou l'absence de tout modèle → erreur en français qui nomme la clé et la correction ; aucune session ne s'ouvre.
5. **Aucune clé API dans le fichier** : seul le *nom* de la variable d'environnement y figure.

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| **A. TOML utilisateur hors dossier, contenu passé en variable** (retenue) | hors de portée de l'agent, un seul chemin hôte visible, pas de dépendance | variable d'environnement un peu inhabituelle ; l'agent peut la lire (comme les clés) |
| B. Fichier `harness.toml` dans le dossier de travail | config par projet | l'agent peut relever ses limites |
| C. Fichier monté en lecture seule | classique | second chemin hôte visible, contre la spec (CA-25) |
| D. Fichier dans l'image | rien à passer | rebuild pour chaque réglage |
| E. Variables d'environnement seules | pas de fichier | profils de modèles lourds à exprimer |

## Conséquences

- Valeurs par défaut tranchées (spec §9 q.1) : 25 étapes/tour, 1,00 $ de budget, lecture 40 000 caractères, sortie de commande 20 000 caractères, délai 120 s. Réglages de départ, à ajuster à l'usage.
- La configuration est lue à chaque lancement : changer la config n'exige pas de rebuild de l'image.
- L'agent peut lire la configuration dans son environnement (pas ses clés en plus de ce qui est déjà accepté).
- Le README documente la création du fichier et fournit `config.example.toml`.
