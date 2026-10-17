import itertools
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from job_radar.db import nova_sessao
from job_radar.models import Auditoria, CanalNotificacao, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import StatusVaga, TipoCanal
from job_radar.notificacao.bot import processar_updates
from job_radar.notificacao.notificador import enviar_resumos, notificar, texto_resumo
from job_radar.notificacao.telegram import ErroTelegram

AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)
CHAT = 555
_sequencia = itertools.count()


class TelegramFalso:
    def __init__(self, falhar: bool = False):
        self.falhar = falhar
        self.enviadas: list[tuple[int, str, object]] = []
        self.editadas: list[tuple[int, int, str, object]] = []
        self.respostas: list[tuple[str, str | None]] = []

    def enviar_mensagem(self, chat_id, texto, botoes=None):
        if self.falhar:
            raise ErroTelegram("sendMessage: falha simulada")
        self.enviadas.append((chat_id, texto, botoes))
        return {"message_id": len(self.enviadas)}

    def editar_mensagem(self, chat_id, message_id, texto, botoes=None):
        self.editadas.append((chat_id, message_id, texto, botoes))

    def responder_callback(self, callback_id, texto=None):
        self.respostas.append((callback_id, texto))


@pytest.fixture
def sessao(banco_com_seed):
    with nova_sessao() as sessao:
        yield sessao


@pytest.fixture
def admin(sessao) -> Usuario:
    return sessao.scalar(select(Usuario))


@pytest.fixture
def vinculado(sessao, admin) -> CanalNotificacao:
    canal = CanalNotificacao(
        usuario_id=admin.id, tipo=TipoCanal.TELEGRAM, destino=str(CHAT), verificado=True
    )
    sessao.add(canal)
    sessao.commit()
    return canal


def recomendada(sessao, usuario, status=StatusVaga.RECOMENDADA) -> VagaUsuario:
    n = next(_sequencia)
    vaga = Vaga(hash_dedupe=f"n-{n}", titulo=f"Estágio {n}", url_canonica=f"https://x.io/{n}")
    sessao.add(vaga)
    sessao.flush()
    vu = VagaUsuario(vaga_id=vaga.id, usuario_id=usuario.id, status=status, score_prefiltro=70)
    sessao.add(vu)
    sessao.flush()
    sessao.add(
        Auditoria(
            vaga_usuario_id=vu.id,
            modelo="fake",
            versao_prompt="v1",
            sucesso=True,
            resultado={"score": 81, "area": "devops", "resumo": "boa", "gaps": ["k8s"]},
        )
    )
    sessao.commit()
    return vu


def callback(dados: str, chat_id: int = CHAT) -> dict:
    return {
        "update_id": 1,
        "callback_query": {
            "id": "cb1",
            "data": dados,
            "message": {"message_id": 10, "chat": {"id": chat_id}},
        },
    }


# ---------- vínculo


def test_start_com_token_vincula_o_chat(sessao, admin):
    sessao.add(CanalNotificacao(usuario_id=admin.id, tipo=TipoCanal.TELEGRAM, token_vinculo="abc"))
    sessao.commit()
    telegram = TelegramFalso()

    processar_updates(
        sessao,
        telegram,
        [{"update_id": 1, "message": {"chat": {"id": CHAT}, "text": "/start abc"}}],
    )

    canal = sessao.scalar(select(CanalNotificacao))
    assert (canal.destino, canal.verificado, canal.token_vinculo) == (str(CHAT), True, None)
    assert "vinculado" in telegram.enviadas[0][1]


def test_start_com_token_invalido(sessao, admin):
    telegram = TelegramFalso()
    processar_updates(
        sessao, telegram, [{"update_id": 1, "message": {"chat": {"id": 1}, "text": "/start xyz"}}]
    )
    assert "inválido" in telegram.enviadas[0][1]


# ---------- envio


def test_notifica_recomendadas_uma_vez(sessao, admin, vinculado):
    vu = recomendada(sessao, admin)
    recomendada(sessao, admin, status=StatusVaga.FILA)  # não é recomendada: não envia
    telegram = TelegramFalso()

    assert notificar(sessao, telegram, AGORA) == 1
    assert notificar(sessao, telegram, AGORA) == 0

    (chat_id, texto, botoes) = telegram.enviadas[0]
    assert chat_id == CHAT
    assert "Score 81" in texto
    assert botoes[0][0]["callback_data"] == f"c:{vu.id}"
    sessao.refresh(vu)
    assert vu.notificado_em == AGORA


def test_sem_canal_vinculado_nao_envia(sessao, admin):
    recomendada(sessao, admin)
    telegram = TelegramFalso()
    assert notificar(sessao, telegram, AGORA) == 0
    assert telegram.enviadas == []


def test_falha_no_envio_tenta_de_novo_depois(sessao, admin, vinculado):
    vu = recomendada(sessao, admin)
    assert notificar(sessao, TelegramFalso(falhar=True), AGORA) == 0
    sessao.refresh(vu)
    assert vu.notificado_em is None
    assert notificar(sessao, TelegramFalso(), AGORA) == 1


def test_alerta_ao_cruzar_80_por_cento(sessao, admin, vinculado):
    admin.limite_recomendadas = 5  # limiar = 4
    sessao.commit()
    for _ in range(3):
        recomendada(sessao, admin)
    telegram = TelegramFalso()
    notificar(sessao, telegram, AGORA)
    assert not any("📦" in texto for _, texto, _ in telegram.enviadas)

    recomendada(sessao, admin)
    notificar(sessao, telegram, AGORA)
    assert any("4/5" in texto for _, texto, _ in telegram.enviadas)


# ---------- botões


def test_confirmar(sessao, admin, vinculado):
    vu = recomendada(sessao, admin)
    telegram = TelegramFalso()

    processar_updates(sessao, telegram, [callback(f"c:{vu.id}")])

    sessao.refresh(vu)
    assert vu.status == StatusVaga.CONFIRMADA
    assert "Confirmada" in telegram.editadas[0][2]


def test_ignorar_e_informar_motivo(sessao, admin, vinculado):
    vu = recomendada(sessao, admin)
    telegram = TelegramFalso()

    processar_updates(sessao, telegram, [callback(f"i:{vu.id}")])
    sessao.refresh(vu)
    assert vu.status == StatusVaga.IGNORADA
    botoes_motivo = telegram.editadas[-1][3]
    assert botoes_motivo[0][0]["callback_data"] == f"m:{vu.id}:nivel"

    processar_updates(sessao, telegram, [callback(f"m:{vu.id}:stack")])
    sessao.refresh(vu)
    assert vu.motivo_usuario == "stack"
    assert "stack" in telegram.editadas[-1][2]


def test_outro_chat_nao_pode_decidir(sessao, admin, vinculado):
    vu = recomendada(sessao, admin)
    telegram = TelegramFalso()

    processar_updates(sessao, telegram, [callback(f"c:{vu.id}", chat_id=999)])

    sessao.refresh(vu)
    assert vu.status == StatusVaga.RECOMENDADA
    assert telegram.respostas == [("cb1", "Não autorizado.")]


def test_botao_de_vaga_ja_tratada(sessao, admin, vinculado):
    vu = recomendada(sessao, admin, status=StatusVaga.EXPIRADA)
    telegram = TelegramFalso()

    processar_updates(sessao, telegram, [callback(f"c:{vu.id}")])

    sessao.refresh(vu)
    assert vu.status == StatusVaga.EXPIRADA
    assert "expirada" in telegram.respostas[0][1]


def test_callback_com_id_invalido(sessao, admin, vinculado):
    telegram = TelegramFalso()
    processar_updates(sessao, telegram, [callback("c:nao-e-uuid")])
    assert telegram.respostas == [("cb1", "Vaga não encontrada.")]


# ---------- resumo


def test_resumo_diario(sessao, admin, vinculado):
    recomendada(sessao, admin)
    texto = texto_resumo(sessao, admin, AGORA.replace(hour=0))
    assert "Aguardando você: 1/50" in texto
    telegram = TelegramFalso()
    assert enviar_resumos(sessao, telegram, "America/Sao_Paulo", AGORA) == 1
