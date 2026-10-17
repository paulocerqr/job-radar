import pytest

from job_radar.filtro.localidade import localidade_atende, normalizar_uf

BRASILIA = [{"cidade": "Brasília", "uf": "DF"}]


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("DF", "DF"), ("df", "DF"), ("Distrito Federal", "DF"), ("São Paulo", "SP"), ("X", None)],
)
def test_normalizar_uf(valor, esperado):
    assert normalizar_uf(valor) == esperado


@pytest.mark.parametrize(
    ("cidade", "uf", "esperado"),
    [
        ("Brasília", "DF", True),
        ("Taguatinga", "DF", True),  # região administrativa conta como Brasília
        ("Brasilia", None, True),
        ("São Paulo", "SP", False),
        ("Goiânia", "GO", False),
        (None, None, None),
    ],
)
def test_localidade_atende(cidade, uf, esperado):
    assert localidade_atende(cidade, uf, BRASILIA) is esperado
