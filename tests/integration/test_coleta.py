import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select

from job_radar.coleta.execucao import executar_coleta
from job_radar.db import nova_sessao
from job_radar.models import Fonte, HistoricoStatus, Vaga, VagaFonte, VagaUsuario
from job_radar.models.enums import StatusExecucao, StatusVaga

FIXTURES = Path(__file__).parent.parent / "fixtures"
AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)


def cliente_gupy() -> httpx.Client:
    dados = json.loads((FIXTURES / "gupy_jobs.json").read_text())
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=dados)))


def contar(sessao, modelo) -> int:
    return sessao.scalar(select(func.count()).select_from(modelo))


def test_coleta_gupy_ponta_a_ponta(banco_com_seed):
    with nova_sessao() as sessao:
        sessao.get(Fonte, "gupy").config = {"termos": ["ti"], "pausa_s": 0}
        sessao.commit()

        execucao = executar_coleta(sessao, "gupy", http=cliente_gupy(), agora=AGORA)

        assert execucao.status == StatusExecucao.OK
        assert execucao.itens_coletados == 5
        # os dois "Bolsista..." da mesma empresa/cidade diferem no fim do título: 2 vagas
        assert execucao.itens_novos == 5
        assert execucao.itens_duplicados == 0
        assert contar(sessao, Vaga) == 5
        assert contar(sessao, VagaFonte) == 5

        # só a vaga presencial de Brasília passa no pré-filtro do admin
        (no_pool,) = sessao.scalars(select(VagaUsuario)).all()
        assert no_pool.status == StatusVaga.POOL
        assert no_pool.score_prefiltro > 0
        vaga = sessao.get(Vaga, no_pool.vaga_id)
        assert vaga.uf == "DF"
        assert contar(sessao, HistoricoStatus) == 1


def test_segunda_coleta_nao_duplica(banco_com_seed):
    with nova_sessao() as sessao:
        sessao.get(Fonte, "gupy").config = {"termos": ["ti"], "pausa_s": 0}
        sessao.commit()
        executar_coleta(sessao, "gupy", http=cliente_gupy(), agora=AGORA)

        segunda = executar_coleta(sessao, "gupy", http=cliente_gupy(), agora=AGORA)

        assert segunda.itens_novos == 0
        assert segunda.itens_duplicados == 5
        assert contar(sessao, Vaga) == 5
        assert contar(sessao, VagaUsuario) == 1


def test_mesma_vaga_em_outra_fonte_vira_uma_so(banco_com_seed):
    """RN06: outra fonte com outro id externo, mas mesma empresa/título/cidade."""
    dados = json.loads((FIXTURES / "gupy_jobs.json").read_text())
    copia = {**dados["data"][0], "id": 999, "jobUrl": "https://outra.fonte/vaga/999"}
    dados_com_copia = {**dados, "data": [*dados["data"], copia]}
    http = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=dados_com_copia))
    )
    with nova_sessao() as sessao:
        sessao.get(Fonte, "gupy").config = {"termos": ["ti"], "pausa_s": 0}
        sessao.commit()
        execucao = executar_coleta(sessao, "gupy", http=http, agora=AGORA)

        assert execucao.itens_duplicados == 1
        assert contar(sessao, Vaga) == 5
        assert contar(sessao, VagaFonte) == 6


def test_falha_http_registra_erro(banco_com_seed):
    falha = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with nova_sessao() as sessao:
        execucao = executar_coleta(sessao, "gupy", http=falha, agora=AGORA)
        assert execucao.status == StatusExecucao.ERRO
        assert "503" in execucao.erro
        assert sessao.get(Fonte, "gupy").ultima_execucao_em is not None
