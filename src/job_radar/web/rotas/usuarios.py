"""Usuários e convites (Fase 3) e o vínculo do Telegram pela Web UI.

Convite: o admin gera um link de uso único para um e-mail; quem abre define nome e senha.
O token só aparece uma vez (na criação); o banco guarda o hash SHA-256 dele. Tokens
inválidos contam no mesmo bloqueio por IP do login, para não dar para adivinhar.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from job_radar.config import get_settings
from job_radar.models import CanalNotificacao, Convite, Perfil, Usuario
from job_radar.models.enums import Papel, TipoCanal
from job_radar.notificacao.telegram import ClienteTelegram, ErroTelegram
from job_radar.seed import PERFIL_ADMIN_PADRAO
from job_radar.seguranca.auth import gerar_hash_senha
from job_radar.web.sessao import (
    SessaoDB,
    UsuarioLogado,
    exigir_csrf,
    exigir_json,
    limite_login,
    token_csrf,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["usuarios"])
Corpo = Annotated[dict[str, Any], Body()]
ComCsrf = [Depends(exigir_csrf)]
VALIDADE = timedelta(days=7)
SENHA_MINIMA = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _so_admin(usuario: Usuario) -> JSONResponse | None:
    if usuario.papel != Papel.ADMIN:
        return JSONResponse({"erro": "apenas o admin gerencia usuários"}, 403)
    return None


def _situacao(c: Convite, agora: datetime) -> str:
    if c.usado_em:
        return "usado"
    if c.revogado_em:
        return "revogado"
    return "expirado" if c.expira_em <= agora else "pendente"


# ---- admin ----


@router.get("/usuarios")
def listar(usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    agora = datetime.now(UTC)
    usuarios = sessao.scalars(select(Usuario).order_by(Usuario.criado_em)).all()
    convites = sessao.scalars(select(Convite).order_by(Convite.criado_em.desc()).limit(50)).all()
    return JSONResponse(
        {
            "usuarios": [
                {
                    "id": str(u.id),
                    "nome": u.nome,
                    "email": u.email,
                    "papel": u.papel,
                    "ativo": u.ativo,
                    "criado_em": u.criado_em.isoformat(),
                    "eu": u.id == usuario.id,
                }
                for u in usuarios
            ],
            "convites": [
                {
                    "id": str(c.id),
                    "email": c.email,
                    "situacao": _situacao(c, agora),
                    "criado_em": c.criado_em.isoformat(),
                    "expira_em": c.expira_em.isoformat(),
                }
                for c in convites
            ],
        }
    )


@router.post("/convites", dependencies=ComCsrf)
def convidar(corpo: Corpo, usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    email = str(corpo.get("email", "")).strip().lower()
    if "@" not in email or len(email) > 200 or " " in email:
        return JSONResponse({"erro": "e-mail inválido"}, 422)
    if sessao.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        return JSONResponse({"erro": "já existe um usuário com esse e-mail"}, 409)
    agora = datetime.now(UTC)
    for antigo in sessao.scalars(  # um convite pendente por e-mail: o novo substitui o antigo
        select(Convite).where(
            Convite.email == email, Convite.usado_em.is_(None), Convite.revogado_em.is_(None)
        )
    ):
        antigo.revogado_em = agora
    token = secrets.token_urlsafe(32)
    convite = Convite(
        token_hash=_hash(token), email=email, criado_por=usuario.id, expira_em=agora + VALIDADE
    )
    sessao.add(convite)
    sessao.commit()
    log.info("convite criado", extra={"convite": str(convite.id), "por": str(usuario.id)})
    # só o caminho: a origem (https://...) é montada no navegador
    return JSONResponse(
        {"id": str(convite.id), "caminho": f"/convite/?token={token}",
         "expira_em": convite.expira_em.isoformat()},
        201,
    )  # fmt: skip


@router.delete("/convites/{convite_id}", dependencies=ComCsrf)
def revogar(convite_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    convite = sessao.get(Convite, convite_id)
    if convite is None:
        return JSONResponse({"erro": "convite não encontrado"}, 404)
    if convite.usado_em is None and convite.revogado_em is None:
        convite.revogado_em = datetime.now(UTC)
        sessao.commit()
    return JSONResponse({"id": str(convite.id), "situacao": _situacao(convite, datetime.now(UTC))})


@router.patch("/usuarios/{usuario_id}", dependencies=ComCsrf)
def alterar_usuario(
    usuario_id: uuid.UUID, corpo: Corpo, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    alvo = sessao.get(Usuario, usuario_id)
    if alvo is None:
        return JSONResponse({"erro": "usuário não encontrado"}, 404)
    if alvo.id == usuario.id:
        return JSONResponse({"erro": "você não pode desativar a si mesmo"}, 409)
    if not isinstance(corpo.get("ativo"), bool):
        return JSONResponse({"erro": "informe ativo: true ou false"}, 422)
    alvo.ativo = corpo["ativo"]  # desativado: não entra, não recebe vagas nem auditoria
    sessao.commit()
    log.info("usuário alterado", extra={"alvo": str(alvo.id), "ativo": alvo.ativo})
    return JSONResponse({"id": str(alvo.id), "ativo": alvo.ativo})


# ---- público: aceitar convite ----


def _convite_valido(sessao, token: str) -> Convite | None:
    convite = sessao.scalar(select(Convite).where(Convite.token_hash == _hash(token)))
    if convite is None or _situacao(convite, datetime.now(UTC)) != "pendente":
        return None
    return convite


def _ip(request: Request) -> str:
    return f"ip:{request.client.host if request.client else '?'}"


@router.get("/convites/validar")
def validar(
    request: Request, sessao: SessaoDB, token: Annotated[str, Query(max_length=100)]
) -> JSONResponse:
    if limite_login.bloqueado(_ip(request)):
        return JSONResponse({"erro": "Muitas tentativas. Aguarde alguns minutos."}, 429)
    convite = _convite_valido(sessao, token)
    if convite is None:
        limite_login.falhou(_ip(request))
        return JSONResponse({"erro": "Convite inválido, expirado ou já usado."}, 404)
    return JSONResponse({"email": convite.email, "expira_em": convite.expira_em.isoformat()})


@router.post("/convites/aceitar", dependencies=[Depends(exigir_json)])
def aceitar(request: Request, corpo: Corpo, sessao: SessaoDB) -> JSONResponse:
    if limite_login.bloqueado(_ip(request)):
        return JSONResponse({"erro": "Muitas tentativas. Aguarde alguns minutos."}, 429)
    convite = _convite_valido(sessao, str(corpo.get("token", "")))
    if convite is None:
        limite_login.falhou(_ip(request))
        return JSONResponse({"erro": "Convite inválido, expirado ou já usado."}, 404)
    nome = " ".join(str(corpo.get("nome", "")).split())
    senha = str(corpo.get("senha", ""))
    erros = {}
    if not 2 <= len(nome) <= 80:
        erros["nome"] = "Informe seu nome"
    if not SENHA_MINIMA <= len(senha) <= 200:
        erros["senha"] = f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres"
    if erros:
        return JSONResponse({"erros": erros}, 422)
    if sessao.scalar(select(Usuario.id).where(func.lower(Usuario.email) == convite.email)):
        return JSONResponse({"erro": "já existe um usuário com esse e-mail"}, 409)

    novo = Usuario(
        email=convite.email, nome=nome, papel=Papel.USUARIO, senha_hash=gerar_hash_senha(senha)
    )
    sessao.add(novo)
    sessao.flush()
    # perfil inicial igual ao padrão do admin; a pessoa ajusta em Meu perfil
    sessao.add(Perfil(usuario_id=novo.id, **PERFIL_ADMIN_PADRAO))
    convite.usado_em = datetime.now(UTC)
    convite.usuario_id = novo.id
    sessao.commit()
    limite_login.sucesso(_ip(request))
    request.session.clear()
    request.session["usuario_id"] = str(novo.id)
    log.info("convite aceito", extra={"convite": str(convite.id), "usuario": str(novo.id)})
    return JSONResponse(
        {"usuario": {"nome": novo.nome, "email": novo.email, "papel": novo.papel},
         "csrf": token_csrf(request)},
        201,
    )  # fmt: skip


# ---- Telegram do próprio usuário ----


def _canal(sessao, usuario: Usuario) -> CanalNotificacao | None:
    return sessao.scalar(
        select(CanalNotificacao).where(
            CanalNotificacao.usuario_id == usuario.id, CanalNotificacao.tipo == TipoCanal.TELEGRAM
        )
    )


@router.get("/telegram")
def telegram_status(usuario: UsuarioLogado, sessao: SessaoDB) -> dict:
    canal = _canal(sessao, usuario)
    if canal is None:
        situacao = "nao_vinculado"
    elif canal.verificado:
        situacao = "vinculado"
    else:
        situacao = "aguardando"
    return {"configurado": get_settings().telegram_bot_token is not None, "situacao": situacao}


@router.post("/telegram/vincular", dependencies=ComCsrf)
def telegram_vincular(usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    """Mesmo fluxo do `job-radar telegram vincular`: link de uso único com /start <token>."""
    token_bot = get_settings().telegram_bot_token
    if token_bot is None:
        return JSONResponse({"erro": "o bot do Telegram não está configurado"}, 409)
    try:
        bot = ClienteTelegram(token_bot.get_secret_value()).eu()
    except ErroTelegram:
        log.exception("Telegram indisponível ao gerar vínculo")
        return JSONResponse({"erro": "não foi possível falar com o Telegram"}, 502)
    canal = _canal(sessao, usuario)
    if canal is None:
        canal = CanalNotificacao(usuario_id=usuario.id, tipo=TipoCanal.TELEGRAM)
        sessao.add(canal)
    canal.token_vinculo = secrets.token_urlsafe(16)
    sessao.commit()
    return JSONResponse({"link": f"https://t.me/{bot['username']}?start={canal.token_vinculo}"})
