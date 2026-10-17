from fastapi import FastAPI

from job_radar import __version__
from job_radar.web.rotas import saude


def create_app() -> FastAPI:
    app = FastAPI(title="Job Radar", version=__version__)
    app.include_router(saude.router)
    return app
