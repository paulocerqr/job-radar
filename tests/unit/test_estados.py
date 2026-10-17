import pytest

from job_radar.fila.estados import TRANSICOES, TransicaoInvalida, transicionar
from job_radar.models import HistoricoStatus, VagaUsuario
from job_radar.models.enums import OrigemTransicao, StatusVaga


class SessaoFalsa:
    def __init__(self):
        self.adicionados = []

    def add(self, objeto):
        self.adicionados.append(objeto)


def test_todos_os_estados_tem_transicoes_definidas():
    assert set(TRANSICOES) == set(StatusVaga)


def test_estados_terminais():
    terminais = {s for s, destinos in TRANSICOES.items() if not destinos}
    assert terminais == {
        StatusVaga.CONFIRMADA,
        StatusVaga.DESCARTADA,
        StatusVaga.IGNORADA,
        StatusVaga.EXPIRADA,
    }


def test_transicao_valida_registra_historico():
    sessao = SessaoFalsa()
    vu = VagaUsuario(status=StatusVaga.POOL)
    transicionar(sessao, vu, StatusVaga.FILA, OrigemTransicao.SISTEMA, "alimentador")
    assert vu.status == StatusVaga.FILA
    (historico,) = sessao.adicionados
    assert isinstance(historico, HistoricoStatus)
    assert (historico.de, historico.para) == (StatusVaga.POOL, StatusVaga.FILA)


def test_transicao_invalida():
    vu = VagaUsuario(status=StatusVaga.POOL)
    with pytest.raises(TransicaoInvalida):
        transicionar(SessaoFalsa(), vu, StatusVaga.CONFIRMADA, OrigemTransicao.USUARIO)
