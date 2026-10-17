import pytest

from job_radar.texto import contem_termo, html_para_texto, normalizar_chave, normalizar_empresa


def test_normalizar_chave():
    assert normalizar_chave("  Estágio em TI — Back-End!  ") == "estagio em ti back end"
    assert normalizar_chave(None) == ""


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("Stefanini Ltda.", "stefanini"),
        ("Itaú Unibanco S.A.", "itau unibanco"),
        ("ACME SA", "acme"),
        ("Empresa X EIRELI ME", "empresa x"),
    ],
)
def test_normalizar_empresa_remove_sufixos(bruto, esperado):
    assert normalizar_empresa(bruto) == esperado


@pytest.mark.parametrize(
    ("texto", "termo", "esperado"),
    [
        ("Estágio em TI", "ti", True),
        ("Tipo de vaga", "ti", False),
        ("Desenvolvedor Back-End", "back-end", True),
        ("Desenvolvedor Back-End", "backend", False),
        ("Full Stack Developer", "full stack", True),
        ("Analista DevOps Sênior", "senior", True),
    ],
)
def test_contem_termo_por_palavra_inteira(texto, termo, esperado):
    assert contem_termo(normalizar_chave(texto), termo) is esperado


def test_html_para_texto():
    html = "<p>Requisitos:</p><ul><li>Python &amp; Linux</li><li>Git</li></ul>"
    assert html_para_texto(html) == "Requisitos:\nPython & Linux\nGit"
