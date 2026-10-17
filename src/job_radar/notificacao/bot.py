"""Atualizações recebidas do Telegram: vínculo via /start e botões das recomendações (RN26).

Recebidas por long polling (`getUpdates`): não precisa de URL pública nem de webhook, e
funciona igual no PC, no cluster e na EC2. Só um processo pode fazer polling por bot,
o que casa com o worker de réplica única (D16).
"""

import logging
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_radar.db import nova_sessao
from job_radar.fila.alimentador import contar_por_status
from job_radar.fila.estados import transicionar
from job_radar.models import CanalNotificacao, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import OrigemTransicao, StatusVaga, TipoCanal
from job_radar.notificacao.mensagens import (
    MOTIVOS_IGNORAR,
    botao_abrir,
    botoes_motivo,
    texto_recomendacao,
)
from job_radar.notificacao.notificador import ultima_auditoria
from job_radar.notificacao.telegram import ClienteTelegram, ErroTelegram

log = logging.getLogger(__name__)

AJUDA = (
    "Olá! Eu sou o bot do Job Radar.\n"
    "Para vincular este chat, gere um link com <code>job-radar telegram vincular</code>.\n"
    "/status mostra quantas vagas aguardam você."
)


def processar_updates(sessao: Session, cliente: ClienteTelegram, updates: list[dict]) -> None:
    for update in updates:
        try:
            if "callback_query" in update:
                tratar_callback(sessao, cliente, update["callback_query"])
            elif "message" in update:
                tratar_mensagem(sessao, cliente, update["message"])
        except Exception:
            sessao.rollback()
            log.exception("falha ao processar update", extra={"update_id": update.get("update_id")})


def tratar_mensagem(sessao: Session, cliente: ClienteTelegram, mensagem: dict) -> None:
    chat_id = mensagem["chat"]["id"]
    texto = (mensagem.get("text") or "").strip()
    comando, _, argumento = texto.partition(" ")

    if comando == "/start" and argumento:
        canal = sessao.scalar(
            select(CanalNotificacao).where(
                CanalNotificacao.tipo == TipoCanal.TELEGRAM,
                CanalNotificacao.token_vinculo == argumento.strip(),
            )
        )
        if canal is None:
            cliente.enviar_mensagem(chat_id, "Link de vínculo inválido ou já usado.")
            return
        canal.destino = str(chat_id)
        canal.verificado = True
        canal.token_vinculo = None  # uso único
        sessao.commit()
        cliente.enviar_mensagem(
            chat_id, "✅ Chat vinculado ao Job Radar. As vagas recomendadas vão chegar aqui."
        )
        return

    if comando == "/status":
        canal = sessao.scalar(
            select(CanalNotificacao).where(
                CanalNotificacao.tipo == TipoCanal.TELEGRAM,
                CanalNotificacao.destino == str(chat_id),
                CanalNotificacao.verificado,
            )
        )
        if canal is None:
            cliente.enviar_mensagem(chat_id, AJUDA)
            return
        usuario = sessao.get_one(Usuario, canal.usuario_id)
        pendentes = contar_por_status(sessao, usuario, StatusVaga.RECOMENDADA)
        fila = contar_por_status(sessao, usuario, StatusVaga.FILA)
        cliente.enviar_mensagem(
            chat_id,
            f"Aguardando você: {pendentes}/{usuario.limite_recomendadas}\n"
            f"Na fila de auditoria: {fila}",
        )
        return

    cliente.enviar_mensagem(chat_id, AJUDA)


def tratar_callback(sessao: Session, cliente: ClienteTelegram, callback: dict) -> None:
    acao, _, resto = (callback.get("data") or "").partition(":")
    id_texto, _, codigo_motivo = resto.partition(":")
    mensagem = callback.get("message") or {}
    chat_id = (mensagem.get("chat") or {}).get("id")

    try:
        vaga_usuario = sessao.get(VagaUsuario, uuid.UUID(id_texto))
    except ValueError:
        vaga_usuario = None
    if vaga_usuario is None or chat_id is None:
        cliente.responder_callback(callback["id"], "Vaga não encontrada.")
        return

    # Só o dono da vaga, no chat vinculado, pode decidir sobre ela
    canal = sessao.scalar(
        select(CanalNotificacao).where(
            CanalNotificacao.usuario_id == vaga_usuario.usuario_id,
            CanalNotificacao.tipo == TipoCanal.TELEGRAM,
            CanalNotificacao.verificado,
        )
    )
    if canal is None or canal.destino != str(chat_id):
        cliente.responder_callback(callback["id"], "Não autorizado.")
        return

    vaga = sessao.get_one(Vaga, vaga_usuario.vaga_id)
    auditoria = ultima_auditoria(sessao, vaga_usuario.id)

    def editar(rodape: str, botoes) -> None:
        try:
            cliente.editar_mensagem(
                chat_id, mensagem["message_id"], texto_recomendacao(vaga, auditoria, rodape), botoes
            )
        except ErroTelegram as erro:  # ex.: mensagem antiga demais para editar
            log.warning("não foi possível editar a mensagem", extra={"erro": str(erro)})

    if acao in ("c", "i") and vaga_usuario.status != StatusVaga.RECOMENDADA:
        cliente.responder_callback(callback["id"], f"Essa vaga já está: {vaga_usuario.status}.")
        editar(f"📌 Situação: <b>{vaga_usuario.status}</b>", [botao_abrir(vaga.url_canonica)])
        return

    if acao == "c":
        transicionar(
            sessao, vaga_usuario, StatusVaga.CONFIRMADA, OrigemTransicao.USUARIO, "telegram"
        )
        sessao.commit()
        cliente.responder_callback(callback["id"], "Confirmada. Boa sorte!")
        editar("✅ <b>Confirmada</b>: boa sorte na candidatura!", [botao_abrir(vaga.url_canonica)])
    elif acao == "i":
        transicionar(sessao, vaga_usuario, StatusVaga.IGNORADA, OrigemTransicao.USUARIO, "telegram")
        sessao.commit()
        cliente.responder_callback(callback["id"], "Ignorada.")
        editar(
            "❌ <b>Ignorada.</b> Quer dizer o motivo? (opcional)",
            botoes_motivo(vaga_usuario.id, vaga.url_canonica),
        )
    elif acao == "m" and codigo_motivo in MOTIVOS_IGNORAR:
        if vaga_usuario.status != StatusVaga.IGNORADA:
            cliente.responder_callback(callback["id"], "Essa vaga não está ignorada.")
            return
        vaga_usuario.motivo_usuario = codigo_motivo
        sessao.commit()
        cliente.responder_callback(callback["id"], "Obrigado, motivo registrado.")
        editar(
            f"❌ <b>Ignorada</b> · motivo: {MOTIVOS_IGNORAR[codigo_motivo]}",
            [botao_abrir(vaga.url_canonica)],
        )
    else:
        cliente.responder_callback(callback["id"], "Ação desconhecida.")


class PollingTelegram:
    """Long polling numa thread própria do worker; para quando `parar()` é chamado."""

    def __init__(self, cliente: ClienteTelegram, timeout_s: int = 20) -> None:
        self.cliente = cliente
        self.timeout_s = timeout_s
        self.offset: int | None = None
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="telegram-polling", daemon=True)

    def iniciar(self) -> None:
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        self._thread.join(timeout=self.timeout_s + 5)

    def rodar_uma_vez(self) -> int:
        updates = self.cliente.obter_updates(self.offset, self.timeout_s)
        if updates:
            # confirmar o offset antes de processar evita reprocessar em loop um update
            # que sempre falha; o erro fica no log
            self.offset = updates[-1]["update_id"] + 1
            with nova_sessao() as sessao:
                processar_updates(sessao, self.cliente, updates)
        return len(updates)

    def _loop(self) -> None:
        log.info("polling do Telegram iniciado")
        while not self._parar.is_set():
            try:
                self.rodar_uma_vez()
            except ErroTelegram as erro:
                log.warning("polling do Telegram falhou", extra={"erro": str(erro)})
                self._parar.wait(10)
            except Exception:
                log.exception("erro inesperado no polling do Telegram")
                self._parar.wait(10)
        log.info("polling do Telegram encerrado")
