import signal
import threading

import pytest
from sqlalchemy import text

from job_radar.db import get_engine
from job_radar.worker import main
from job_radar.worker.trava import TravaWorker


@pytest.fixture
def travas():
    criadas = [TravaWorker(get_engine()) for _ in range(2)]
    yield criadas
    for trava in criadas:
        trava.liberar()
    get_engine().dispose()


def derrubar_conexao(trava: TravaWorker) -> None:
    """Simula a queda da conexão da trava (restart do Postgres, rede)."""
    pid = trava._conexao.execute(text("SELECT pg_backend_pid()")).scalar_one()
    with get_engine().connect() as outra:
        outra.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})


def test_so_um_worker_fica_com_a_trava(travas):
    primeiro, segundo = travas
    assert primeiro.tentar()
    assert primeiro.mantida()
    assert not segundo.tentar()
    assert not segundo.mantida()

    primeiro.liberar()
    assert not primeiro.mantida()
    assert segundo.tentar()


def test_conexao_perdida_libera_a_trava(travas):
    primeiro, segundo = travas
    assert primeiro.tentar()
    derrubar_conexao(primeiro)

    assert not primeiro.mantida()
    assert segundo.tentar()


def test_esperar_trava_desiste_quando_pedem_para_encerrar(travas, tmp_path):
    primeiro, segundo = travas
    assert primeiro.tentar()
    parar = threading.Event()
    threading.Timer(0.5, parar.set).start()

    assert not main.esperar_trava(segundo, tmp_path / "hb", parar)
    # enquanto espera, o heartbeat continua (a liveness não mata quem só está aguardando)
    assert main.heartbeat_recente(tmp_path / "hb", max_idade_s=60)


def test_esperar_trava_obtem_quando_o_outro_solta(travas, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ESPERA_TRAVA_S", 0.1)
    primeiro, segundo = travas
    assert primeiro.tentar()
    threading.Timer(0.3, primeiro.liberar).start()

    assert main.esperar_trava(segundo, tmp_path / "hb", threading.Event())
    assert segundo.mantida()


def test_heartbeat_readquire_a_trava_perdida(travas, tmp_path, monkeypatch):
    sinais = []
    monkeypatch.setattr(main.os, "kill", lambda pid, sinal: sinais.append(sinal))
    trava, _ = travas
    assert trava.tentar()
    derrubar_conexao(trava)

    main.job_heartbeat(tmp_path / "hb", trava)

    assert trava.mantida()
    assert sinais == []
    assert main.heartbeat_recente(tmp_path / "hb", max_idade_s=60)


def test_heartbeat_encerra_se_outro_worker_pegou_a_trava(travas, tmp_path, monkeypatch):
    sinais = []
    monkeypatch.setattr(main.os, "kill", lambda pid, sinal: sinais.append(sinal))
    primeiro, segundo = travas
    assert primeiro.tentar()
    derrubar_conexao(primeiro)
    assert segundo.tentar()

    main.job_heartbeat(tmp_path / "hb", primeiro)

    assert sinais == [signal.SIGTERM]
    assert not main.heartbeat_recente(tmp_path / "hb", max_idade_s=60)
