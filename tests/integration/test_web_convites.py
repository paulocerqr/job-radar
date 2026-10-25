"""Requer Postgres: convites de cadastro, gestão de usuários, Telegram pela web e o uso
dos providers do admin por convidados."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from job_radar.auditoria.auditor import providers_do_usuario
from job_radar.db import nova_sessao
from job_radar.models import CanalNotificacao, Convite, Perfil, ProviderIA, Usuario
from job_radar.models.enums import Papel
from job_radar.web.app import create_app
from job_radar.web.rotas import usuarios as rotas_usuarios
from job_radar.web.sessao import MAX_FALHAS, limite_login


def _cliente() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def admin(banco_com_seed):
    limite_login._falhas.clear()
    c = _cliente()
    r = c.post("/api/login", json={"email": "admin@teste.local", "senha": "senha-de-teste"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def _convidar(admin, email="nova@x.y") -> str:
    r = admin.post("/api/convites", json={"email": email})
    assert r.status_code == 201
    return parse_qs(urlsplit(r.json()["caminho"]).query)["token"][0]


def test_convite_do_inicio_ao_fim(admin):
    token = _convidar(admin, "Nova@X.y")
    with nova_sessao() as sessao:  # só o hash vai para o banco
        assert sessao.scalar(select(Convite.token_hash)) != token

    visitante = _cliente()
    assert visitante.get(f"/api/convites/validar?token={token}").json()["email"] == "nova@x.y"
    r = visitante.post(
        "/api/convites/aceitar", json={"token": token, "nome": "Ana", "senha": "curta"}
    )
    assert r.status_code == 422 and "senha" in r.json()["erros"]
    r = visitante.post(
        "/api/convites/aceitar",
        json={"token": token, "nome": " Ana  Souza ", "senha": "senha-boa-123"},
    )
    assert r.status_code == 201
    assert r.json()["usuario"] == {"nome": "Ana Souza", "email": "nova@x.y", "papel": "usuario"}
    assert visitante.get("/api/sessao").json()["usuario"]["papel"] == "usuario"  # já entra logada

    # uso único, e o login normal passa a funcionar
    assert _cliente().get(f"/api/convites/validar?token={token}").status_code == 404
    login = _cliente().post("/api/login", json={"email": "nova@x.y", "senha": "senha-boa-123"})
    assert login.status_code == 200
    with nova_sessao() as sessao:
        ana = sessao.scalar(select(Usuario).where(Usuario.email == "nova@x.y"))
        assert sessao.get(Perfil, ana.id).localidades == [{"cidade": "Brasília", "uf": "DF"}]
    situacoes = {c["email"]: c["situacao"] for c in admin.get("/api/usuarios").json()["convites"]}
    assert situacoes["nova@x.y"] == "usado"


def test_convite_revogado_expirado_ou_email_existente(admin):
    assert admin.post("/api/convites", json={"email": "admin@teste.local"}).status_code == 409
    assert admin.post("/api/convites", json={"email": "sem-arroba"}).status_code == 422

    velho = _convidar(admin, "a@x.y")
    novo = _convidar(admin, "a@x.y")  # o novo convite revoga o anterior do mesmo e-mail
    assert _cliente().get(f"/api/convites/validar?token={velho}").status_code == 404
    assert _cliente().get(f"/api/convites/validar?token={novo}").status_code == 200

    convite_id = next(c["id"] for c in admin.get("/api/usuarios").json()["convites"]
                      if c["situacao"] == "pendente")  # fmt: skip
    revogado = admin.request("DELETE", f"/api/convites/{convite_id}", json={})
    assert revogado.json().get("situacao") == "revogado", revogado.text
    assert _cliente().get(f"/api/convites/validar?token={novo}").status_code == 404

    expira = _convidar(admin, "b@x.y")
    with nova_sessao() as sessao:
        for c in sessao.scalars(select(Convite).where(Convite.email == "b@x.y")):
            c.expira_em = datetime.now(UTC) - timedelta(minutes=1)
        sessao.commit()
    assert _cliente().get(f"/api/convites/validar?token={expira}").status_code == 404


def test_tokens_errados_bloqueiam_o_ip(admin):
    visitante = _cliente()
    for _ in range(MAX_FALHAS):
        assert visitante.get("/api/convites/validar?token=chute").status_code == 404
    assert visitante.get("/api/convites/validar?token=outro").status_code == 429


def test_usuario_comum_nao_gerencia_e_desativado_nao_entra(admin):
    token = _convidar(admin, "c@x.y")
    comum = _cliente()
    r = comum.post(
        "/api/convites/aceitar", json={"token": token, "nome": "Caio", "senha": "senha-boa-123"}
    )
    comum.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert comum.get("/api/usuarios").status_code == 403
    assert comum.post("/api/convites", json={"email": "d@x.y"}).status_code == 403

    lista = admin.get("/api/usuarios").json()["usuarios"]
    eu = next(u for u in lista if u["eu"])
    caio = next(u for u in lista if u["email"] == "c@x.y")
    assert admin.patch(f"/api/usuarios/{eu['id']}", json={"ativo": False}).status_code == 409
    assert (
        admin.patch(f"/api/usuarios/{caio['id']}", json={"ativo": False}).json()["ativo"] is False
    )
    assert comum.get("/api/sessao").status_code == 401  # sessão aberta deixa de valer
    login = _cliente().post("/api/login", json={"email": "c@x.y", "senha": "senha-boa-123"})
    assert login.status_code == 401


def test_convidado_usa_os_providers_do_admin(admin):
    with nova_sessao() as sessao:
        dono = sessao.scalar(select(Usuario).where(Usuario.papel == Papel.ADMIN))
        sessao.add_all([
            ProviderIA(usuario_id=dono.id, nome="groq", tipo="openai_compatible", modelo="m",
                       base_url="https://x", prioridade=1),
            ProviderIA(usuario_id=dono.id, nome="codex", tipo="cli", modelo="m", comando="codex",
                       prioridade=2),
        ])  # fmt: skip
        convidado = Usuario(email="e@x.y", nome="E", senha_hash="x", papel=Papel.USUARIO)
        sessao.add(convidado)
        sessao.commit()
        assert [p.nome for p in providers_do_usuario(sessao, convidado)] == ["groq"]  # sem CLI
        sessao.add(ProviderIA(usuario_id=convidado.id, nome="proprio", tipo="openai_compatible",
                              modelo="m", base_url="https://y", prioridade=1))  # fmt: skip
        sessao.commit()
        assert [p.nome for p in providers_do_usuario(sessao, convidado)] == ["proprio"]


def test_telegram_pela_web(admin, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")  # ignora um .env local com o token real
    rotas_usuarios.get_settings.cache_clear()
    assert admin.get("/api/telegram").json() == {"configurado": False, "situacao": "nao_vinculado"}
    assert admin.post("/api/telegram/vincular", json={}).status_code == 409

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    rotas_usuarios.get_settings.cache_clear()

    class Bot:
        def __init__(self, token):
            pass

        def eu(self):
            return {"username": "JobRadarBot"}

    monkeypatch.setattr(rotas_usuarios, "ClienteTelegram", Bot)
    link = admin.post("/api/telegram/vincular", json={}).json()["link"]
    assert link.startswith("https://t.me/JobRadarBot?start=")
    with nova_sessao() as sessao:
        assert sessao.scalar(select(CanalNotificacao.token_vinculo)) == link.split("start=")[1]
    assert admin.get("/api/telegram").json()["situacao"] == "aguardando"
