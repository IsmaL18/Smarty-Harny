"""Démarrage commun au REPL et au mode headless : ouverture de session et purge.

Notion : sessions-et-journal. Les deux interfaces ouvrent une session de la même façon
(reprise ou neuve → modèle → `check` du client → modèle repris) ; seuls changent les
canaux d'affichage et les codes de sortie, que l'appelant décide d'après `Refused`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from harness.config import Config, ModelProfile
from harness.models.base import ModelClient, ProviderError
from harness.session import RestoredState
from harness.sessions.journal import Journal, JournalError, purge_expired
from harness.tools.environment import Environment
from harness.tools.outputs import OutputStore


@dataclass
class Opened:
    journal: Journal | None  # None seulement en `--no-session`
    restored: RestoredState | None
    alias: str
    client: ModelClient


@dataclass
class Refused:
    message: str
    journal_failure: (
        bool  # reprise refusée ou journal inutilisable (sinon : modèle/client)
    )


async def open_session(
    config: Config,
    client_factory: Callable[[ModelProfile], ModelClient],
    env: Environment,
    host: str,
    secrets: tuple[str, ...],
    *,
    resume: str | None,
    model_override: str | None,
    record: bool = True,
) -> Opened | Refused:
    """Ouvre une session neuve ou reprise ; sinon dit pourquoi elle est refusée.

    Un refus rend le verrou : la session reste reprenable.
    """
    stale_s = config.sessions.lock_stale_s
    restored: RestoredState | None = None
    journal: Journal | None = None
    try:
        if resume:
            journal, restored = Journal.resume(
                env.workdir, host, resume, stale_s, secrets
            )
            alias = model_override or restored.model
        else:
            alias = model_override or config.default_model
            if record:  # sans fichier avant la 1re demande
                journal = Journal.new(env.workdir, host, alias, stale_s, secrets)
    except JournalError as failure:
        return Refused(str(failure), journal_failure=True)

    def refuse(message: str, journal_failure: bool = False) -> Refused:
        if journal:
            journal.close()
        return Refused(message, journal_failure)

    if alias not in config.models:
        return refuse(
            f"Modèle inconnu : '{alias}'. Modèles disponibles : {', '.join(config.models)}."
        )
    client = client_factory(config.models[alias])
    try:
        await client.check()
    except ProviderError as failure:
        return refuse(failure.message_fr)
    if journal and restored is not None and alias != restored.model:
        try:
            journal.model_changed(alias)  # le modèle demandé devient le modèle actif
        except JournalError as failure:
            return refuse(str(failure), journal_failure=True)
    return Opened(journal, restored, alias, client)


def purge_at_launch(
    config: Config,
    env: Environment,
    notify: Callable[[str], None],
    report: Callable[[str], None],
) -> None:
    """Purge des sessions inactives et des restes d'un arrêt brutal (ADR-0012 §5, ADR-0011 §12).

    À appeler *après* l'ouverture : la session reprise est alors verrouillée, donc épargnée.
    """
    purged, failures = purge_expired(
        env.workdir, config.sessions.retention_days, config.sessions.lock_stale_s
    )
    if purged:
        notify(
            f"{purged} session(s) purgée(s) : sans activité depuis plus de "
            f"{config.sessions.retention_days:g} jours."
        )
    for failure in failures:
        report(failure)
    OutputStore.purge_stale(env.workdir)
