import base64
import hashlib

from fastapi.testclient import TestClient

from job_radar.config import get_settings
from job_radar.web.app import create_app
from job_radar.web.frontend import hashes_de_scripts

SCRIPT = "self.__next_f.push([1])"


def build_falso(tmp_path):
    (tmp_path / "_next/static/chunks").mkdir(parents=True)
    (tmp_path / "_next/static/chunks/app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text(
        f'<html><script src="/_next/static/chunks/app.js"></script><script>{SCRIPT}</script></html>'
    )
    return tmp_path


def test_hash_so_dos_scripts_inline(tmp_path):
    esperado = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    assert hashes_de_scripts(build_falso(tmp_path)) == [f"'sha256-{esperado}'"]


def test_api_serve_frontend_com_csp_por_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", str(build_falso(tmp_path)))
    get_settings.cache_clear()
    cliente = TestClient(create_app())

    inicio = cliente.get("/")
    assert inicio.status_code == 200
    csp = inicio.headers["content-security-policy"]
    assert "'sha256-" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]

    estatico = cliente.get("/_next/static/chunks/app.js")
    assert "immutable" in estatico.headers["cache-control"]

    # rotas da API continuam com prioridade e CSP estrita
    assert cliente.get("/healthz").json() == {"status": "ok"}
    api = cliente.get("/api/sessao")
    assert api.status_code == 401
    assert "'sha256-" not in api.headers["content-security-policy"]


def test_redirect_de_diretorio_sem_esquema(tmp_path, monkeypatch):
    build = build_falso(tmp_path)
    (build / "login").mkdir()
    (build / "login/index.html").write_text("<html></html>")
    monkeypatch.setenv("FRONTEND_DIR", str(build))
    get_settings.cache_clear()
    resposta = TestClient(create_app()).get("/login", follow_redirects=False)
    assert resposta.status_code == 307
    assert resposta.headers["location"] == "/login/"


def test_sem_build_do_frontend_nada_e_montado():
    assert TestClient(create_app()).get("/").status_code == 404
