from typer.testing import CliRunner

from job_radar.cli import app
from job_radar.worker.main import gravar_heartbeat

runner = CliRunner()


def test_coletar_fonte_desconhecida_sai_com_2():
    resultado = runner.invoke(app, ["coletar", "nao-existe"])
    assert resultado.exit_code == 2


def test_worker_saude_sem_heartbeat_sai_com_1():
    assert runner.invoke(app, ["worker-saude"]).exit_code == 1


def test_worker_saude_com_heartbeat_sai_com_0(tmp_path):
    gravar_heartbeat(tmp_path / "heartbeat")  # mesmo caminho definido no conftest
    assert runner.invoke(app, ["worker-saude"]).exit_code == 0
