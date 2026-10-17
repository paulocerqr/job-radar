"""Processo `worker`: APScheduler com os jobs da fila (PLANO §8).

Sempre com 1 réplica (D16). Na Fase 0 só registra o heartbeat usado pelo health check.
"""

import logging
import signal
import time
from datetime import UTC, datetime
from datetime import time as Hora
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

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


def dentro_da_janela(agora: Hora, inicio: Hora, fim: Hora) -> bool:
    return inicio <= agora <= fim


def job_coletar(fonte_id: str, settings: Settings) -> None:
    from job_radar.coleta.execucao import executar_coleta
    from job_radar.db import nova_sessao

    agora = datetime.now(ZoneInfo(settings.tz)).time()
    if not dentro_da_janela(agora, settings.coleta_inicio, settings.coleta_fim):
        log.debug("fora da janela de coleta", extra={"fonte": fonte_id})
        return
    with nova_sessao() as sessao:
        executar_coleta(sessao, fonte_id)


def job_alimentar_fila() -> None:
    from job_radar.db import nova_sessao
    from job_radar.fila.alimentador import alimentar_fila

    with nova_sessao() as sessao:
        alimentar_fila(sessao)


def job_expirar() -> None:
    from job_radar.db import nova_sessao
    from job_radar.fila.expirador import expirar

    with nova_sessao() as sessao:
        expirar(sessao)


def registrar_jobs(scheduler: BlockingScheduler, settings: Settings) -> None:
    # PLANO §8: alimentador a cada 10 min, expirador a cada hora, 24h por dia
    for funcao, minutos in ((job_alimentar_fila, 10), (job_expirar, 60)):
        scheduler.add_job(
            funcao,
            "interval",
            minutes=minutos,
            id=funcao.__name__,
            next_run_time=datetime.now(UTC),
            max_instances=1,
            coalesce=True,
        )
    registrar_coletas(scheduler, settings)


def registrar_coletas(scheduler: BlockingScheduler, settings: Settings) -> None:
    if not settings.coleta_no_worker:
        log.info("coleta externa ao worker (CronJob)")
        return

    from job_radar.coleta.base import fontes_registradas
    from job_radar.db import nova_sessao
    from job_radar.models import Fonte

    with nova_sessao() as sessao:
        fontes = sessao.scalars(select(Fonte).where(Fonte.ativa)).all()
    disponiveis = fontes_registradas()
    for fonte in fontes:
        if fonte.id not in disponiveis:
            log.warning("fonte ativa sem coletor implementado", extra={"fonte": fonte.id})
            continue
        # RN01: intervalo próprio por fonte; a janela 08-20h é checada dentro do job
        scheduler.add_job(
            job_coletar,
            "interval",
            minutes=fonte.intervalo_min,
            args=[fonte.id, settings],
            id=f"coletar:{fonte.id}",
            next_run_time=datetime.now(UTC),
            max_instances=1,
            coalesce=True,
        )
        log.info("coleta agendada", extra={"fonte": fonte.id, "intervalo_min": fonte.intervalo_min})


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
