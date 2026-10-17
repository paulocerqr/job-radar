import json
import logging
import uuid

import httpx
import pytest

from job_radar.logs import configurar_logs
from job_radar.models import Vaga
from job_radar.notificacao.mensagens import (
    botoes_motivo,
    botoes_recomendacao,
    texto_recomendacao,
)
from job_radar.notificacao.telegram import ClienteTelegram, ErroTelegram

TOKEN = "123456:SEGREDO-do-bot"


def cliente_com(responder) -> ClienteTelegram:
    return ClienteTelegram(TOKEN, http=httpx.Client(transport=httpx.MockTransport(responder)))


def test_enviar_mensagem_monta_requisicao():
    requisicoes = []

    def responder(request):
        requisicoes.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    resultado = cliente_com(responder).enviar_mensagem(42, "<b>oi</b>", [[{"text": "a"}]])

    assert resultado == {"message_id": 7}
    (requisicao,) = requisicoes
    assert requisicao.url.path == f"/bot{TOKEN}/sendMessage"
    corpo = json.loads(requisicao.content)
    assert corpo["chat_id"] == 42
    assert corpo["parse_mode"] == "HTML"
    assert corpo["reply_markup"] == {"inline_keyboard": [[{"text": "a"}]]}


def test_erro_da_api_nao_expoe_token():
    def responder(_):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(ErroTelegram) as erro:
        cliente_com(responder).enviar_mensagem(1, "x")
    assert "chat not found" in str(erro.value)
    assert TOKEN not in str(erro.value)


def test_falha_de_rede_nao_expoe_token():
    def responder(request):
        raise httpx.ConnectError(f"falhou ao conectar em {request.url}", request=request)

    with pytest.raises(ErroTelegram) as erro:
        cliente_com(responder).obter_updates(None)
    assert TOKEN not in str(erro.value)


def test_logs_do_httpx_ficam_silenciados():
    configurar_logs("json", "DEBUG")
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def vaga(**campos) -> Vaga:
    base = {
        "titulo": "Estágio <DevOps> & Cloud",
        "empresa": "ACME",
        "cidade": "Brasília",
        "uf": "DF",
        "modalidade": "presencial",
        "url_canonica": "https://x.io/1",
    }
    return Vaga(**(base | campos))


def test_texto_escapa_html_de_fora():
    auditoria = {
        "score": 80,
        "area": "devops",
        "resumo": "Boa vaga <script>",
        "requisitos_atendidos": ["Linux", "Docker", "Git", "quarto não aparece"],
        "gaps": ["Kubernetes"],
        "red_flags": [],
    }
    texto = texto_recomendacao(vaga(), auditoria)

    assert "Estágio &lt;DevOps&gt; &amp; Cloud" in texto
    assert "<script>" not in texto
    assert "ACME · Brasília, DF · presencial" in texto
    assert "Score 80" in texto
    assert "quarto não aparece" not in texto
    assert "🚩" not in texto


def test_texto_sem_auditoria():
    assert "Score" not in texto_recomendacao(vaga(), None)


def test_callback_data_cabe_no_limite_do_telegram():
    vu_id = uuid.uuid4()
    botoes = botoes_recomendacao(vu_id, "https://x.io") + botoes_motivo(vu_id, "https://x.io")
    dados = [b["callback_data"] for linha in botoes for b in linha if "callback_data" in b]
    assert dados
    assert all(len(d.encode()) <= 64 for d in dados)
