"""Processus enfant des tests de sessions : un vrai harness qu'on peut tuer.

Lancé par `test_sessions_resume.py` (`python child_session.py <dossier> <mode>`).
Il appelle `cli.main.main(argv, client_factory=...)` avec un modèle simulé
(ADR-0012 §Conséquences), exactement comme `launch`, mais dans un processus à part
pour que le test puisse lui envoyer SIGKILL.

- `sleep` : une demande, un premier outil rapide, puis une commande `sleep` : le
  processus reste bloqué en plein tour.
- `hold` : une demande, une réponse, puis le REPL reste ouvert sur l'invite.
"""

import os
import sys
import time
from pathlib import Path

from support import ScriptedModel, call, say, tools


def run() -> int:
    from harness.cli import main as cli_main

    workdir, mode = Path(sys.argv[1]), sys.argv[2]
    os.chdir(workdir)
    os.environ["HARNESS_IN_CONTAINER"] = "1"
    os.environ["HARNESS_CONFIG_TOML"] = (
        'default_model = "scripted"\n'
        '[models.scripted]\nmodel = "openai/scripted"\n'
        "[tools]\ncommand_timeout_s = 300\n"
    )
    if mode == "sleep":
        model = ScriptedModel(
            [
                tools(call("shell", command="echo avant")),
                tools(call("shell", command="sleep 120")),
                say("jamais atteint"),
            ]
        )
        lines = ["lance la tâche"]
    else:
        model = ScriptedModel([say("session ouverte")])
        lines = ["ouvre la session"]

    def fake_input(prompt: str = "") -> str:
        print(prompt, end="", flush=True)
        if lines:
            return lines.pop(0)
        time.sleep(600)  # garde le REPL ouvert sur l'invite
        raise EOFError

    import builtins

    builtins.input = fake_input
    return cli_main.main([], client_factory=lambda _profile: model)


if __name__ == "__main__":
    sys.exit(run())
