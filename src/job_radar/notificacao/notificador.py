"""Envio das recomendações (RN28), alerta de capacidade (RN25) e resumo diário (RN29).

`vaga_usuario.notificado_em` funciona como outbox: só é preenchido depois que o Telegram
confirma o envio. Se o envio falhar, a próxima rodada tenta de novo.
"""

import logging
import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_radar.fila.alimentador import contar_por_status
from job_radar.models import (
    Auditoria,
    CanalNotificacao,
    HistoricoStatus,
    Usuario,
    Vaga,
    VagaUsuario,
)
from job_radar.models.enums import StatusVaga, TipoCanal
from job_radar.notificacao.mensagens import botoes_recomendacao, texto_recomendacao
from job_radar.notificacao.telegram import ClienteTelegram, ErroTelegram

log = logging.getLogger(__name__)

LIMIAR_CAPACIDADE = 0.8
MAXIMO_POR_RODADA = 20


def canal_telegram(sessao: Session, usuario_id) -> CanalNotificacao | None:
    return sessao.scalar(
        select(CanalNotificacao).where(
            CanalNotificacao.usuario_id == usuario_id,
            CanalNotificacao.tipo == TipoCanal.TELEGRAM,
            CanalNotificacao.ativo,
            CanalNotificacao.verificado,
            CanalNotificacao.destino.is_not(None),
        )
    )


def ultima_auditoria(sessao: Session, vaga_usuario_id) -> dict | None:
    return sessao.scalar(
        select(Auditoria.resultado)
        .where(Auditoria.vaga_usuario_id == vaga_usuario_id, Auditoria.sucesso)
        .order_by(Auditoria.criado_em.desc())
        .limit(1)
    )


def _limiar(usuario: Usuario) -> int:
    return math.ceil(usuario.limite_recomendadas * LIMIAR_CAPACIDADE)


def notificar(sessao: Session, cliente: ClienteTelegram, agora: datetime | None = None) -> int:
    agora = agora or datetime.now(UTC)
    pendentes = sessao.execute(
        select(VagaUsuario, Vaga, CanalNotificacao)
        .join(Vaga, Vaga.id == VagaUsuario.vaga_id)
        .join(
            CanalNotificacao,
            (CanalNotificacao.usuario_id == VagaUsuario.usuario_id)
            & (CanalNotificacao.tipo == TipoCanal.TELEGRAM),
        )
        .where(
            VagaUsuario.status == StatusVaga.RECOMENDADA,
            VagaUsuario.notificado_em.is_(None),
            CanalNotificacao.ativo,
            CanalNotificacao.verificado,
            CanalNotificacao.destino.is_not(None),
        )
        .order_by(VagaUsuario.status_em)
        .limit(MAXIMO_POR_RODADA)
    ).all()

    enviadas_por_usuario: dict = {}
    for vaga_usuario, vaga, canal in pendentes:
        texto = texto_recomendacao(vaga, ultima_auditoria(sessao, vaga_usuario.id))
        try:
            cliente.enviar_mensagem(
                int(canal.destino), texto, botoes_recomendacao(vaga_usuario.id, vaga.url_canonica)
            )
        except ErroTelegram as erro:
            log.warning("falha ao enviar recomendação", extra={"erro": str(erro)})
            continue
        vaga_usuario.notificado_em = agora
        sessao.commit()
        enviadas_por_usuario.setdefault(canal, 0)
        enviadas_por_usuario[canal] += 1

    for canal, enviadas in enviadas_por_usuario.items():
        _alertar_capacidade(sessao, cliente, canal, enviadas)
    return sum(enviadas_por_usuario.values())


def _alertar_capacidade(
    sessao: Session, cliente: ClienteTelegram, canal: CanalNotificacao, enviadas: int
) -> None:
    """RN25: avisa uma vez, quando esta rodada fez as recomendadas cruzarem 80%."""
    usuario = sessao.get_one(Usuario, canal.usuario_id)
    atual = contar_por_status(sessao, usuario, StatusVaga.RECOMENDADA)
    limiar = _limiar(usuario)
    if atual >= limiar > atual - enviadas:
        texto = (
            f"📦 Recomendadas em {atual}/{usuario.limite_recomendadas}."
            " Ao chegar no limite a auditoria pausa: confirme ou ignore algumas vagas."
        )
        try:
            cliente.enviar_mensagem(int(canal.destino), texto)
        except ErroTelegram as erro:
            log.warning("falha ao enviar alerta de capacidade", extra={"erro": str(erro)})


def texto_resumo(sessao: Session, usuario: Usuario, desde: datetime) -> str:
    def transicoes_para(status: StatusVaga) -> int:
        return sessao.scalar(
            select(func.count())
            .select_from(HistoricoStatus)
            .join(VagaUsuario, VagaUsuario.id == HistoricoStatus.vaga_usuario_id)
            .where(
                VagaUsuario.usuario_id == usuario.id,
                HistoricoStatus.para == status,
                HistoricoStatus.criado_em >= desde,
            )
        )

    pendentes = contar_por_status(sessao, usuario, StatusVaga.RECOMENDADA)
    return "\n".join(
        [
            "🗓 <b>Resumo do dia</b>",
            f"Recomendadas hoje: {transicoes_para(StatusVaga.RECOMENDADA)}",
            f"Descartadas pela IA hoje: {transicoes_para(StatusVaga.DESCARTADA)}",
            f"Confirmadas hoje: {transicoes_para(StatusVaga.CONFIRMADA)}",
            f"Aguardando você: {pendentes}/{usuario.limite_recomendadas}",
            f"Na fila de auditoria: {contar_por_status(sessao, usuario, StatusVaga.FILA)}",
        ]
    )


def enviar_resumos(
    sessao: Session, cliente: ClienteTelegram, fuso: str, agora: datetime | None = None
) -> int:
    agora = (agora or datetime.now(UTC)).astimezone(ZoneInfo(fuso))
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    enviados = 0
    for usuario in sessao.scalars(select(Usuario).where(Usuario.ativo)).all():
        canal = canal_telegram(sessao, usuario.id)
        if canal is None:
            continue
        try:
            cliente.enviar_mensagem(
                int(canal.destino), texto_resumo(sessao, usuario, inicio_do_dia)
            )
            enviados += 1
        except ErroTelegram as erro:
            log.warning("falha ao enviar resumo", extra={"erro": str(erro)})
    return enviados
