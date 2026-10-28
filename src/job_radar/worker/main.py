"""Processo `worker`: APScheduler com os jobs da fila (PLANO §8).

Sempre com 1 réplica (D16), garantida pela trava no Postgres (`trava.py`).
"""

import logging
import os
import signal
import threading
import time
from datetime import UTC, datetime
from datetime import time as Hora
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from job_radar.config import Settings
from job_radar.worker.trava import TravaWorker

log = logging.getLogger(__name__)

INTERVALO_HEARTBEAT_S = 30
ESPERA_TRAVA_S = 5


def gravar_heartbeat(caminho: Path) -> None:
    caminho.write_text(datetime.now(UTC).isoformat())


def heartbeat_recente(caminho: Path, max_idade_s: int) -> bool:
    try:
        modificado_em = caminho.stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - modificado_em <= max_idade_s


def job_heartbeat(caminho: Path, trava: TravaWorker) -> None:
    """Grava o heartbeat e confere a trava; se outro worker ficou com ela, encerra este."""
    if not trava.mantida():
        log.warning("trava do worker perdida, tentando readquirir")
        try:
            obtida = trava.tentar()
        except Exception:
            # banco fora: nenhum worker consegue trabalhar; tenta de novo no próximo ciclo
            log.error("banco indisponível para readquirir a trava", exc_info=True)
            obtida = True
        if not obtida:
            log.error("outro worker está com a trava: encerrando este")
            os.kill(os.getpid(), signal.SIGTERM)
            return
    gravar_heartbeat(caminho)


def esperar_trava(trava: TravaWorker, caminho: Path, parar: threading.Event) -> bool:
    """Bloqueia até pegar a trava (True) ou até pedirem para encerrar (False)."""
    avisado = False
    while not parar.is_set():
        try:
            if trava.tentar():
                log.info("trava do worker obtida")
                return True
            if not avisado:
                log.info("outro worker está com a trava; aguardando ele encerrar")
                avisado = True
        except Exception:
            log.error("banco indisponível ao pegar a trava do worker", exc_info=True)
        # a liveness olha o heartbeat: esperar a trava não é estar travado
        gravar_heartbeat(caminho)
        parar.wait(ESPERA_TRAVA_S)
    return False


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


def job_auditar() -> None:
    from job_radar.auditoria.auditor import auditar
    from job_radar.auditoria.testes_cli import executar_teste_pendente
    from job_radar.db import nova_sessao

    with nova_sessao() as sessao:
        # Serializa CLI de teste e auditoria para caber no limite de memória do worker.
        executar_teste_pendente(sessao)
        auditar(sessao)


def job_expirar() -> None:
    from job_radar.db import nova_sessao
    from job_radar.fila.expirador import expirar

    with nova_sessao() as sessao:
        expirar(sessao)


def registrar_jobs(scheduler: BlockingScheduler, settings: Settings) -> None:
    # PLANO §8: auditor a cada minuto, alimentador a cada 10 min, expirador a cada hora
    for funcao, minutos in ((job_auditar, 1), (job_alimentar_fila, 10), (job_expirar, 60)):
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


def job_notificar(cliente) -> None:
    from job_radar.db import nova_sessao
    from job_radar.notificacao.notificador import notificar

    with nova_sessao() as sessao:
        notificar(sessao, cliente)


def job_resumo(cliente, settings: Settings) -> None:
    from job_radar.db import nova_sessao
    from job_radar.notificacao.notificador import enviar_resumos

    with nova_sessao() as sessao:
        enviar_resumos(sessao, cliente, settings.tz)


def registrar_telegram(scheduler: BlockingScheduler, settings: Settings):
    """Retorna o polling (para encerrar no shutdown) ou None se o bot não estiver configurado."""
    if settings.telegram_bot_token is None:
        log.info("TELEGRAM_BOT_TOKEN ausente: notificações desligadas")
        return None

    from job_radar.notificacao.bot import PollingTelegram
    from job_radar.notificacao.telegram import ClienteTelegram

    cliente = ClienteTelegram(settings.telegram_bot_token.get_secret_value())
    scheduler.add_job(
        job_notificar,
        "interval",
        minutes=1,
        args=[cliente],
        id="notificar",
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    # RN29
    scheduler.add_job(
        job_resumo,
        "cron",
        hour=settings.resumo_diario.hour,
        minute=settings.resumo_diario.minute,
        args=[cliente, settings],
        id="resumo_diario",
    )
    polling = PollingTelegram(cliente)
    polling.iniciar()
    return polling


def executar(settings: Settings) -> None:
    from job_radar.db import get_engine

    trava = TravaWorker(get_engine())
    encerrando = threading.Event()
    scheduler = BlockingScheduler(timezone=settings.tz)
    polling = None

    def parar(signum: int, _frame: object) -> None:
        log.info("sinal recebido, encerrando", extra={"sinal": signal.Signals(signum).name})
        encerrando.set()
        if polling is not None:
            polling.parar()
        if scheduler.running:
            # wait=True deixa os jobs em andamento terminarem (RNF12)
            scheduler.shutdown(wait=True)

    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)

    if not esperar_trava(trava, settings.worker_heartbeat_path, encerrando):
        log.info("worker encerrado antes de obter a trava")
        return

    scheduler.add_job(
        job_heartbeat,
        "interval",
        seconds=INTERVALO_HEARTBEAT_S,
        args=[settings.worker_heartbeat_path, trava],
        id="heartbeat",
        next_run_time=datetime.now(UTC),
    )
    registrar_jobs(scheduler, settings)
    polling = registrar_telegram(scheduler, settings)

    log.info("worker iniciado", extra={"coleta_no_worker": settings.coleta_no_worker})
    try:
        scheduler.start()
    finally:
        trava.liberar()
    log.info("worker encerrado")
