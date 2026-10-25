import json
from pathlib import Path

import httpx

from job_radar.coleta.base import obter_coletor
from job_radar.models.enums import Modalidade, Nivel

FIXTURES = Path(__file__).parent.parent / "fixtures"


def cliente_com(rotas: dict[str, object]) -> tuple[httpx.Client, list[httpx.Request]]:
    """Cliente httpx que responde por host+path e registra as requisições feitas."""
    requisicoes: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        corpo = rotas[f"{request.url.host}{request.url.path}"]
        if callable(corpo):
            corpo = corpo(request)
        return httpx.Response(200, json=corpo)

    return httpx.Client(transport=httpx.MockTransport(responder)), requisicoes


def test_gupy_mapeia_campos_e_deduplica_entre_termos():
    dados = json.loads((FIXTURES / "gupy_jobs.json").read_text())
    http, requisicoes = cliente_com({"portal.gupy.io/api/job-search/jobs": dados})
    config = {
        "termos": ["ti", "tecnologia"],
        "filtros": [],
        "tipos": ["vacancy_type_internship"],
        "pausa_s": 0,
    }

    vagas = obter_coletor("gupy", http).buscar(config, limite=100)

    assert len(requisicoes) == 2  # um por termo; total da fixture cabe em uma página
    assert requisicoes[0].url.params["type"] == "vacancy_type_internship"
    assert len(vagas) == len(dados["data"])  # mesmas vagas nos dois termos → sem repetição
    df = next(v for v in vagas if v.uf == "Distrito Federal")
    assert df.fonte_id == "gupy"
    assert df.cidade == "Brasília"
    assert df.modalidade == Modalidade.PRESENCIAL
    assert df.nivel == Nivel.ESTAGIO
    assert df.empresa
    assert df.publicada_em is not None


def test_gupy_busca_por_filtros_sem_termo():
    dados = json.loads((FIXTURES / "gupy_jobs.json").read_text())
    http, requisicoes = cliente_com({"portal.gupy.io/api/job-search/jobs": dados})
    config = {"termos": ["ti"], "filtros": [{"state": "Distrito Federal"}], "pausa_s": 0}

    obter_coletor("gupy", http).buscar(config, limite=100)

    assert len(requisicoes) == 2
    assert requisicoes[0].url.params["jobName"] == "ti"
    filtro = requisicoes[1].url.params
    assert filtro["state"] == "Distrito Federal"
    assert "jobName" not in filtro
    assert filtro["type"] == "vacancy_type_internship"


def test_gupy_respeita_limite():
    dados = json.loads((FIXTURES / "gupy_jobs.json").read_text())
    http, _ = cliente_com({"portal.gupy.io/api/job-search/jobs": dados})
    vagas = obter_coletor("gupy", http).buscar({"termos": ["ti"], "pausa_s": 0}, limite=2)
    assert len(vagas) == 2


def test_github_mapeia_labels_e_ignora_stale():
    issues = json.loads((FIXTURES / "github_issues.json").read_text())

    def paginar(request: httpx.Request):
        return issues if request.url.params["page"] == "1" else []

    http, _ = cliente_com({"api.github.com/repos/backend-br/vagas/issues": paginar})
    vagas = obter_coletor("github_backendbr", http).buscar(
        {"repositorio": "backend-br/vagas"}, limite=50
    )

    assert len(vagas) == len(issues) - 1  # a issue "Stale" fica de fora
    primeira = vagas[0]
    assert primeira.titulo == "Full Stack Developer Pleno"  # sem "[Remoto]" e sem empresa
    assert primeira.empresa == "Rotha IA"
    assert primeira.modalidade == Modalidade.REMOTO
    assert primeira.nivel == Nivel.JUNIOR  # labels Pleno + Júnior → aceita júnior


def test_github_extrai_empresa_com_na():
    from job_radar.coleta.fontes.github_issues import mapear

    issue = {
        "number": 1,
        "title": "Software Engineer (For Women in Tech Candidates) na Google",
        "html_url": "https://github.com/x/y/issues/1",
        "labels": [],
    }
    vaga = mapear(issue, "github_backendbr")
    assert vaga.titulo == "Software Engineer (For Women in Tech Candidates)"
    assert vaga.empresa == "Google"


def test_solides_mapeia_campos_e_monta_link():
    dados = json.loads((FIXTURES / "solides_vagas.json").read_text())
    http, requisicoes = cliente_com({"apigw.solides.com.br/jobs/v3/vacancies": dados})
    config = {"buscas": [{"contractsType": "estagio", "jobsType": "remoto"}], "pausa_s": 0}

    vagas = obter_coletor("solides", http).buscar(config, limite=100)

    assert len(requisicoes) == 1  # totalPages = 1
    params = requisicoes[0].url.params
    assert params["contractsType"] == "estagio"
    assert params["take"] == "25"
    assert len(vagas) == len(dados["data"])
    ia = next(v for v in vagas if "Inteligência Artificial" in v.titulo)
    assert ia.fonte_id == "solides"
    assert ia.url == "https://concert.vagas.solides.com.br/vaga/939337"
    assert ia.titulo.endswith("Full Stack")  # sem o espaço final da fonte
    assert ia.uf == "MG"
    assert ia.modalidade == Modalidade.REMOTO
    assert ia.nivel == Nivel.ESTAGIO
    assert ia.publicada_em is not None and ia.publicada_em.tzinfo is not None


def test_solides_pagina_e_ignora_vaga_encerrada():
    item = json.loads((FIXTURES / "solides_vagas.json").read_text())["data"][0]

    def responder(request: httpx.Request):
        pagina = int(request.url.params["page"])
        encerrada = {**item, "id": "x2", "currentState": "encerrada"}
        dados = [{**item, "id": "x1"}] if pagina == 1 else [encerrada]
        return {"totalPages": 2, "data": dados}

    http, requisicoes = cliente_com({"apigw.solides.com.br/jobs/v3/vacancies": responder})
    vagas = obter_coletor("solides", http).buscar({"buscas": [{}], "pausa_s": 0}, limite=100)

    assert [r.url.params["page"] for r in requisicoes] == ["1", "2"]
    assert [v.id_externo for v in vagas] == ["x1"]
