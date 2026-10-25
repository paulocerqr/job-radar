"""Requer Postgres: API das vagas (resumo, lista, detalhe, confirmar/ignorar)."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from job_radar.db import nova_sessao
from job_radar.fila.estados import criar_no_pool, transicionar
from job_radar.models import Auditoria, ExecucaoColeta, HistoricoStatus, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import Modalidade, Nivel, OrigemTransicao, StatusVaga
from job_radar.web.app import create_app
from job_radar.web.sessao import limite_login


def _vaga(sessao, usuario, titulo: str, empresa: str, score_ia: int | None, recomendar: bool):
    vaga = Vaga(
        hash_dedupe=uuid.uuid4().hex, titulo=titulo, empresa=empresa,
        url_canonica=f"https://x/{uuid.uuid4().hex}", cidade="Brasília", uf="DF",
        modalidade=Modalidade.HIBRIDO, nivel=Nivel.ESTAGIO, publicada_em=datetime.now(UTC),
        descricao="Linux e Docker",
    )  # fmt: skip
    sessao.add(vaga)
    sessao.flush()
    vu = criar_no_pool(sessao, vaga.id, usuario.id, 70, datetime.now(UTC))
    if recomendar:
        transicionar(sessao, vu, StatusVaga.FILA, OrigemTransicao.SISTEMA)
        transicionar(sessao, vu, StatusVaga.RECOMENDADA, OrigemTransicao.IA)
        vu.score_ia = score_ia
        sessao.add(
            Auditoria(
                vaga_usuario_id=vu.id, modelo="m", versao_prompt="v2", sucesso=True,
                resultado={"resumo": f"parecer {titulo}", "gaps": ["Ansible"], "area": "devops"},
            )
        )  # fmt: skip
    return vu


@pytest.fixture
def dados(banco_com_seed):
    with nova_sessao() as sessao:
        admin = sessao.scalar(select(Usuario))
        a = _vaga(sessao, admin, "Estágio DevOps", "Acme", 72, recomendar=True)
        b = _vaga(sessao, admin, "Estágio Suporte", "Beta", 91, recomendar=True)
        c = _vaga(sessao, admin, "Estágio Dados", "Gama", None, recomendar=False)
        sessao.add(ExecucaoColeta(fonte_id="gupy", status="ok", itens_coletados=10, itens_novos=3))
        outro = Usuario(email="outro@x.y", senha_hash="x", nome="Outro")
        sessao.add(outro)
        sessao.flush()
        d = _vaga(sessao, outro, "Vaga de outra pessoa", "Delta", 80, recomendar=True)
        sessao.commit()
        return {"a": str(a.id), "b": str(b.id), "c": str(c.id), "d": str(d.id)}


@pytest.fixture
def cliente(dados):
    limite_login._falhas.clear()
    c = TestClient(create_app())
    r = c.post("/api/login", json={"email": "admin@teste.local", "senha": "senha-de-teste"})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def test_resumo(cliente):
    r = cliente.get("/api/resumo").json()
    assert r["contagens"]["recomendada"] == 2
    assert r["contagens"]["pool"] == 1
    assert r["recomendadas_hoje"] == 2
    assert r["vagas_novas_hoje"] == 3
    gupy = next(f for f in r["fontes"] if f["id"] == "gupy")
    assert gupy["novas"] == 3
    assert r["atividade"][0]["para"] == "recomendada"
    assert "nivel" in r["motivos_ignorar"]


def test_lista_ordena_por_nota_e_busca(cliente):
    r = cliente.get("/api/vagas?status=recomendada").json()
    assert r["total"] == 2
    assert [i["titulo"] for i in r["itens"]] == ["Estágio Suporte", "Estágio DevOps"]
    assert r["itens"][0]["resumo"] == "parecer Estágio Suporte"
    assert cliente.get("/api/vagas?status=pool").json()["itens"][0]["titulo"] == "Estágio Dados"
    assert cliente.get("/api/vagas?status=recomendada&busca=acme").json()["total"] == 1


def test_detalhe_com_parecer_e_historico(cliente, dados):
    r = cliente.get(f"/api/vagas/{dados['a']}").json()
    assert r["descricao"] == "Linux e Docker"
    assert r["auditoria"]["resultado"]["gaps"] == ["Ansible"]
    assert [h["para"] for h in r["historico"]] == ["pool", "fila", "recomendada"]


def test_vaga_de_outra_pessoa_nao_aparece(cliente, dados):
    assert cliente.get(f"/api/vagas/{dados['d']}").status_code == 404
    assert cliente.post(f"/api/vagas/{dados['d']}/confirmar", json={}).status_code == 404


def test_confirmar_e_ignorar(cliente, dados):
    r = cliente.post(f"/api/vagas/{dados['a']}/confirmar", json={})
    assert r.json()["status"] == "confirmada"
    assert cliente.post(f"/api/vagas/{dados['a']}/confirmar", json={}).status_code == 409

    assert (
        cliente.post(f"/api/vagas/{dados['b']}/ignorar", json={"motivo": "xyz"}).status_code == 422
    )
    r = cliente.post(f"/api/vagas/{dados['b']}/ignorar", json={"motivo": "local"})
    assert r.json() == {"id": dados["b"], "status": "ignorada", "motivo_usuario": "local"}

    with nova_sessao() as sessao:
        vu = sessao.get(VagaUsuario, uuid.UUID(dados["b"]))
        assert vu.motivo_usuario == "local"
        ultimo = sessao.scalars(
            select(HistoricoStatus).where(HistoricoStatus.vaga_usuario_id == vu.id)
            .order_by(HistoricoStatus.id.desc())
        ).first()  # fmt: skip
        assert (ultimo.para, ultimo.origem, ultimo.detalhe) == ("ignorada", "usuario", "web")


def test_decisao_exige_csrf(cliente, dados):
    del cliente.headers["X-CSRF-Token"]
    assert cliente.post(f"/api/vagas/{dados['a']}/confirmar", json={}).status_code == 403
