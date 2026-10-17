"""Ponto de entrada único da imagem: `job-radar <comando>` (PLANO §3.2)."""

import logging

import typer

from job_radar.config import get_settings
from job_radar.logs import configurar_logs

app = typer.Typer(help="Job Radar", no_args_is_help=True, add_completion=False)
log = logging.getLogger("job_radar.cli")


@app.callback()
def _inicializar() -> None:
    settings = get_settings()
    configurar_logs(settings.log_format, settings.log_level)


@app.command()
def api() -> None:
    """Sobe a API/UI (FastAPI)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "job_radar.web.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # usa o logging já configurado (JSON em stdout)
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


@app.command()
def worker() -> None:
    """Sobe o scheduler (sempre 1 réplica)."""
    from job_radar.worker.main import executar

    executar(get_settings())


@app.command("worker-saude")
def worker_saude() -> None:
    """Sai com 0 se o heartbeat do worker for recente (exec probe / healthcheck)."""
    from job_radar.worker.main import heartbeat_recente

    settings = get_settings()
    if not heartbeat_recente(settings.worker_heartbeat_path, settings.worker_heartbeat_max_idade_s):
        raise typer.Exit(1)


@app.command()
def migrar(revisao: str = typer.Argument("head")) -> None:
    """Aplica as migrations e sai (Job/initContainer, RNF11)."""
    from alembic import command

    from job_radar.db import alembic_config

    command.upgrade(alembic_config(), revisao)
    log.info("migrations aplicadas", extra={"revisao": revisao})


@app.command()
def seed() -> None:
    """Cria fontes e o usuário admin (idempotente)."""
    from job_radar.db import nova_sessao
    from job_radar.seed import ConfiguracaoSeedInvalida, executar_seed

    with nova_sessao() as sessao:
        try:
            resumo = executar_seed(sessao, get_settings())
        except ConfiguracaoSeedInvalida as erro:
            log.error(str(erro))
            raise typer.Exit(2) from None
    log.info(
        "seed concluído",
        extra={"fontes_criadas": resumo.fontes_criadas, "admin_criado": resumo.admin_criado},
    )


@app.command()
def alimentar() -> None:
    """Move as melhores vagas do pool para a fila (o worker faz isso a cada 10 min)."""
    from job_radar.db import nova_sessao
    from job_radar.fila.alimentador import alimentar_fila

    with nova_sessao() as sessao:
        log.info("fila alimentada", extra={"movidas": alimentar_fila(sessao)})


@app.command()
def expirar() -> None:
    """Expira vagas além do TTL no pool e nas recomendadas (o worker faz isso a cada hora)."""
    from job_radar.db import nova_sessao
    from job_radar.fila.expirador import expirar as expirar_vagas

    with nova_sessao() as sessao:
        log.info("expiração concluída", extra={"expiradas": expirar_vagas(sessao)})


@app.command()
def coletar(fonte: str) -> None:
    """Executa uma coleta da fonte e sai (CronJob no Kubernetes, D17)."""
    from job_radar.coleta.base import fontes_registradas
    from job_radar.coleta.execucao import FonteNaoCadastrada, executar_coleta
    from job_radar.db import nova_sessao
    from job_radar.models.enums import StatusExecucao

    disponiveis = fontes_registradas()
    if fonte not in disponiveis:
        log.error("fonte desconhecida", extra={"fonte": fonte, "disponiveis": disponiveis})
        raise typer.Exit(2)
    with nova_sessao() as sessao:
        try:
            execucao = executar_coleta(sessao, fonte)
        except FonteNaoCadastrada:
            log.error("fonte sem cadastro no banco; rode `job-radar seed`", extra={"fonte": fonte})
            raise typer.Exit(2) from None
    if execucao.status == StatusExecucao.ERRO:
        raise typer.Exit(1)
