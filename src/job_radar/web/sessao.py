"""Sessão da Web UI: login, CSRF e limite de tentativas.

A sessão é um cookie assinado (SessionMiddleware do Starlette, itsdangerous) que guarda só
o id do usuário e o token CSRF. A UI fica exposta na internet pelo túnel, então todo POST
exige o token CSRF e o login bloqueia depois de várias falhas.
"""

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from job_radar.config import Settings
from job_radar.db import nova_sessao
from job_radar.models import Usuario

log = logging.getLogger(__name__)

COOKIE = "jr_sessao"
DURACAO_S = 7 * 24 * 3600
MAX_FALHAS = 5
BLOQUEIO_S = 300


def chave_sessao(settings: Settings) -> str:
    if settings.sessao_secret:
        return settings.sessao_secret.get_secret_value()
    if settings.fernet_key:
        # chave própria para a sessão, derivada (não é a chave Fernet em si)
        return hmac.new(
            settings.fernet_key.get_secret_value().encode(), b"job-radar:sessao", hashlib.sha256
        ).hexdigest()
    log.warning("sem SESSAO_SECRET nem FERNET_KEY: sessões não sobrevivem a um restart")
    return secrets.token_hex(32)


class NaoAutenticado(Exception):
    pass


class CsrfInvalido(Exception):
    pass


def token_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def exigir_json(request: Request) -> None:
    """Formulário de outro site não consegue mandar JSON sem preflight de CORS (que a API
    não libera): exigir o Content-Type já barra CSRF por formulário."""
    tipo = request.headers.get("content-type", "").split(";")[0].strip()
    if tipo != "application/json":
        raise CsrfInvalido


def exigir_csrf(request: Request) -> None:
    """Toda escrita autenticada: JSON + cabeçalho X-CSRF-Token igual ao da sessão."""
    exigir_json(request)
    esperado = request.session.get("csrf")
    recebido = request.headers.get("x-csrf-token")
    if not esperado or not recebido or not secrets.compare_digest(esperado, recebido):
        raise CsrfInvalido


def sessao_db():
    with nova_sessao() as sessao:
        yield sessao


SessaoDB = Annotated[Session, Depends(sessao_db)]


def usuario_logado(request: Request, sessao: SessaoDB) -> Usuario:
    bruto = request.session.get("usuario_id")
    usuario = sessao.get(Usuario, uuid.UUID(bruto)) if bruto else None
    if usuario is None or not usuario.ativo:
        request.session.pop("usuario_id", None)
        raise NaoAutenticado
    return usuario


UsuarioLogado = Annotated[Usuario, Depends(usuario_logado)]


class LimiteLogin:
    """Bloqueia por IP e por e-mail depois de MAX_FALHAS falhas seguidas.

    Em memória, por processo: com 2 réplicas da API, o limite efetivo dobra. Suficiente
    para um app de um usuário; o argon2 já torna cada tentativa cara.
    """

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._falhas: dict[str, tuple[int, float]] = {}

    def bloqueado(self, *chaves: str) -> bool:
        agora = self._relogio()
        return any(
            n >= MAX_FALHAS and agora < ate
            for n, ate in (self._falhas.get(c, (0, 0.0)) for c in chaves)
        )

    def falhou(self, *chaves: str) -> None:
        agora = self._relogio()
        for chave in chaves:
            n, ate = self._falhas.get(chave, (0, 0.0))
            if n >= MAX_FALHAS and agora >= ate:
                n = 0  # bloqueio expirou: recomeça a contagem
            self._falhas[chave] = (n + 1, agora + BLOQUEIO_S)

    def sucesso(self, *chaves: str) -> None:
        for chave in chaves:
            self._falhas.pop(chave, None)


limite_login = LimiteLogin()
