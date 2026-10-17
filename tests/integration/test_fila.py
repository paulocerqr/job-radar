import itertools
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from job_radar.db import nova_sessao
from job_radar.fila.alimentador import alimentar_fila
from job_radar.fila.expirador import expirar
from job_radar.models import HistoricoStatus, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import StatusVaga

AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)
_sequencia = itertools.count()


@pytest.fixture
def sessao(banco_com_seed):
    with nova_sessao() as sessao:
        yield sessao


@pytest.fixture
def admin(sessao) -> Usuario:
    usuario = sessao.scalar(select(Usuario))
    usuario.limite_fila = 3
    usuario.limite_recomendadas = 2
    sessao.commit()
    return usuario


def criar(
    sessao,
    usuario: Usuario,
    status: StatusVaga = StatusVaga.POOL,
    score: int = 50,
    publicada_em: datetime | None = AGORA,
    expira_em: datetime | None = None,
) -> VagaUsuario:
    n = next(_sequencia)
    vaga = Vaga(
        hash_dedupe=f"hash-{n}",
        titulo=f"Vaga {n}",
        url_canonica=f"https://x.io/{n}",
        publicada_em=publicada_em,
    )
    sessao.add(vaga)
    sessao.flush()
    vaga_usuario = VagaUsuario(
        vaga_id=vaga.id,
        usuario_id=usuario.id,
        status=status,
        score_prefiltro=score,
        expira_em=expira_em,
    )
    sessao.add(vaga_usuario)
    sessao.commit()
    return vaga_usuario


def status_de(sessao, vaga_usuario: VagaUsuario) -> str:
    sessao.refresh(vaga_usuario)
    return vaga_usuario.status


def test_alimentador_move_as_melhores_ate_o_limite(sessao, admin):
    scores = [60, 90, 50, 70, 55]
    vagas = [criar(sessao, admin, score=s) for s in scores]

    assert alimentar_fila(sessao, AGORA) == 3

    na_fila = {v.score_prefiltro for v in vagas if status_de(sessao, v) == StatusVaga.FILA}
    assert na_fila == {90, 70, 60}
    historico = sessao.scalar(select(func.count()).select_from(HistoricoStatus))
    assert historico == 3


def test_score_baixo_fica_no_pool(sessao, admin):
    fraca = criar(sessao, admin, score=49)
    assert alimentar_fila(sessao, AGORA) == 0
    assert status_de(sessao, fraca) == StatusVaga.POOL


def test_alimentador_completa_so_as_vagas_livres(sessao, admin):
    criar(sessao, admin, status=StatusVaga.FILA)
    criar(sessao, admin, status=StatusVaga.FILA)
    for _ in range(3):
        criar(sessao, admin)

    assert alimentar_fila(sessao, AGORA) == 1


def test_empate_de_score_prefere_a_mais_recente(sessao, admin):
    admin.limite_fila = 1
    sessao.commit()
    antiga = criar(sessao, admin, score=50, publicada_em=AGORA - timedelta(days=10))
    recente = criar(sessao, admin, score=50, publicada_em=AGORA)

    alimentar_fila(sessao, AGORA)

    assert status_de(sessao, recente) == StatusVaga.FILA
    assert status_de(sessao, antiga) == StatusVaga.POOL


def test_backpressure_com_recomendadas_cheias(sessao, admin):
    criar(sessao, admin, status=StatusVaga.RECOMENDADA)
    criar(sessao, admin, status=StatusVaga.RECOMENDADA)
    candidata = criar(sessao, admin)

    assert alimentar_fila(sessao, AGORA) == 0
    assert status_de(sessao, candidata) == StatusVaga.POOL


def test_alimentador_ignora_pool_vencido(sessao, admin):
    vencida = criar(sessao, admin, expira_em=AGORA - timedelta(minutes=1))

    assert alimentar_fila(sessao, AGORA) == 0
    assert status_de(sessao, vencida) == StatusVaga.POOL


def test_alimentador_limpa_ttl_ao_entrar_na_fila(sessao, admin):
    vaga = criar(sessao, admin, expira_em=AGORA + timedelta(days=3))
    alimentar_fila(sessao, AGORA)
    sessao.refresh(vaga)
    assert vaga.expira_em is None


def test_expirador_vence_pool_e_recomendadas(sessao, admin):
    ontem = AGORA - timedelta(days=1)
    amanha = AGORA + timedelta(days=1)
    pool_vencida = criar(sessao, admin, expira_em=ontem)
    recomendada_vencida = criar(sessao, admin, status=StatusVaga.RECOMENDADA, expira_em=ontem)
    pool_valida = criar(sessao, admin, expira_em=amanha)
    na_fila = criar(sessao, admin, status=StatusVaga.FILA)

    assert expirar(sessao, AGORA) == 2

    assert status_de(sessao, pool_vencida) == StatusVaga.EXPIRADA
    assert status_de(sessao, recomendada_vencida) == StatusVaga.EXPIRADA
    assert status_de(sessao, pool_valida) == StatusVaga.POOL
    assert status_de(sessao, na_fila) == StatusVaga.FILA
