"""Mode headless (tranche 4), dans un vrai processus : entrée standard, séparation
réelle stdout/stderr, flux JSONL au fil de l'eau, signaux.

Spec 003 §4.8, CA-S29, CA-S30, CA-S32, CA-S39 ; ADR-0012 §7 (descripteur 1 réservé
au protocole, gestionnaires SIGINT/SIGTERM, code 130).

Seam : vrai sous-processus `child_headless.py`, qui appelle
`cli.main.main(argv, client_factory=...)` avec un modèle simulé et les vrais outils ;
le test lit ses vrais descripteurs 1 et 2 et lui envoie de vrais signaux. Les
sessions préparées ou reprises passent par `cli.main.main` dans le processus de test.
"""

import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from child_headless import ACTION_PATH, ANSWER, NOISE, PID_FILE
from support import (
    ScriptedModel,
    headless,
    journals,
    jsonl_lines,
    launch,
    money,
    read_journal,
    say,
    tool_outputs,
    values,
    wait_for,
)

CHILD = Path(__file__).parent / "child_headless.py"


class Child:
    """Un run headless dans un processus à part.

    L'entrée standard reste un tube ouvert jamais écrit ni fermé : un run qui
    attendrait une saisie resterait bloqué. stdout est lu ligne à ligne au fil de
    l'eau (fil de lecture) ; stderr va dans un fichier.
    """

    def __init__(self, workdir: Path, scenario: str, *argv: str):
        self.err_path = workdir.parent / f"stderr-{scenario}-{time.monotonic_ns()}.txt"
        self._err = self.err_path.open("wb")
        self.proc = subprocess.Popen(
            [sys.executable, str(CHILD), str(workdir), scenario, *argv],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._err,
            start_new_session=True,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.out: list[str] = []
        self.ended = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            self.lines.put(raw.decode())
        self.lines.put(None)

    def next_line(self, timeout: float = 30.0) -> str | None:
        """Prochaine ligne de stdout (None à la fin du flux)."""
        if self.ended:
            return None
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError(
                f"aucune ligne sur stdout en {timeout:.0f} s : {self.out}"
            ) from None
        if line is None:
            self.ended = True
        else:
            self.out.append(line)
        return line

    def read_until(self, predicate, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            line = self.next_line(max(0.1, deadline - time.monotonic()))
            assert line is not None, f"flux terminé sans la ligne attendue : {self.out}"
            obj = json.loads(line)
            if predicate(obj):
                return obj

    def finish(self, timeout: float = 30.0) -> tuple[int, str, str]:
        """Attend la fin (stdin toujours ouvert) ; rend (code, stdout complet, stderr)."""
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                "le run headless ne s'est pas terminé : il attend une saisie ou est bloqué"
            ) from None
        while self.next_line(10) is not None:
            pass
        self._err.close()
        return code, "".join(self.out), self.err_path.read_text()

    def kill(self) -> None:
        """Nettoyage. Ne vise le groupe que si le harness tourne encore : après sa
        fin, tuer le groupe tuerait aussi la commande dont on vérifie l'arrêt."""
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.proc.wait()
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        self._err.close()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_command(workdir: Path) -> None:
    """Filet : tue la commande longue si elle a survécu (test en échec)."""
    try:
        pid = int((workdir / PID_FILE).read_text())
        os.kill(pid, signal.SIGKILL)
    except (FileNotFoundError, ProcessLookupError, ValueError):
        pass


def _line_ref(number: int) -> re.Pattern[str]:
    return re.compile(rf"ligne\s*(?:n°\s*)?{number}(?!\d)", re.IGNORECASE)


# --------------------------------------------------------------------------


def test_prompt_run_ends_with_code_0_without_reading_standard_input(workdir):
    """CA-S29 : avec le prompt en argument, le run exécute la demande et se termine
    (code 0) alors que l'entrée standard reste ouverte sans jamais rien recevoir."""
    child = Child(workdir, "answer", "-p", "écris le fichier")
    try:
        code, _out, err = child.finish(timeout=60)
    finally:
        child.kill()

    assert code == 0, f"code {code}, stderr : {err}"
    assert (workdir / ACTION_PATH).exists(), "la demande n'a pas été exécutée"


def test_text_output_puts_only_the_final_answer_on_stdout_and_everything_else_on_stderr(
    workdir, monkeypatch, capfd
):
    """CA-S30 (et ADR-0012 §7, impressions parasites) : en sortie texte, stdout
    contient exactement la réponse finale, même si une bibliothèque imprime sur
    stdout pendant le run ; la ligne-titre de l'action, le coût cumulé, l'identifiant
    de session et l'avertissement (ici : ligne tronquée ignorée à la reprise) sont
    sur stderr."""
    launch(
        [], ["première demande", "/quit"], {"scripted": ScriptedModel([say("ok")])},
        workdir, monkeypatch, capfd,
    )  # fmt: skip
    (path,) = journals(workdir)
    session_id = path.stem
    skipped = len(path.read_text().splitlines()) + 1
    with path.open("a") as journal:
        journal.write('{"id": 99, "parentId": 3, "type": "mess')  # arrêt brutal simulé

    child = Child(workdir, "answer", "--resume", session_id, "-p", "seconde demande")
    try:
        code, out, err = child.finish(timeout=60)
    finally:
        child.kill()

    assert code == 0, f"code {code}, stderr : {err}"
    assert out in (ANSWER, ANSWER + "\n"), (
        f"stdout n'est pas la seule réponse : {out!r}"
    )
    assert NOISE not in out
    assert ACTION_PATH in err, "ligne-titre de l'action absente de stderr"
    assert money("0.03").search(err), "coût cumulé absent de stderr"
    assert session_id in err, "identifiant de session absent de stderr"
    assert _line_ref(skipped).search(err), "avertissement absent de stderr"


def test_jsonl_events_are_written_while_the_action_is_still_running(workdir, request):
    """CA-S32 : en JSONL, l'appel d'action est lisible sur stdout pendant que la
    commande tourne encore (aucun résultat, processus vivant), après la ligne
    `run_started`."""
    request.addfinalizer(lambda: _kill_command(workdir))
    child = Child(
        workdir, "sleep", "-p", "lance la commande longue", "--output-format", "jsonl"
    )
    try:
        first = json.loads(child.next_line() or "null")
        started = child.read_until(lambda obj: obj["type"] == "tool_call")

        assert first["type"] == "run_started"
        assert any("sleep 120" in str(v) for v in values(started))
        assert child.proc.poll() is None, "le run était déjà terminé"
        assert all(json.loads(line)["type"] != "tool_result" for line in child.out)
    finally:
        child.kill()


@pytest.mark.parametrize(
    "signum", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"]
)
def test_signal_during_a_long_command_kills_it_exits_130_and_records_the_interruption(
    workdir, monkeypatch, capfd, request, signum
):
    """CA-S39 : un signal d'interruption ou d'arrêt pendant une commande longue :
    la commande est tuée, code 130, ligne finale `interrupted`, l'interruption est
    enregistrée dans la session, qui reste reprenable (chaque appel a un résultat)."""
    child = Child(
        workdir, "sleep", "-p", "lance la commande longue", "--output-format", "jsonl"
    )
    request.addfinalizer(lambda: _kill_command(workdir))
    pid_file = workdir / PID_FILE
    try:
        child.read_until(lambda obj: obj["type"] == "tool_call")
        wait_for(lambda: pid_file.exists() and pid_file.read_text().strip())
        command_pid = int(pid_file.read_text())
        time.sleep(0.3)  # la commande dort vraiment

        os.kill(child.proc.pid, signum)  # au seul harness, comme `docker stop` au PID 1
        code, out, err = child.finish(timeout=30)
    finally:
        child.kill()

    assert code == 130, f"code {code}, stderr : {err}"
    last = jsonl_lines(out)[-1]
    assert last["type"] == "result" and "interrupted" in values(last)
    try:
        wait_for(lambda: not _alive(command_pid), timeout=10)
    except AssertionError:
        raise AssertionError("la commande longue n'a pas été tuée") from None

    (path,) = journals(workdir)
    marks = [
        e for e in read_journal(path)
        if e.get("type") == "state" and e.get("kind") == "interrupted"
    ]  # fmt: skip
    assert marks, "interruption non enregistrée dans la session"

    model = ScriptedModel([say("repris")])
    resumed = headless(
        ["--resume", path.stem, "-p", "et maintenant ?"], {"scripted": model},
        workdir, monkeypatch, capfd,
    )  # fmt: skip
    assert resumed.code == 0 and model.saw_text("lance la commande longue", 0)
    seen = model.calls[0]
    for call_id in [c["id"] for m in seen for c in m.get("tool_calls") or []]:
        assert len(tool_outputs(seen, call_id)) == 1, (
            "appel sans résultat après reprise"
        )
