"""Requer Postgres: cadastro, edição e remoção de providers pela Web UI."""

import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from job_radar.config import get_settings
from job_radar.db import nova_sessao
from job_radar.models import ProviderIA, Usuario
from job_radar.seguranca.cripto import decifrar, gerar_chave
from job_radar.web import providers_web
from job_radar.web.app import create_app
from job_radar.web.rotas import operacao
from job_radar.web.sessao import limite_login

IPS = {"api.publica.dev": "8.8.8.8", "interno.dev": "169.254.169.254", "local.dev": "10.0.0.5"}


@pytest.fixture
def cliente(banco_com_seed, monkeypatch):
    monkeypatch.setenv("FERNET_KEY", gerar_chave())
    get_settings.cache_clear()

    def resolver(host, porta, *args, **kwargs):
        if host not in IPS:
            raise socket.gaierror("não existe")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (IPS[host], porta))]

    monkeypatch.setattr(providers_web, "_resolver", resolver)
    limite_login._falhas.clear()
    c = TestClient(create_app())
    r = c.post("/api/login", json={"email": "admin@teste.local", "senha": "senha-de-teste"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def novo(**extra) -> dict:
    return {"nome": "meu-groq", "base_url": "https://api.publica.dev/openai/v1/", "modelo": "m1",
            "api_key": "gsk_segredo_1234", "rpm": 30, "rpd": "", **extra}  # fmt: skip


def test_presets_sem_cli(cliente):
    presets = cliente.get("/api/providers/presets").json()["presets"]
    assert set(presets) == {"groq", "nvidia", "gemini"}


def test_cadastrar_cifra_a_chave_e_vai_para_o_fim(cliente):
    cliente.post("/api/providers", json=novo(nome="primeiro"))
    r = cliente.post("/api/providers", json=novo())
    assert r.status_code == 201
    lista = cliente.get("/api/providers").json()["providers"]
    assert [p["nome"] for p in lista] == ["primeiro", "meu-groq"]
    assert (
        lista[1]["chave"] == "…1234" and lista[1]["base_url"] == "https://api.publica.dev/openai/v1"
    )
    assert "gsk_segredo_1234" not in str(lista)
    with nova_sessao() as sessao:
        salvo = sessao.scalar(select(ProviderIA).where(ProviderIA.nome == "meu-groq"))
        assert salvo.api_key_cifrada != b"gsk_segredo_1234"
        assert decifrar(salvo.api_key_cifrada) == "gsk_segredo_1234"
        assert salvo.rpd is None and salvo.tamanho_lote == 5
    assert cliente.post("/api/providers", json=novo()).json()["erros"]["nome"]  # nome repetido


@pytest.mark.parametrize(
    ("url", "trecho"),
    [
        ("http://api.publica.dev/v1", "https"),
        ("https://interno.dev/v1", "público"),  # servidor de metadados da GCP
        ("https://local.dev/v1", "público"),
        ("https://nao-existe.dev/v1", "resolver"),
        ("https://user:senha@api.publica.dev/v1", "usuário"),
    ],
)
def test_url_bloqueia_rede_interna(cliente, url, trecho):
    r = cliente.post("/api/providers", json=novo(base_url=url))
    assert r.status_code == 422
    assert trecho in r.json()["erros"]["base_url"]


def test_validacao_de_campos(cliente):
    r = cliente.post(
        "/api/providers", json=novo(nome="", modelo="", api_key="", rpm=0, timeout_s=5)
    )
    assert set(r.json()["erros"]) == {"nome", "modelo", "api_key", "rpm", "timeout_s"}


def test_editar_trocar_chave_e_remover(cliente):
    cliente.post("/api/providers", json=novo())
    pid = cliente.get("/api/providers").json()["providers"][0]["id"]
    r = cliente.patch(f"/api/providers/{pid}", json={"modelo": "m2", "rpm": 60})
    assert r.status_code == 200
    r = cliente.patch(f"/api/providers/{pid}", json={"api_key": "nova_chave_9999"})
    assert r.status_code == 200
    assert (
        cliente.patch(f"/api/providers/{pid}", json={"base_url": "https://interno.dev"}).status_code
        == 422
    )
    with nova_sessao() as sessao:
        p = sessao.get(ProviderIA, __import__("uuid").UUID(pid))
        assert (p.modelo, p.rpm, p.api_key_sufixo) == ("m2", 60, "9999")
        assert decifrar(p.api_key_cifrada) == "nova_chave_9999"
    assert cliente.request("DELETE", f"/api/providers/{pid}", json={}).status_code == 200
    assert cliente.get("/api/providers").json()["providers"] == []


def test_provider_cli_so_pelo_terminal_e_de_outro_usuario_nao(cliente):
    with nova_sessao() as sessao:
        dono = sessao.scalar(select(Usuario))
        sessao.add(ProviderIA(usuario_id=dono.id, nome="codex", tipo="cli", modelo="m",
                              comando="codex", prioridade=1))  # fmt: skip
        outro = Usuario(email="o@x.y", nome="O", senha_hash="x")
        sessao.add(outro)
        sessao.flush()
        sessao.add(ProviderIA(usuario_id=outro.id, nome="dele", tipo="openai_compatible",
                              modelo="m", base_url="https://x", prioridade=1))  # fmt: skip
        sessao.commit()
        dele = str(sessao.scalar(select(ProviderIA.id).where(ProviderIA.nome == "dele")))
    codex = cliente.get("/api/providers").json()["providers"][0]["id"]
    assert cliente.patch(f"/api/providers/{codex}", json={"modelo": "x"}).status_code == 409
    assert cliente.patch(f"/api/providers/{codex}", json={"ativo": False}).status_code == 200
    assert cliente.patch(f"/api/providers/{dele}", json={"modelo": "x"}).status_code == 404
    assert cliente.request("DELETE", f"/api/providers/{dele}", json={}).status_code == 404


def test_listar_modelos(cliente, monkeypatch):
    cliente.post("/api/providers", json=novo())
    pid = cliente.get("/api/providers").json()["providers"][0]["id"]

    class Falso(operacao.ProviderOpenAICompativel):
        def __init__(self):
            pass

        def listar_modelos(self):
            return ["b-modelo", "a-modelo"]

    monkeypatch.setattr(operacao, "construir_provider", lambda config: Falso())
    assert cliente.get(f"/api/providers/{pid}/modelos").json() == {
        "modelos": ["a-modelo", "b-modelo"]
    }


def test_url_com_chat_completions_e_ajustada(cliente):
    r = cliente.post(
        "/api/providers", json=novo(base_url="https://api.publica.dev/v1/chat/completions")
    )
    assert r.status_code == 201
    assert (
        cliente.get("/api/providers").json()["providers"][0]["base_url"]
        == "https://api.publica.dev/v1"
    )
