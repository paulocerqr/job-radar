"""Expira vagas paradas no pool ou nas recomendadas além do TTL (RN13, RN23)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_radar.fila.estados import transicionar
from job_radar.models import VagaUsuario
from job_radar.models.enums import OrigemTransicao, StatusVaga

log = logging.getLogger(__name__)

_COM_TTL = (StatusVaga.POOL, StatusVaga.RECOMENDADA)


def expirar(sessao: Session, agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    vencidas = sessao.scalars(
        select(VagaUsuario)
        .where(VagaUsuario.status.in_(_COM_TTL), VagaUsuario.expira_em <= agora)
        .with_for_update(skip_locked=True)
    ).all()
    for vaga_usuario in vencidas:
        detalhe = f"TTL vencido em {vaga_usuario.status}"
        transicionar(sessao, vaga_usuario, StatusVaga.EXPIRADA, OrigemTransicao.SISTEMA, detalhe)
    sessao.commit()
    if vencidas:
        log.info("vagas expiradas", extra={"quantidade": len(vencidas)})
    return len(vencidas)
