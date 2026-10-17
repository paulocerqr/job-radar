import pytest

from job_radar.coleta.normalizador import (
    calcular_hash_dedupe,
    inferir_nivel,
    normalizar,
    url_canonica,
)
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta


def test_url_canonica_remove_rastreio():
    url = "https://Empresa.gupy.io/job/abc=?jobBoardSource=gupy_portal&utm_source=x&id=7#topo"
    assert url_canonica(url) == "https://empresa.gupy.io/job/abc=?id=7"


@pytest.mark.parametrize(
    ("titulo", "nivel"),
    [
        ("Estagiário(a) de TI", Nivel.ESTAGIO),
        ("Estágio em Desenvolvimento", Nivel.ESTAGIO),
        ("Desenvolvedor Python Jr", Nivel.JUNIOR),
        ("Analista DevOps Sênior", Nivel.SENIOR),
        ("Engenheiro de Software", Nivel.DESCONHECIDO),
    ],
)
def test_inferir_nivel(titulo, nivel):
    assert inferir_nivel(titulo) == nivel


def test_hash_ignora_diferencas_irrelevantes():
    a = calcular_hash_dedupe("ACME Ltda.", "Estágio em TI", "Brasília", Modalidade.PRESENCIAL)
    b = calcular_hash_dedupe("acme", "  estagio em ti ", "brasilia", Modalidade.HIBRIDO)
    assert a == b


def test_hash_remoto_ignora_cidade():
    a = calcular_hash_dedupe("ACME", "Dev Backend", "São Paulo", Modalidade.REMOTO)
    b = calcular_hash_dedupe("ACME", "Dev Backend", None, Modalidade.REMOTO)
    assert a == b


def test_hash_cidades_diferentes_sao_vagas_diferentes():
    a = calcular_hash_dedupe("ACME", "Estágio TI", "Brasília", Modalidade.PRESENCIAL)
    b = calcular_hash_dedupe("ACME", "Estágio TI", "Goiânia", Modalidade.PRESENCIAL)
    assert a != b


def test_normalizar_limpa_campos_e_infere_nivel():
    bruta = VagaBruta(
        fonte_id="x",
        id_externo="1",
        url="https://x.io/vaga?utm_source=a",
        titulo="  Estágio   em  TI ",
        empresa=" ACME ",
        descricao="<p>Python</p>",
        cidade="Brasília",
        uf="Distrito Federal",
    )
    normalizada = normalizar(bruta)
    assert normalizada.titulo == "Estágio em TI"
    assert normalizada.empresa == "ACME"
    assert normalizada.descricao == "Python"
    assert normalizada.uf == "DF"
    assert normalizada.nivel == Nivel.ESTAGIO
    assert normalizada.url_canonica == "https://x.io/vaga"
