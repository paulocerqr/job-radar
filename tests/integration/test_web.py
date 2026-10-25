"""Requer Postgres: fluxo da Web UI (login, Perfil & Regras, simulação, recálculo)."""

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from job_radar.db import nova_sessao
from job_radar.models import Perfil, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import Modalidade, Nivel, StatusVaga
from job_radar.web.app import create_app
from job_radar.web.sessao import MAX_FALHAS, limite_login


@pytest.fixture
def cliente(banco_com_seed):
    limite_login._falhas.clear()
    return TestClient(create_app())


def csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def entrar(cliente: TestClient, senha: str = "senha-de-teste"):
    token = csrf(cliente.get("/login").text)
    return cliente.post(
        "/login",
        data={"email": "ADMIN@teste.local", "senha": senha, "csrf": token},
        follow_redirects=False,
    )


def form_perfil(token: str, **extra) -> dict:
    dados = {
        "csrf": token,
        "palavras_chave": "suporte\nmachine learning",
        "palavras_excluidas": "senior",
        "niveis": "estagio",
        "localidades": "Brasília/DF",
        "aceita_remoto": "on",
        "score_minimo": "65",
        "ttl_pool_dias": "7",
        "ttl_recomendada_dias": "14",
        "curriculo_md": "# Meu CV",
        "instrucoes_ia": "aceito idas esporádicas",
    }
    dados.update(extra)
    return dados


def test_login_e_logout(cliente):
    assert entrar(cliente, "errada").status_code == 401
    resposta = entrar(cliente)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/perfil"
    pagina = cliente.get("/perfil")
    assert pagina.status_code == 200
    assert "Perfil &amp; Regras" in pagina.text
    cliente.post("/sair", data={"csrf": csrf(pagina.text)})
    assert cliente.get("/perfil", follow_redirects=False).status_code == 303


def test_login_bloqueia_depois_de_varias_falhas(cliente):
    for _ in range(MAX_FALHAS):
        assert entrar(cliente, "errada").status_code == 401
    assert entrar(cliente).status_code == 429  # nem a senha certa passa durante o bloqueio


def test_salvar_perfil_e_recalcular_pool(cliente):
    entrar(cliente)
    with nova_sessao() as sessao:
        admin = sessao.scalar(select(Usuario))
        vaga = Vaga(
            hash_dedupe="h1", titulo="Estagiário(a) de Suporte", url_canonica="https://x/1",
            cidade="Brasília", uf="DF", modalidade=Modalidade.HIBRIDO, nivel=Nivel.ESTAGIO,
            publicada_em=datetime.now(UTC),
        )  # fmt: skip
        sessao.add(vaga)
        sessao.flush()
        sessao.add(
            VagaUsuario(
                vaga_id=vaga.id, usuario_id=admin.id, status=StatusVaga.POOL, score_prefiltro=18
            )
        )
        sessao.commit()

    token = csrf(cliente.get("/perfil").text)
    simulacao = cliente.post(
        "/perfil/simular", data=form_perfil(token), headers={"X-CSRF-Token": token}
    )
    assert simulacao.status_code == 200
    assert "Estagiário(a) de Suporte" in simulacao.text

    resposta = cliente.post("/perfil", data=form_perfil(token, recalcular_pool="on"))
    assert resposta.status_code == 200
    assert "Pool recalculado: 1 vaga(s)" in resposta.text

    with nova_sessao() as sessao:
        perfil = sessao.scalar(select(Perfil))
        assert perfil.palavras_chave == ["suporte", "machine learning"]
        assert perfil.score_minimo == 65
        assert perfil.instrucoes_ia == "aceito idas esporádicas"
        assert sessao.scalar(select(VagaUsuario)).score_prefiltro >= 50


def test_formulario_invalido_nao_salva(cliente):
    entrar(cliente)
    token = csrf(cliente.get("/perfil").text)
    resposta = cliente.post("/perfil", data=form_perfil(token, localidades="Brasília/XX"))
    assert resposta.status_code == 422
    assert "UF inválida" in resposta.text
    with nova_sessao() as sessao:
        assert sessao.scalar(select(Perfil)).score_minimo == 60
