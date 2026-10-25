"""API JSON usada pelo frontend (Next.js): sessão e Perfil & Regras."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from job_radar.fila.recalculo import Simulacao, recalcular_pool, simular
from job_radar.models import Perfil, Usuario
from job_radar.seguranca.auth import verificar_senha
from job_radar.web import perfil_json
from job_radar.web.sessao import (
    SessaoDB,
    UsuarioLogado,
    exigir_csrf,
    exigir_json,
    limite_login,
    token_csrf,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])
Corpo = Annotated[dict[str, Any], Body()]
ComCsrf = [Depends(exigir_csrf)]


def _usuario_json(usuario: Usuario) -> dict:
    return {"nome": usuario.nome, "email": usuario.email, "papel": usuario.papel}


@router.get("/sessao")
def sessao(request: Request, usuario: UsuarioLogado) -> dict:
    return {"usuario": _usuario_json(usuario), "csrf": token_csrf(request)}


@router.post("/login", dependencies=[Depends(exigir_json)])
def login(request: Request, corpo: Corpo, sessao_db: SessaoDB) -> JSONResponse:
    email = str(corpo.get("email", "")).strip().lower()
    senha = str(corpo.get("senha", ""))
    ip = request.client.host if request.client else "?"
    chaves = (f"ip:{ip}", f"email:{email}")

    if limite_login.bloqueado(*chaves):
        log.warning("login bloqueado", extra={"ip": ip})
        return JSONResponse({"erro": "Muitas tentativas. Aguarde alguns minutos."}, 429)

    usuario = sessao_db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    if usuario is None or not usuario.ativo or not verificar_senha(usuario.senha_hash, senha):
        limite_login.falhou(*chaves)
        log.warning("login falhou", extra={"ip": ip})
        return JSONResponse({"erro": "E-mail ou senha inválidos."}, 401)

    limite_login.sucesso(*chaves)
    request.session.clear()  # sessão nova no login (evita fixação de sessão)
    request.session["usuario_id"] = str(usuario.id)
    log.info("login", extra={"usuario": str(usuario.id)})
    return JSONResponse({"usuario": _usuario_json(usuario), "csrf": token_csrf(request)})


@router.post("/sair", dependencies=ComCsrf)
def sair(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


def _perfil_de(usuario: Usuario, sessao_db: SessaoDB) -> Perfil:
    if usuario.perfil is None:
        usuario.perfil = Perfil(usuario_id=usuario.id)
        sessao_db.flush()
    return usuario.perfil


@router.get("/perfil")
def perfil_ler(usuario: UsuarioLogado, sessao_db: SessaoDB) -> dict:
    perfil = _perfil_de(usuario, sessao_db)
    return {"perfil": perfil_json.para_json(perfil), "limites": perfil_json.limites()}


@router.put("/perfil", dependencies=ComCsrf)
def perfil_salvar(
    corpo: Corpo, usuario: UsuarioLogado, sessao_db: SessaoDB, recalcular: bool = False
) -> JSONResponse:
    dados = perfil_json.validar(corpo)
    if dados.erros:
        return JSONResponse({"erros": dados.erros}, 422)
    perfil = _perfil_de(usuario, sessao_db)
    for campo in perfil_json.CAMPOS_PERFIL:
        setattr(perfil, campo, getattr(dados, campo))
    recalculadas = None
    if recalcular:
        sessao_db.flush()
        recalculadas = recalcular_pool(sessao_db, usuario.id, perfil)
    sessao_db.commit()
    log.info("perfil salvo", extra={"usuario": str(usuario.id), "recalculadas": recalculadas})
    return JSONResponse({"perfil": perfil_json.para_json(perfil), "recalculadas": recalculadas})


def _simulacao_json(simulacao: Simulacao) -> dict:
    return {
        "avaliadas": simulacao.avaliadas,
        "aprovadas": simulacao.aprovadas,
        "para_fila": simulacao.para_fila,
        "exemplos": [{"nota": nota, "titulo": titulo} for nota, titulo in simulacao.exemplos],
    }


@router.post("/perfil/simular", dependencies=ComCsrf)
def perfil_simular(corpo: Corpo, usuario: UsuarioLogado, sessao_db: SessaoDB) -> JSONResponse:
    """Efeito das regras recebidas (ainda não salvas) no pré-filtro das vagas do banco."""
    dados = perfil_json.validar(corpo)
    if dados.erros:
        return JSONResponse({"erros": dados.erros}, 422)
    atual = simular(sessao_db, _perfil_de(usuario, sessao_db), limite_exemplos=0)
    nova = simular(sessao_db, dados)
    return JSONResponse({"atual": _simulacao_json(atual), "nova": _simulacao_json(nova)})
