"""Fixtures partagées des tests de comportement du harness."""

import os
import signal
import threading
from collections.abc import Iterator

import pytest


@pytest.fixture
def workdir(tmp_path):
    """Dossier de travail de l'agent : un dossier temporaire réel de l'hôte."""
    path = tmp_path / "workdir"
    path.mkdir()
    return path


class SigintTimer:
    """Envoie un vrai SIGINT au processus de test après un délai (ADR-0005).

    Filet de sécurité : tant que le harness n'a pas installé son propre
    gestionnaire, un SIGINT est seulement noté au lieu de lever
    `KeyboardInterrupt`, ce qui interromprait toute la session pytest.
    """

    def __init__(self) -> None:
        self.unhandled = 0
        self._timers: list[threading.Timer] = []

    def _fallback(self, signum, frame) -> None:
        self.unhandled += 1

    def after(self, seconds: float) -> None:
        timer = threading.Timer(seconds, os.kill, (os.getpid(), signal.SIGINT))
        timer.daemon = True
        self._timers.append(timer)
        timer.start()

    def cancel(self) -> None:
        for timer in self._timers:
            timer.cancel()


@pytest.fixture
def sigint() -> Iterator[SigintTimer]:
    timer = SigintTimer()
    previous = signal.signal(signal.SIGINT, timer._fallback)
    try:
        yield timer
    finally:
        timer.cancel()
        signal.signal(signal.SIGINT, previous)
