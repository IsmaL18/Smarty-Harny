"""Processus enfant des tests headless : un vrai run `-p` dans un processus à part.

Lancé par `test_headless_process.py` :
`python child_headless.py <dossier> <scénario> <argv du harness...>`.
Il appelle `cli.main.main(argv, client_factory=...)` avec un modèle simulé
(ADR-0012 §Conséquences) ; ses vrais descripteurs 0, 1 et 2 sont ceux que le test
lui donne, ce qui permet de vérifier la séparation stdout/stderr, l'écriture au fil
de l'eau et la réaction aux signaux.

- `answer` : une action (`write_file` de `titre-action.txt`), puis, pendant le second
  appel au modèle, une bibliothèque imprime du bruit sur stdout (par `print` et
  directement sur le descripteur 1), puis la réponse finale `ANSWER`.
- `sleep` : une commande longue qui écrit son pid dans `commande.pid` puis dort 120 s.
"""

import os
import sys
from pathlib import Path

from support import ScriptedModel, call, say, tools

ANSWER = 'Réponse finale : « fait », avec "guillemets"\net une seconde ligne é'
NOISE = "bruit-de-bibliotheque"
ACTION_PATH = "titre-action.txt"
PID_FILE = "commande.pid"
LONG_COMMAND = f"echo $$ > {PID_FILE}; exec sleep 120"


def _noisy_answer(_messages: list[dict]):
    print(NOISE + "-print", flush=True)
    os.write(1, (NOISE + "-fd\n").encode())
    return say(ANSWER, cost=0.02)


def run() -> int:
    from harness.cli import main as cli_main

    workdir, scenario, argv = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    os.chdir(workdir)
    os.environ["HARNESS_IN_CONTAINER"] = "1"
    os.environ["HARNESS_CONFIG_TOML"] = (
        'default_model = "scripted"\n'
        '[models.scripted]\nmodel = "openai/scripted"\n'
        "[tools]\ncommand_timeout_s = 300\n"
    )
    if scenario == "answer":
        model = ScriptedModel(
            [
                tools(call("write_file", path=ACTION_PATH, content="x"), cost=0.01),
                _noisy_answer,
            ]
        )
    else:
        model = ScriptedModel(
            [tools(call("shell", command=LONG_COMMAND)), say("jamais atteint")]
        )
    return cli_main.main(argv, client_factory=lambda _profile: model)


if __name__ == "__main__":
    sys.exit(run())
