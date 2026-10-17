"""Uma execução de coleta: busca → normaliza → deduplica → pré-filtra por usuário → pool."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from job_radar.coleta.base import obter_coletor
from job_radar.coleta.dedupe import registrar_vaga
from job_radar.coleta.http import novo_cliente
from job_radar.coleta.normalizador import normalizar
from job_radar.fila.estados import criar_no_pool
from job_radar.filtro.prefiltro import avaliar
from job_radar.models import ExecucaoColeta, Fonte, Usuario, Vaga
from job_radar.models.enums import StatusExecucao

log = logging.getLogger(__name__)


class FonteNaoCadastrada(Exception):
    pass


def distribuir(
    sessao: Session,
    vaga: Vaga,
    usuarios: Sequence[Usuario],
    confiabilidade_fonte: int,
    agora: datetime,
) -> int:
    """Cria `vaga_usuario` em `pool` para cada usuário cujo pré-filtro aprova a vaga."""
    aprovadas = 0
    for usuario in usuarios:
        if usuario.perfil is None:
            continue
        resultado = avaliar(vaga, usuario.perfil, confiabilidade_fonte, agora)
        if not resultado.aprovada:
            log.debug(
                "pré-filtro reprovou", extra={"vaga": vaga.titulo, "motivo": resultado.motivo}
            )
            continue
        criar_no_pool(
            sessao,
            vaga_id=vaga.id,
            usuario_id=usuario.id,
            score_prefiltro=resultado.score,
            expira_em=agora + timedelta(days=usuario.perfil.ttl_pool_dias),
        )
        aprovadas += 1
    return aprovadas


def executar_coleta(
    sessao: Session,
    fonte_id: str,
    http: httpx.Client | None = None,
    agora: datetime | None = None,
) -> ExecucaoColeta:
    fonte = sessao.get(Fonte, fonte_id)
    if fonte is None:
        raise FonteNaoCadastrada(fonte_id)
    agora = agora or datetime.now(UTC)

    execucao = ExecucaoColeta(fonte_id=fonte_id, status=StatusExecucao.RODANDO)
    sessao.add(execucao)
    sessao.commit()

    usuarios = sessao.scalars(
        select(Usuario).where(Usuario.ativo).options(selectinload(Usuario.perfil))
    ).all()

    falhas = 0
    no_pool = 0
    cliente = http or novo_cliente()
    try:
        brutas = obter_coletor(fonte_id, cliente).buscar(fonte.config, fonte.max_itens_execucao)
        for bruta in brutas:
            try:
                with sessao.begin_nested():
                    vaga, nova = registrar_vaga(sessao, normalizar(bruta))
                    if nova:
                        no_pool += distribuir(sessao, vaga, usuarios, fonte.confiabilidade, agora)
            except Exception:
                falhas += 1
                log.exception("falha ao processar vaga", extra={"id_externo": bruta.id_externo})
                continue
            execucao.itens_coletados += 1
            if nova:
                execucao.itens_novos += 1
            else:
                execucao.itens_duplicados += 1
        execucao.status = StatusExecucao.PARCIAL if falhas else StatusExecucao.OK
    except Exception as erro:
        sessao.rollback()
        execucao.status = StatusExecucao.ERRO
        execucao.erro = repr(erro)
        log.exception("coleta falhou", extra={"fonte": fonte_id})
    finally:
        if http is None:
            cliente.close()

    execucao.finalizada_em = datetime.now(UTC)
    fonte.ultima_execucao_em = execucao.finalizada_em
    sessao.commit()
    log.info(
        "coleta finalizada",
        extra={
            "fonte": fonte_id,
            "status": execucao.status,
            "coletados": execucao.itens_coletados,
            "novos": execucao.itens_novos,
            "duplicados": execucao.itens_duplicados,
            "no_pool": no_pool,
            "falhas": falhas,
        },
    )
    return execucao
