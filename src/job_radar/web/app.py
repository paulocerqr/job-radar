from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from job_radar import __version__
from job_radar.config import get_settings
from job_radar.web.frontend import Frontend, diretorio_frontend
from job_radar.web.rotas import api, operacao, saude, usuarios, vagas
from job_radar.web.sessao import COOKIE, DURACAO_S, CsrfInvalido, NaoAutenticado, chave_sessao

# Respostas da API (JSON) não executam nada; o frontend tem CSP própria (web/frontend.py)
CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Job Radar", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=chave_sessao(settings),
        session_cookie=COOKIE,
        max_age=DURACAO_S,
        same_site="lax",
        https_only=settings.sessao_cookie_seguro,
    )

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next) -> Response:
        resposta = await call_next(request)
        resposta.headers.setdefault("Content-Security-Policy", CSP)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        return resposta

    @app.exception_handler(NaoAutenticado)
    async def _nao_autenticado(_: Request, __: NaoAutenticado) -> Response:
        return JSONResponse({"erro": "não autenticado"}, status_code=401)

    @app.exception_handler(CsrfInvalido)
    async def _csrf(_: Request, __: CsrfInvalido) -> Response:
        return JSONResponse({"erro": "sessão expirada; recarregue a página"}, status_code=403)

    app.include_router(saude.router)
    app.include_router(api.router)
    app.include_router(vagas.router)
    app.include_router(operacao.router)
    app.include_router(usuarios.router)
    # por último: as rotas da API têm prioridade sobre os arquivos do frontend
    if diretorio := diretorio_frontend(settings.frontend_dir):
        app.mount("/", Frontend(diretorio), name="frontend")
    return app
