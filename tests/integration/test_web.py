"""Requer Postgres: API JSON da Web UI (login, Perfil & Regras, simulação, recálculo)."""

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


def entrar(cliente: TestClient, senha: str = "senha-de-teste"):
    return cliente.post("/api/login", json={"email": "ADMIN@teste.local", "senha": senha})


def perfil(**extra) -> dict:
    dados = {
        "palavras_chave": ["suporte", "machine learning"],
        "palavras_excluidas": ["senior"],
        "niveis": ["estagio"],
        "localidades": ["Brasília/DF"],
        "aceita_remoto": True,
        "score_minimo": 65,
        "ttl_pool_dias": 7,
        "ttl_recomendada_dias": 14,
        "curriculo_md": "# Meu CV",
        "instrucoes_ia": "aceito idas esporádicas",
    }
    return {**dados, **extra}


def test_login_sessao_e_logout(cliente):
    assert entrar(cliente, "errada").status_code == 401
    resposta = entrar(cliente)
    assert resposta.status_code == 200
    csrf = resposta.json()["csrf"]
    assert cliente.get("/api/sessao").json()["usuario"]["email"] == "admin@teste.local"
    assert cliente.post("/api/sair", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert cliente.get("/api/sessao").status_code == 401


def test_login_bloqueia_depois_de_varias_falhas(cliente):
    for _ in range(MAX_FALHAS):
        assert entrar(cliente, "errada").status_code == 401
    assert entrar(cliente).status_code == 429  # nem a senha certa passa durante o bloqueio


def test_token_csrf_errado_nao_salva(cliente):
    entrar(cliente)
    resposta = cliente.put("/api/perfil", json=perfil(), headers={"X-CSRF-Token": "outro"})
    assert resposta.status_code == 403


def test_salvar_perfil_simular_e_recalcular_pool(cliente):
    csrf = entrar(cliente).json()["csrf"]
    cabecalho = {"X-CSRF-Token": csrf}
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

    lido = cliente.get("/api/perfil").json()
    assert lido["perfil"]["localidades"] == ["Brasília/DF"]
    assert "estagio" in lido["limites"]["niveis"]

    simulacao = cliente.post("/api/perfil/simular", json=perfil(), headers=cabecalho).json()
    assert simulacao["nova"]["para_fila"] == 1
    assert simulacao["nova"]["exemplos"][0]["titulo"] == "Estagiário(a) de Suporte"

    resposta = cliente.put("/api/perfil?recalcular=true", json=perfil(), headers=cabecalho)
    assert resposta.status_code == 200
    assert resposta.json()["recalculadas"] == 1

    with nova_sessao() as sessao:
        salvo = sessao.scalar(select(Perfil))
        assert salvo.palavras_chave == ["suporte", "machine learning"]
        assert salvo.score_minimo == 65
        assert salvo.instrucoes_ia == "aceito idas esporádicas"
        assert sessao.scalar(select(VagaUsuario)).score_prefiltro >= 50


def test_perfil_invalido_nao_salva(cliente):
    csrf = entrar(cliente).json()["csrf"]
    resposta = cliente.put(
        "/api/perfil", json=perfil(localidades=["Brasília/XX"]), headers={"X-CSRF-Token": csrf}
    )
    assert resposta.status_code == 422
    assert "UF inválida" in resposta.json()["erros"]["localidades"]
    with nova_sessao() as sessao:
        assert sessao.scalar(select(Perfil)).score_minimo == 60
