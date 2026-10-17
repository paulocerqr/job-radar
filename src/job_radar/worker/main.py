"""Processo `worker`: APScheduler com os jobs da fila (PLANO §8).

Sempre com 1 réplica (D16). Na Fase 0 só registra o heartbeat usado pelo health check.
"""

import logging
import signal
import time
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from job_radar.config import Settings

log = logging.getLogger(__name__)

INTERVALO_HEARTBEAT_S = 30


def gravar_heartbeat(caminho: Path) -> None:
    caminho.write_text(datetime.now(UTC).isoformat())


def heartbeat_recente(caminho: Path, max_idade_s: int) -> bool:
    try:
        modificado_em = caminho.stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - modificado_em <= max_idade_s


def registrar_jobs(scheduler: BlockingScheduler, settings: Settings) -> None:
    if settings.coleta_no_worker:
        log.info("coleta agendada no worker; nenhum coletor registrado ainda")
    else:
        log.info("coleta externa ao worker (CronJob)")


def executar(settings: Settings) -> None:
    scheduler = BlockingScheduler(timezone=settings.tz)
    scheduler.add_job(
        gravar_heartbeat,
        "interval",
        seconds=INTERVALO_HEARTBEAT_S,
        args=[settings.worker_heartbeat_path],
        id="heartbeat",
        next_run_time=datetime.now(UTC),
    )
    registrar_jobs(scheduler, settings)

    def parar(signum: int, _frame: object) -> None:
        log.info("sinal recebido, encerrando", extra={"sinal": signal.Signals(signum).name})
        # wait=True deixa os jobs em andamento terminarem (RNF12)
        scheduler.shutdown(wait=True)

    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)

    log.info("worker iniciado", extra={"coleta_no_worker": settings.coleta_no_worker})
    scheduler.start()
    log.info("worker encerrado")
