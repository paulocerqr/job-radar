"""Páginas da Web UI (Jinja2 + HTMX): login e Perfil & Regras."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from job_radar.fila.recalculo import recalcular_pool, simular
from job_radar.models import Perfil, Usuario
from job_radar.seguranca.auth import verificar_senha
from job_radar.web.formulario_perfil import (
    CAMPOS_PERFIL,
    LIMITE_CURRICULO,
    LIMITE_INSTRUCOES,
    NIVEIS_EDITAVEIS,
    DadosPerfil,
    ler_formulario,
    localidades_para_texto,
)
from job_radar.web.sessao import (
    SessaoDB,
    UsuarioLogado,
    exigir_csrf,
    limite_login,
    token_csrf,
)

log = logging.getLogger(__name__)

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
router = APIRouter()
ComCsrf = [Depends(exigir_csrf)]


def _pagina(request: Request, nome: str, status_code: int = 200, **contexto) -> HTMLResponse:
    contexto.setdefault("usuario", None)
    return templates.TemplateResponse(
        request, nome, {"csrf": token_csrf(request), **contexto}, status_code=status_code
    )


@router.get("/", include_in_schema=False)
def inicio() -> RedirectResponse:
    return RedirectResponse("/perfil", status_code=303)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request) -> HTMLResponse:
    return _pagina(request, "login.html")


@router.post("/login", include_in_schema=False, dependencies=ComCsrf)
async def login(request: Request, sessao: SessaoDB) -> Response:
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    senha = str(form.get("senha", ""))
    ip = request.client.host if request.client else "?"
    chaves = (f"ip:{ip}", f"email:{email}")

    if limite_login.bloqueado(*chaves):
        log.warning("login bloqueado", extra={"ip": ip})
        return _pagina(
            request, "login.html", 429, erro="Muitas tentativas. Aguarde alguns minutos.",
            email=email,
        )  # fmt: skip

    usuario = sessao.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    if usuario is None or not usuario.ativo or not verificar_senha(usuario.senha_hash, senha):
        limite_login.falhou(*chaves)
        log.warning("login falhou", extra={"ip": ip})
        return _pagina(request, "login.html", 401, erro="E-mail ou senha inválidos.", email=email)

    limite_login.sucesso(*chaves)
    request.session.clear()  # sessão nova no login (evita fixação de sessão)
    request.session["usuario_id"] = str(usuario.id)
    token_csrf(request)
    log.info("login", extra={"usuario": str(usuario.id)})
    return RedirectResponse("/perfil", status_code=303)


@router.post("/sair", include_in_schema=False, dependencies=ComCsrf)
def sair(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def _contexto_perfil(perfil: Perfil | DadosPerfil) -> dict:
    return {
        "p": perfil,
        "palavras_chave_txt": "\n".join(perfil.palavras_chave),
        "palavras_excluidas_txt": "\n".join(perfil.palavras_excluidas),
        "localidades_txt": localidades_para_texto(perfil.localidades),
        "niveis_editaveis": NIVEIS_EDITAVEIS,
        "limite_curriculo": LIMITE_CURRICULO,
        "limite_instrucoes": LIMITE_INSTRUCOES,
    }


def _perfil_de(usuario: Usuario, sessao: SessaoDB) -> Perfil:
    if usuario.perfil is None:
        usuario.perfil = Perfil(usuario_id=usuario.id)
        sessao.flush()
    return usuario.perfil


@router.get("/perfil", response_class=HTMLResponse, include_in_schema=False)
def perfil_form(request: Request, usuario: UsuarioLogado, sessao: SessaoDB) -> HTMLResponse:
    perfil = _perfil_de(usuario, sessao)
    return _pagina(request, "perfil.html", usuario=usuario, **_contexto_perfil(perfil))


@router.post("/perfil", include_in_schema=False, dependencies=ComCsrf)
async def perfil_salvar(request: Request, usuario: UsuarioLogado, sessao: SessaoDB) -> Response:
    form = await request.form()
    dados = ler_formulario(form)
    if dados.erros:
        return _pagina(
            request, "perfil.html", 422, usuario=usuario, erros=dados.erros,
            **_contexto_perfil(dados),
        )  # fmt: skip

    perfil = _perfil_de(usuario, sessao)
    for campo in CAMPOS_PERFIL:
        setattr(perfil, campo, getattr(dados, campo))
    recalculadas = None
    if form.get("recalcular_pool") == "on":
        sessao.flush()
        recalculadas = recalcular_pool(sessao, usuario.id, perfil)
    sessao.commit()
    log.info("perfil salvo", extra={"usuario": str(usuario.id), "recalculadas": recalculadas})
    return _pagina(
        request, "perfil.html", usuario=usuario, salvo=True, recalculadas=recalculadas,
        **_contexto_perfil(perfil),
    )  # fmt: skip


@router.post(
    "/perfil/simular", response_class=HTMLResponse, include_in_schema=False, dependencies=ComCsrf
)
async def perfil_simular(
    request: Request, usuario: UsuarioLogado, sessao: SessaoDB
) -> HTMLResponse:
    """Fragmento HTMX: efeito das regras do formulário (ainda não salvas) no pré-filtro."""
    dados = ler_formulario(await request.form())
    atual = simular(sessao, _perfil_de(usuario, sessao), limite_exemplos=0)
    nova = simular(sessao, dados)
    return _pagina(request, "_simulacao.html", atual=atual, nova=nova, erros=dados.erros)
