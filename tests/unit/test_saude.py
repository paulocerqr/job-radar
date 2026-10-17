from fastapi.testclient import TestClient

from job_radar.web.app import create_app
from job_radar.web.rotas.saude import banco_disponivel


def cliente(banco_ok: bool) -> TestClient:
    app = create_app()
    app.dependency_overrides[banco_disponivel] = lambda: banco_ok
    return TestClient(app)


def test_healthz_nao_depende_do_banco():
    resposta = cliente(banco_ok=False).get("/healthz")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_readyz_ok_com_banco():
    resposta = cliente(banco_ok=True).get("/readyz")
    assert resposta.status_code == 200
    assert resposta.json()["banco"] == "ok"


def test_readyz_503_sem_banco():
    resposta = cliente(banco_ok=False).get("/readyz")
    assert resposta.status_code == 503
