"""Requer Postgres: API de fontes e providers, e coleta respeitando fonte desativada."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from typer.testing import CliRunner

from job_radar.auditoria.providers.base import ErroProvider
from job_radar.cli import app as cli
from job_radar.db import nova_sessao
from job_radar.models import ExecucaoColeta, ProviderIA, Usuario
from job_radar.models.enums import Papel, StatusExecucao
from job_radar.seguranca.auth import gerar_hash_senha
from job_radar.seguranca.cripto import ChaveFernetInvalida
from job_radar.web.app import create_app
from job_radar.web.rotas import operacao
from job_radar.web.sessao import limite_login


def _entrar(email: str, senha: str) -> TestClient:
    c = TestClient(create_app())
    r = c.post("/api/login", json={"email": email, "senha": senha})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


@pytest.fixture
def admin(banco_com_seed):
    limite_login._falhas.clear()
    with nova_sessao() as sessao:
        dono = sessao.scalar(select(Usuario))
        for prioridade, nome in enumerate(["groq", "nvidia", "gemini"], start=1):
            sessao.add(
                ProviderIA(
                    usuario_id=dono.id, nome=nome, tipo="openai_compatible", modelo="m",
                    base_url="https://x", api_key_sufixo="ab12", prioridade=prioridade,
                )
            )  # fmt: skip
        sessao.commit()
    return _entrar("admin@teste.local", "senha-de-teste")


def _ids(cliente) -> list[str]:
    return [p["id"] for p in cliente.get("/api/providers").json()["providers"]]


def test_lista_fontes_com_ultima_execucao(admin):
    with nova_sessao() as sessao:
        sessao.add(ExecucaoColeta(fonte_id="gupy", status="ok", itens_coletados=9, itens_novos=2))
        sessao.commit()
    r = admin.get("/api/fontes").json()
    assert r["pode_alterar"] is True
    gupy = next(f for f in r["fontes"] if f["id"] == "gupy")
    assert gupy["ultima"]["novas"] == 2 and gupy["implementada"] is True
    assert next(f for f in r["fontes"] if f["id"] == "greenhouse")["implementada"] is False


def test_desativar_fonte_e_cli_respeita(admin):
    assert admin.patch("/api/fontes/gupy", json={"ativa": "não"}).status_code == 422
    assert admin.patch("/api/fontes/gupy", json={"ativa": False}).json()["ativa"] is False
    resultado = CliRunner().invoke(cli, ["coletar", "gupy"])
    assert resultado.exit_code == 0
    with nova_sessao() as sessao:
        assert sessao.scalar(select(func.count()).select_from(ExecucaoColeta)) == 0
    assert admin.post("/api/fontes/gupy/coletar", json={}).status_code == 409


def test_coletar_agora_em_segundo_plano(admin, monkeypatch):
    disparadas = []
    monkeypatch.setattr(operacao, "_coletar_em_segundo_plano", disparadas.append)
    assert admin.post("/api/fontes/gupy/coletar", json={}).status_code == 202
    assert disparadas == ["gupy"]
    assert admin.post("/api/fontes/greenhouse/coletar", json={}).status_code == 404

    with nova_sessao() as sessao:  # outra coleta da mesma fonte em andamento
        sessao.add(ExecucaoColeta(fonte_id="gupy", status=StatusExecucao.RODANDO,
                                  iniciada_em=datetime.now(UTC)))  # fmt: skip
        sessao.commit()
    assert admin.post("/api/fontes/gupy/coletar", json={}).status_code == 409


def test_usuario_comum_nao_altera_fontes(admin):
    with nova_sessao() as sessao:
        sessao.add(Usuario(email="comum@x.y", nome="Comum", papel=Papel.USUARIO,
                           senha_hash=gerar_hash_senha("senha-comum")))  # fmt: skip
        sessao.commit()
    comum = _entrar("comum@x.y", "senha-comum")
    assert comum.get("/api/fontes").json()["pode_alterar"] is False
    assert comum.patch("/api/fontes/gupy", json={"ativa": False}).status_code == 403
    assert comum.post("/api/fontes/gupy/coletar", json={}).status_code == 403
    assert comum.get("/api/providers").json()["providers"] == []  # só os próprios


def test_providers_lista_desativa_e_reordena(admin):
    r = admin.get("/api/providers").json()["providers"]
    assert [p["nome"] for p in r] == ["groq", "nvidia", "gemini"]
    assert r[0]["chave"] == "…ab12" and "api_key_cifrada" not in r[0]

    groq, nvidia, gemini = _ids(admin)
    assert admin.patch(f"/api/providers/{nvidia}", json={"ativo": False}).json()["ativo"] is False
    assert admin.put("/api/providers/ordem", json={"ids": [groq, nvidia]}).status_code == 422
    assert (
        admin.put("/api/providers/ordem", json={"ids": [gemini, groq, nvidia]}).status_code == 200
    )
    with nova_sessao() as sessao:
        nomes = sessao.scalars(select(ProviderIA.nome).order_by(ProviderIA.prioridade)).all()
    assert nomes == ["gemini", "groq", "nvidia"]


def test_testar_provider(admin, monkeypatch):
    class Falso:
        def completar(self, sistema, usuario):
            raise ErroProvider("HTTP 401: chave inválida")

    monkeypatch.setattr(operacao, "construir_provider", lambda config: Falso())
    r = admin.post(f"/api/providers/{_ids(admin)[0]}/testar", json={}).json()
    assert r == {"ok": False, "erro": "HTTP 401: chave inválida"}


def test_testar_provider_com_chave_que_nao_decifra(admin, monkeypatch):
    def falha(config):
        raise ChaveFernetInvalida("FERNET_KEY não decifra a chave salva (foi trocada?)")

    monkeypatch.setattr(operacao, "construir_provider", falha)
    r = admin.post(f"/api/providers/{_ids(admin)[0]}/testar", json={})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "erro": "FERNET_KEY não decifra a chave salva (foi trocada?)"}
