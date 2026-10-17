"""Probes do Kubernetes / healthcheck do compose (RNF10)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from job_radar.db import get_engine

log = logging.getLogger(__name__)

router = APIRouter(tags=["saude"])


def banco_disponivel() -> bool:
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception:
        log.warning("banco indisponível", exc_info=True)
        return False
    return True


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: o processo responde. Não consulta o banco."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(banco_ok: Annotated[bool, Depends(banco_disponivel)]) -> JSONResponse:
    """Readiness: só recebe tráfego com o banco acessível."""
    if not banco_ok:
        return JSONResponse({"status": "indisponivel", "banco": "erro"}, status_code=503)
    return JSONResponse({"status": "ok", "banco": "ok"})
