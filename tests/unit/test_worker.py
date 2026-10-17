import os
import time

from job_radar.worker.main import gravar_heartbeat, heartbeat_recente


def test_heartbeat_inexistente(tmp_path):
    assert not heartbeat_recente(tmp_path / "nao-existe", max_idade_s=60)


def test_heartbeat_recente(tmp_path):
    caminho = tmp_path / "hb"
    gravar_heartbeat(caminho)
    assert heartbeat_recente(caminho, max_idade_s=60)


def test_heartbeat_antigo(tmp_path):
    caminho = tmp_path / "hb"
    gravar_heartbeat(caminho)
    antigo = time.time() - 600
    os.utime(caminho, (antigo, antigo))
    assert not heartbeat_recente(caminho, max_idade_s=60)
