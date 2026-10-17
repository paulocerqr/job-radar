"""Máquina de estados de `vaga_usuario` (PLANO §4.1). Toda transição gera histórico."""

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from job_radar.models import HistoricoStatus, VagaUsuario
from job_radar.models.enums import OrigemTransicao, StatusVaga

TRANSICOES: dict[StatusVaga, frozenset[StatusVaga]] = {
    StatusVaga.POOL: frozenset({StatusVaga.FILA, StatusVaga.EXPIRADA}),
    StatusVaga.FILA: frozenset(
        {StatusVaga.RECOMENDADA, StatusVaga.DESCARTADA, StatusVaga.ERRO, StatusVaga.POOL}
    ),
    StatusVaga.RECOMENDADA: frozenset(
        {StatusVaga.CONFIRMADA, StatusVaga.IGNORADA, StatusVaga.EXPIRADA}
    ),
    StatusVaga.ERRO: frozenset({StatusVaga.FILA}),
    StatusVaga.CONFIRMADA: frozenset(),
    StatusVaga.DESCARTADA: frozenset(),
    StatusVaga.IGNORADA: frozenset(),
    StatusVaga.EXPIRADA: frozenset(),
}


class TransicaoInvalida(Exception):
    pass


def criar_no_pool(
    sessao: Session,
    vaga_id: uuid.UUID,
    usuario_id: uuid.UUID,
    score_prefiltro: int,
    expira_em: datetime,
) -> VagaUsuario:
    vaga_usuario = VagaUsuario(
        vaga_id=vaga_id,
        usuario_id=usuario_id,
        status=StatusVaga.POOL,
        score_prefiltro=score_prefiltro,
        expira_em=expira_em,
    )
    sessao.add(vaga_usuario)
    sessao.flush()
    sessao.add(
        HistoricoStatus(
            vaga_usuario_id=vaga_usuario.id,
            de=None,
            para=StatusVaga.POOL,
            origem=OrigemTransicao.SISTEMA,
            detalhe=f"pré-filtro: score {score_prefiltro}",
        )
    )
    return vaga_usuario


def transicionar(
    sessao: Session,
    vaga_usuario: VagaUsuario,
    para: StatusVaga,
    origem: OrigemTransicao,
    detalhe: str | None = None,
) -> None:
    de = StatusVaga(vaga_usuario.status)
    if para not in TRANSICOES[de]:
        raise TransicaoInvalida(f"{de} → {para}")
    vaga_usuario.status = para
    vaga_usuario.status_em = func.now()
    sessao.add(
        HistoricoStatus(
            vaga_usuario_id=vaga_usuario.id, de=de, para=para, origem=origem, detalhe=detalhe
        )
    )
