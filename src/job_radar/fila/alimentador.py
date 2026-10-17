"""Move as melhores vagas do pool para a fila de auditoria de cada usuário (RN14-RN15)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from job_radar.fila.estados import transicionar
from job_radar.models import Usuario, Vaga, VagaUsuario
from job_radar.models.enums import OrigemTransicao, StatusVaga

log = logging.getLogger(__name__)

# Abaixo disso a vaga fica no pool: não vale uma chamada de IA (calibrado em 17/10)
SCORE_MINIMO_FILA = 50


def contar_por_status(sessao: Session, usuario: Usuario, status: StatusVaga) -> int:
    return sessao.scalar(
        select(func.count())
        .select_from(VagaUsuario)
        .where(VagaUsuario.usuario_id == usuario.id, VagaUsuario.status == status)
    )


def alimentar_usuario(sessao: Session, usuario: Usuario, agora: datetime) -> int:
    # RN15: com as recomendadas cheias, a auditoria para e a fila não cresce (backpressure)
    if contar_por_status(sessao, usuario, StatusVaga.RECOMENDADA) >= usuario.limite_recomendadas:
        return 0
    vagas_livres = usuario.limite_fila - contar_por_status(sessao, usuario, StatusVaga.FILA)
    if vagas_livres <= 0:
        return 0

    candidatas = sessao.scalars(
        select(VagaUsuario)
        .join(Vaga, Vaga.id == VagaUsuario.vaga_id)
        .where(
            VagaUsuario.usuario_id == usuario.id,
            VagaUsuario.status == StatusVaga.POOL,
            VagaUsuario.score_prefiltro >= SCORE_MINIMO_FILA,
            or_(VagaUsuario.expira_em.is_(None), VagaUsuario.expira_em > agora),
        )
        .order_by(VagaUsuario.score_prefiltro.desc(), Vaga.publicada_em.desc().nulls_last())
        .limit(vagas_livres)
        .with_for_update(of=VagaUsuario, skip_locked=True)
    ).all()

    for vaga_usuario in candidatas:
        transicionar(sessao, vaga_usuario, StatusVaga.FILA, OrigemTransicao.SISTEMA, "alimentador")
        vaga_usuario.expira_em = None  # na fila não há TTL; volta a valer em recomendada
        vaga_usuario.tentativas = 0
        vaga_usuario.proxima_tentativa_em = None
    return len(candidatas)


def alimentar_fila(sessao: Session, agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    usuarios = sessao.scalars(select(Usuario).where(Usuario.ativo)).all()
    total = 0
    for usuario in usuarios:
        movidas = alimentar_usuario(sessao, usuario, agora)
        if movidas:
            log.info("fila alimentada", extra={"usuario": str(usuario.id), "movidas": movidas})
        total += movidas
    sessao.commit()
    return total
