import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import httpx
import pandas as pd
import pytest
from pydantic import ValidationError

from job_radar.coleta.base import obter_coletor
from job_radar.coleta.fontes.jobspy import CONFIG_PADRAO, mapear
from job_radar.coleta.normalizador import normalizar
from job_radar.models.enums import Modalidade, Nivel

FIXTURE = Path(__file__).parent.parent / "fixtures" / "jobspy_linkedin.json"


@pytest.fixture
def itens():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def coletor():
    with httpx.Client() as http:
        yield obter_coletor("jobspy", http)


def test_descobrir_fontes_nao_importa_jobspy_ou_pandas():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from job_radar.coleta.base import fontes_registradas
assert 'jobspy' in fontes_registradas()
assert 'jobspy' not in sys.modules and 'pandas' not in sys.modules
""",
        ],
        check=True,
    )


def test_mapeia_campos_e_preserva_dados_ausentes(coletor, itens, monkeypatch):
    quadro = pd.DataFrame(itens)
    quadro.loc[1, "company"] = float("nan")
    quadro["date_posted"] = pd.to_datetime(quadro["date_posted"])
    scrape = Mock(return_value=quadro)
    monkeypatch.setattr("jobspy.scrape_jobs", scrape)

    vagas = coletor.buscar(CONFIG_PADRAO, 20)

    primeira = normalizar(vagas[0])
    assert primeira.id_externo == "1001"
    assert primeira.url == "https://www.linkedin.com/jobs/view/1001"
    assert primeira.cidade == "Brasília" and primeira.uf == "DF"
    assert primeira.modalidade == Modalidade.REMOTO
    assert primeira.nivel == Nivel.ESTAGIO  # título vence o job_level genérico
    assert primeira.publicada_em == datetime(2026, 10, 27, tzinfo=UTC)
    assert "Python" in primeira.descricao
    assert vagas[1].empresa is None and vagas[1].descricao is None
    assert vagas[1].publicada_em is None
    assert vagas[1].modalidade == Modalidade.DESCONHECIDA
    json.dumps([v.dados_brutos for v in vagas], allow_nan=False)
    args = scrape.call_args.kwargs
    assert args["site_name"] == ["linkedin"] and args["fetch_description"] is True
    assert args["hours_old"] == 72 and args["results_wanted"] == 20
    assert "is_remote" not in args and "job_type" not in args


def test_deduplica_entre_buscas_e_respeita_limite(coletor, itens, monkeypatch):
    primeira = pd.DataFrame([itens[0]])
    segunda = pd.DataFrame(
        [itens[0], itens[1], {**itens[1], "job_url": "https://www.linkedin.com/jobs/view/1003"}]
    )
    scrape = Mock(side_effect=[primeira, segunda])
    monkeypatch.setattr("jobspy.scrape_jobs", scrape)
    pausa = Mock()
    monkeypatch.setattr("job_radar.coleta.fontes.jobspy.time.sleep", pausa)
    config = {**CONFIG_PADRAO, "buscas": CONFIG_PADRAO["buscas"] * 3}

    vagas = coletor.buscar(config, 3)

    assert [v.id_externo for v in vagas] == ["1001", "1002", "1003"]
    assert [c.kwargs["results_wanted"] for c in scrape.call_args_list] == [3, 2]
    pausa.assert_called_once_with(5)


def test_para_sem_consultar_as_demais_buscas(coletor, itens, monkeypatch):
    scrape = Mock(return_value=pd.DataFrame(itens))
    monkeypatch.setattr("jobspy.scrape_jobs", scrape)
    assert len(coletor.buscar({**CONFIG_PADRAO, "buscas": CONFIG_PADRAO["buscas"] * 2}, 1)) == 1
    scrape.assert_called_once()


@pytest.mark.parametrize("com_resultados", [False, True])
def test_erro_reportado_no_dataframe_nao_vira_sucesso(coletor, itens, monkeypatch, com_resultados):
    quadro = pd.DataFrame(itens if com_resultados else [])
    quadro.attrs["errors"] = {"linkedin": "HTTP 429 Too Many Requests"}
    scrape = Mock(return_value=quadro)
    monkeypatch.setattr("jobspy.scrape_jobs", scrape)
    with pytest.raises(RuntimeError, match="429"):
        coletor.buscar(CONFIG_PADRAO, 20)
    scrape.assert_called_once()  # sem repetição imediata


def test_busca_vazia_e_avisos(coletor, monkeypatch, caplog):
    quadro = pd.DataFrame()
    quadro.attrs["warnings"] = {"linkedin": ["aviso da fonte"]}
    monkeypatch.setattr("jobspy.scrape_jobs", Mock(return_value=quadro))
    assert coletor.buscar(CONFIG_PADRAO, 20) == []
    assert "avisos do JobSpy" in caplog.text


def test_excecao_http_segue_para_executor(coletor, monkeypatch):
    monkeypatch.setattr("jobspy.scrape_jobs", Mock(side_effect=TimeoutError("timeout")))
    with pytest.raises(TimeoutError):
        coletor.buscar(CONFIG_PADRAO, 20)


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"buscas": []},
        {**CONFIG_PADRAO, "horas": 0},
        {**CONFIG_PADRAO, "buscas": [{"termo": " ", "local": "Brazil"}]},
        {**CONFIG_PADRAO, "buscas": CONFIG_PADRAO["buscas"] * 6},
        {**CONFIG_PADRAO, "proxies": ["x"]},
        {**CONFIG_PADRAO, "pausa_s": -1},
    ],
)
def test_rejeita_configuracao_invalida_antes_da_rede(coletor, monkeypatch, config):
    scrape = Mock()
    monkeypatch.setattr("jobspy.scrape_jobs", scrape)
    with pytest.raises(ValidationError):
        coletor.buscar(config, 20)
    scrape.assert_not_called()


@pytest.mark.parametrize("limite", [0, -1, 51])
def test_limite_invalido(coletor, limite):
    with pytest.raises(ValueError, match="limite"):
        coletor.buscar(CONFIG_PADRAO, limite)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/jobs/view/1",
        "javascript:alert(1)",
        "https://www.linkedin.com/jobs/view/sem-id",
    ],
)
def test_rejeita_url_invalida(itens, url):
    with pytest.raises(ValueError):
        mapear({**itens[0], "job_url": url})


def test_mapeia_serializacao_real_do_jobspy(coletor, monkeypatch):
    from datetime import date

    from jobspy.model import JobPost, JobType, Location

    post = JobPost(
        id="li-901",
        job_url="https://www.linkedin.com/jobs/view/901",
        title="Programa de formação em TI",
        company="Acme",
        location=Location(city="Brasília", state="Federal District", country="Brazil"),
        job_type=[JobType.INTERNSHIP],
        date_posted=date(2026, 10, 27),
    )
    quadro = pd.DataFrame([post.model_dump()])
    monkeypatch.setattr("jobspy.scrape_jobs", Mock(return_value=quadro))
    (vaga,) = coletor.buscar(CONFIG_PADRAO, 1)
    assert vaga.cidade == "Brasília" and vaga.uf == "DF"
    assert vaga.nivel == Nivel.ESTAGIO
    assert vaga.publicada_em == datetime(2026, 10, 27, tzinfo=UTC)
