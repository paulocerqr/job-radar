import os
import time
from contextlib import nullcontext

from job_radar.worker.main import gravar_heartbeat, heartbeat_recente, job_auditar


def test_teste_cli_termina_antes_da_auditoria(monkeypatch):
    from job_radar import db
    from job_radar.auditoria import auditor, testes_cli

    ordem = []
    monkeypatch.setattr(db, "nova_sessao", lambda: nullcontext(None))
    monkeypatch.setattr(testes_cli, "executar_teste_pendente", lambda s: ordem.append("teste"))
    monkeypatch.setattr(auditor, "auditar", lambda s: ordem.append("auditoria"))
    job_auditar()
    assert ordem == ["teste", "auditoria"]


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
