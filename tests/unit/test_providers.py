import json
import shlex
import sys

import httpx
import pytest

from job_radar.auditoria.providers.base import (
    ErroProvider,
    LimiteExcedido,
    RespostaInvalida,
    extrair_json,
)
from job_radar.auditoria.providers.cli import ProviderCLI
from job_radar.auditoria.providers.openai_compatible import ProviderOpenAICompativel

# ---------- extrair_json


@pytest.mark.parametrize(
    "texto",
    [
        '{"ok": true}',
        '```json\n{"ok": true}\n```',
        'Claro! Segue:\n{"ok": true}\nEspero ter ajudado.',
    ],
)
def test_extrair_json_tolera_formatos_comuns(texto):
    assert extrair_json(texto) == {"ok": True}


@pytest.mark.parametrize("texto", ["sem json", '{"ok": tru', "[1, 2]"])
def test_extrair_json_invalido(texto):
    with pytest.raises(RespostaInvalida):
        extrair_json(texto)


# ---------- openai_compatible


def provider_com(responder) -> ProviderOpenAICompativel:
    http = httpx.Client(transport=httpx.MockTransport(responder))
    return ProviderOpenAICompativel("https://api.x/v1/", "chave", "modelo-x", http=http)


def resposta_chat(conteudo: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "modelo-x-2026",
            "choices": [{"message": {"content": conteudo}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )


def test_openai_compativel_sucesso():
    requisicoes = []

    def responder(request):
        requisicoes.append(request)
        return resposta_chat('{"ok": true}')

    resposta = provider_com(responder).completar("sistema", "usuario")

    assert resposta.texto == '{"ok": true}'
    assert (resposta.tokens_entrada, resposta.tokens_saida) == (100, 20)
    assert resposta.modelo == "modelo-x-2026"
    (requisicao,) = requisicoes
    assert str(requisicao.url) == "https://api.x/v1/chat/completions"
    assert requisicao.headers["authorization"] == "Bearer chave"
    corpo = json.loads(requisicao.content)
    assert corpo["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in corpo["messages"]] == ["system", "user"]


def test_openai_compativel_repete_sem_json_mode_se_nao_suportado():
    corpos = []

    def responder(request):
        corpo = json.loads(request.content)
        corpos.append(corpo)
        if "response_format" in corpo:
            return httpx.Response(400, text="response_format is not supported")
        return resposta_chat('{"ok": true}')

    provider_com(responder).completar("s", "u")
    assert len(corpos) == 2
    assert "response_format" not in corpos[1]


def test_openai_compativel_429_vira_limite_excedido():
    def responder(_):
        return httpx.Response(429, headers={"retry-after": "12"}, text="rate limit")

    with pytest.raises(LimiteExcedido) as erro:
        provider_com(responder).completar("s", "u")
    assert erro.value.retry_after_s == 12
    assert erro.value.transitorio


def test_openai_compativel_401_nao_e_transitorio():
    with pytest.raises(ErroProvider) as erro:
        provider_com(lambda _: httpx.Response(401, text="invalid key")).completar("s", "u")
    assert not erro.value.transitorio


def test_openai_compativel_modelo_aposentado_nao_e_transitorio():
    with pytest.raises(ErroProvider) as erro:
        provider_com(lambda _: httpx.Response(410, text="end of life")).completar("s", "u")
    assert not erro.value.transitorio


def test_openai_compativel_lista_modelos():
    def responder(request):
        assert str(request.url) == "https://api.x/v1/models"
        return httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]})

    assert provider_com(responder).listar_modelos() == ["a", "b"]


def test_openai_compativel_falha_de_rede():
    def responder(request):
        raise httpx.ConnectError("sem rede", request=request)

    with pytest.raises(ErroProvider) as erro:
        provider_com(responder).completar("s", "u")
    assert erro.value.transitorio


# ---------- cli


def comando_python(codigo: str) -> str:
    return f"{sys.executable} -c '{codigo}'"


def test_cli_le_stdout_e_recebe_prompt_pelo_stdin():
    codigo = 'import sys, json; p = sys.stdin.read(); print(json.dumps({"tamanho": len(p)}))'
    resposta = ProviderCLI(comando_python(codigo), "fake").completar("abc", "def")
    assert extrair_json(resposta.texto) == {"tamanho": len("abc\n\ndef")}


def test_cli_le_arquivo_de_saida():
    codigo = 'import sys; open(sys.argv[1], "w").write("{\\"ok\\": true}")'
    resposta = ProviderCLI(comando_python(codigo) + " {saida}", "fake").completar("s", "u")
    assert extrair_json(resposta.texto) == {"ok": True}


def test_cli_codigo_de_saida_diferente_de_zero():
    codigo = 'import sys; sys.stderr.write("falhou"); sys.exit(3)'
    with pytest.raises(ErroProvider, match="código 3"):
        ProviderCLI(comando_python(codigo), "fake").completar("s", "u")


def test_cli_comando_inexistente_nao_e_transitorio():
    with pytest.raises(ErroProvider) as erro:
        ProviderCLI("comando-que-nao-existe-xyz", "fake").completar("s", "u")
    assert not erro.value.transitorio


def test_cli_timeout():
    with pytest.raises(ErroProvider, match="tempo esgotado"):
        ProviderCLI(comando_python("import time; time.sleep(5)"), "fake", 1).completar("s", "u")


def test_cli_substitui_modelo_sem_transformar_em_comando():
    modelo = "gpt-6-luna; echo nao-executar"
    codigo = (
        'import sys, json; print(json.dumps({"modelo": sys.argv[1], "prompt": sys.stdin.read()}))'
    )
    resposta = ProviderCLI(comando_python(codigo) + " {modelo}", modelo).completar("s", "u")
    assert extrair_json(resposta.texto) == {"modelo": modelo, "prompt": "s\n\nu"}
    assert resposta.modelo == modelo


def test_preset_codex_seleciona_luna_e_isola_configuracao_pessoal():
    from job_radar.auditoria.presets import PRESETS

    preset = PRESETS["codex"]
    args = shlex.split(preset.comando)
    assert preset.modelo == "gpt-6-luna"
    assert args[args.index("--model") + 1] == "{modelo}"
    assert "--ignore-user-config" in args and "--ignore-rules" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args
    assert "shell_tool" in args and "multi_agent" in args and "plugins" in args
    assert "web_search=disabled" in args and "project_doc_max_bytes=0" in args
    assert 'log_dir="{saida}.logs"' in args
