"""API de operação: fontes de coleta e providers de IA.

As fontes são globais (valem para todos os usuários): alterar ou disparar coleta é só
para admin. "Coletar agora" roda na própria API, em segundo plano, com o mesmo código
dos CronJobs; uma coleta "rodando" há menos de 15 min bloqueia outra da mesma fonte.
"""

import logging
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from job_radar.auditoria.providers import ProviderOpenAICompativel, construir_provider
from job_radar.auditoria.providers.base import ErroProvider, RespostaInvalida, extrair_json
from job_radar.auditoria.testes_cli import resultado_teste
from job_radar.coleta.base import fontes_registradas
from job_radar.coleta.execucao import executar_coleta
from job_radar.coleta.fontes.jobspy import ConfigJobSpy
from job_radar.db import nova_sessao
from job_radar.models import ExecucaoColeta, Fonte, ProviderIA, UsoProvider, Usuario
from job_radar.models.enums import Papel, StatusExecucao, TipoProvider
from job_radar.seguranca.cripto import ChaveFernetAusente, ChaveFernetInvalida, cifrar, mascarar
from job_radar.web import providers_web
from job_radar.web.sessao import SessaoDB, UsuarioLogado, exigir_csrf

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operacao"])
ComCsrf = [Depends(exigir_csrf)]
JANELA_RODANDO = timedelta(minutes=15)


def _so_admin(usuario: Usuario) -> JSONResponse | None:
    if usuario.papel != Papel.ADMIN:
        return JSONResponse({"erro": "apenas o admin altera as fontes"}, 403)
    return None


def _execucao_json(e: ExecucaoColeta) -> dict:
    return {
        "id": str(e.id),
        "fonte_id": e.fonte_id,
        "iniciada_em": e.iniciada_em.isoformat(),
        "finalizada_em": e.finalizada_em.isoformat() if e.finalizada_em else None,
        "status": e.status,
        "coletadas": e.itens_coletados,
        "novas": e.itens_novos,
        "duplicadas": e.itens_duplicados,
        "erro": e.erro,
    }


def _rodando(sessao, fonte_id: str) -> bool:
    return bool(
        sessao.scalar(
            select(func.count())
            .select_from(ExecucaoColeta)
            .where(
                ExecucaoColeta.fonte_id == fonte_id,
                ExecucaoColeta.status == StatusExecucao.RODANDO,
                ExecucaoColeta.iniciada_em > datetime.now(UTC) - JANELA_RODANDO,
            )
        )
    )


@router.get("/fontes")
def fontes(usuario: UsuarioLogado, sessao: SessaoDB) -> dict:
    registradas = set(fontes_registradas())
    execucoes = sessao.scalars(
        select(ExecucaoColeta).order_by(ExecucaoColeta.iniciada_em.desc()).limit(30)
    ).all()
    ultima = {
        e.fonte_id: e
        for e in sessao.scalars(
            select(ExecucaoColeta)
            .order_by(ExecucaoColeta.fonte_id, ExecucaoColeta.iniciada_em.desc())
            .ext(distinct_on(ExecucaoColeta.fonte_id))
        )
    }
    lista = []
    for f in sessao.scalars(select(Fonte).order_by(Fonte.ativa.desc(), Fonte.nome)):
        lista.append(
            {
                "id": f.id,
                "nome": f.nome,
                "ativa": f.ativa,
                "implementada": f.id in registradas,
                "intervalo_min": f.intervalo_min,
                "max_itens": f.max_itens_execucao,
                "confiabilidade": f.confiabilidade,
                "config": f.config,
                "ultima": _execucao_json(ultima[f.id]) if f.id in ultima else None,
            }
        )
    return {
        "fontes": lista,
        "execucoes": [_execucao_json(e) for e in execucoes],
        "pode_alterar": usuario.papel == Papel.ADMIN,
    }


@router.patch("/fontes/{fonte_id}", dependencies=ComCsrf)
def alterar_fonte(
    fonte_id: str, corpo: Annotated[dict[str, Any], Body()], usuario: UsuarioLogado,
    sessao: SessaoDB,
) -> JSONResponse:  # fmt: skip
    if negado := _so_admin(usuario):
        return negado
    fonte = sessao.get(Fonte, fonte_id)
    if fonte is None:
        return JSONResponse({"erro": "fonte não encontrada"}, 404)
    if not isinstance(corpo.get("ativa"), bool):
        return JSONResponse({"erro": "informe ativa: true ou false"}, 422)
    fonte.ativa = corpo["ativa"]
    sessao.commit()
    log.info("fonte alterada", extra={"fonte": fonte_id, "ativa": fonte.ativa})
    return JSONResponse({"id": fonte.id, "ativa": fonte.ativa})


class EditarBuscasJobSpy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: ConfigJobSpy
    max_itens: int = Field(ge=1, le=50, strict=True)


@router.put("/fontes/jobspy/buscas", dependencies=ComCsrf)
def editar_buscas_jobspy(
    corpo: Annotated[dict[str, Any], Body()], usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    fonte = sessao.get(Fonte, "jobspy")
    if fonte is None:
        return JSONResponse({"erro": "fonte não encontrada"}, 404)
    try:
        dados = EditarBuscasJobSpy.model_validate(corpo)
    except ValidationError:
        return JSONResponse(
            {"erro": "Configuração inválida. Confira os campos e limites informados."}, 422
        )
    if _rodando(sessao, fonte.id):
        return JSONResponse(
            {"erro": "Aguarde a coleta em andamento terminar para editar as buscas."}, 409
        )
    fonte.config = dados.config.model_dump()
    fonte.max_itens_execucao = dados.max_itens
    sessao.commit()
    log.info("buscas do LinkedIn alteradas", extra={"fonte": fonte.id})
    return JSONResponse({"config": fonte.config, "max_itens": fonte.max_itens_execucao})


def _coletar_em_segundo_plano(fonte_id: str) -> None:
    with nova_sessao() as sessao:
        executar_coleta(sessao, fonte_id)


@router.post("/fontes/{fonte_id}/coletar", dependencies=ComCsrf)
def coletar_agora(
    fonte_id: str, tarefas: BackgroundTasks, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    if negado := _so_admin(usuario):
        return negado
    fonte = sessao.get(Fonte, fonte_id)
    if fonte is None or fonte_id not in fontes_registradas():
        return JSONResponse({"erro": "fonte não encontrada ou sem coletor"}, 404)
    if not fonte.ativa:
        return JSONResponse({"erro": "fonte desativada"}, 409)
    if _rodando(sessao, fonte_id):
        return JSONResponse({"erro": "já há uma coleta desta fonte em andamento"}, 409)
    tarefas.add_task(_coletar_em_segundo_plano, fonte_id)
    log.info("coleta manual disparada", extra={"fonte": fonte_id, "usuario": str(usuario.id)})
    return JSONResponse({"ok": True}, 202)


# ---- providers de IA (por usuário) ----


def _provider_json(p: ProviderIA, uso_hoje: UsoProvider | None, uso_7d: dict) -> dict:
    return {
        "id": str(p.id),
        "nome": p.nome,
        "tipo": p.tipo,
        "modelo": p.modelo,
        "base_url": p.base_url,
        "chave": f"…{p.api_key_sufixo}" if p.api_key_sufixo else None,
        "prioridade": p.prioridade,
        "ativo": p.ativo,
        "tamanho_lote": p.tamanho_lote,
        "rpm": p.rpm,
        "rpd": p.rpd,
        "timeout_s": p.timeout_s,
        "ultimo_erro": p.ultimo_erro,
        "ultimo_erro_em": p.ultimo_erro_em.isoformat() if p.ultimo_erro_em else None,
        "hoje": {
            "requisicoes": uso_hoje.requisicoes if uso_hoje else 0,
            "tokens_entrada": uso_hoje.tokens_entrada if uso_hoje else 0,
            "tokens_saida": uso_hoje.tokens_saida if uso_hoje else 0,
            "erros": uso_hoje.erros if uso_hoje else 0,
        },
        "ultimos_7_dias": uso_7d,
    }


def _providers(sessao, usuario: Usuario) -> list[ProviderIA]:
    return list(
        sessao.scalars(
            select(ProviderIA)
            .where(ProviderIA.usuario_id == usuario.id)
            .order_by(ProviderIA.prioridade)
        )
    )


@router.get("/providers")
def providers(usuario: UsuarioLogado, sessao: SessaoDB) -> dict:
    lista = _providers(sessao, usuario)
    hoje = date.today()
    usos = sessao.scalars(
        select(UsoProvider).where(
            UsoProvider.provider_id.in_([p.id for p in lista]),
            UsoProvider.dia > hoje - timedelta(days=7),
        )
    ).all()
    uso_hoje = {u.provider_id: u for u in usos if u.dia == hoje}
    uso_7d: dict[uuid.UUID, dict] = {}
    for u in usos:
        soma = uso_7d.setdefault(u.provider_id, {"requisicoes": 0, "tokens": 0, "erros": 0})
        soma["requisicoes"] += u.requisicoes
        soma["tokens"] += u.tokens_entrada + u.tokens_saida
        soma["erros"] += u.erros
    vazio = {"requisicoes": 0, "tokens": 0, "erros": 0}
    return {
        "providers": [_provider_json(p, uso_hoje.get(p.id), uso_7d.get(p.id, vazio)) for p in lista]
    }


def _do_usuario(sessao, usuario: Usuario, provider_id: uuid.UUID) -> ProviderIA | None:
    p = sessao.get(ProviderIA, provider_id)
    return p if p is not None and p.usuario_id == usuario.id else None


@router.post("/providers/{provider_id}/testar", dependencies=ComCsrf)
def testar_provider(
    provider_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    config = _do_usuario(sessao, usuario, provider_id)
    if config is None:
        return JSONResponse({"erro": "provider não encontrado"}, 404)
    if config.tipo == TipoProvider.CLI:
        if usuario.papel != Papel.ADMIN:
            return JSONResponse({"erro": "provider CLI é exclusivo do admin"}, 403)
        teste = resultado_teste(config)
        if not teste or not teste.get("pendente"):
            config = sessao.scalar(
                select(ProviderIA)
                .where(ProviderIA.id == config.id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
            if config is None:
                return JSONResponse({"erro": "provider ocupado; tente novamente"}, 409)
            teste = resultado_teste(config)
            if not teste or not teste.get("pendente"):
                teste = {"pendente": True, "solicitado_em": datetime.now(UTC).isoformat()}
                config.teste_conexao = teste
                sessao.commit()
        return JSONResponse(teste, 202)
    inicio = time.monotonic()
    try:
        resposta = construir_provider(config).completar(
            'Responda somente com o objeto JSON {"ok": true}.', "teste de conexão"
        )
        extrair_json(resposta.texto)
    # chave que não decifra (FERNET_KEY trocada ou ausente) também é falha de configuração
    except (ErroProvider, RespostaInvalida, ChaveFernetAusente, ChaveFernetInvalida) as erro:
        return JSONResponse({"ok": False, "erro": str(erro)[:300]})
    return JSONResponse(
        {"ok": True, "segundos": round(time.monotonic() - inicio, 1), "modelo": resposta.modelo}
    )


@router.get("/providers/{provider_id}/teste")
def consultar_teste_provider(
    provider_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    config = _do_usuario(sessao, usuario, provider_id)
    if config is None:
        return JSONResponse({"erro": "provider não encontrado"}, 404)
    return JSONResponse(
        resultado_teste(config) or {"erro": "nenhum teste solicitado"},
        200 if config.teste_conexao else 404,
    )


@router.get("/providers/presets")
def presets(usuario: UsuarioLogado) -> dict:
    return {
        "presets": {
            nome: {"base_url": p.base_url, "modelo": p.modelo, "rpm": p.rpm, "rpd": p.rpd,
                   "tamanho_lote": p.tamanho_lote, "timeout_s": p.timeout_s}
            for nome, p in providers_web.PRESETS_WEB.items()
        }
    }  # fmt: skip


@router.post("/providers", dependencies=ComCsrf)
def criar_provider(
    corpo: Annotated[dict[str, Any], Body()], usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    campos, erros = providers_web.validar(corpo, novo=True)
    if not erros and sessao.scalar(
        select(ProviderIA.id).where(
            ProviderIA.usuario_id == usuario.id, ProviderIA.nome == campos["nome"]
        )
    ):
        erros["nome"] = "Você já tem um provider com esse nome"
    if erros:
        return JSONResponse({"erros": erros}, 422)
    chave = campos.pop("api_key")
    try:
        cifrada = cifrar(chave)
    except ChaveFernetAusente:
        return JSONResponse({"erro": "FERNET_KEY não configurada no servidor"}, 409)
    maior = sessao.scalar(
        select(func.max(ProviderIA.prioridade)).where(ProviderIA.usuario_id == usuario.id)
    )
    provider = ProviderIA(
        usuario_id=usuario.id, tipo=TipoProvider.OPENAI_COMPATIBLE, prioridade=(maior or 0) + 1,
        api_key_cifrada=cifrada, api_key_sufixo=mascarar(chave), **campos,
    )  # fmt: skip
    sessao.add(provider)
    sessao.commit()
    log.info("provider criado", extra={"provider": str(provider.id), "usuario": str(usuario.id)})
    return JSONResponse({"id": str(provider.id)}, 201)


@router.patch("/providers/{provider_id}", dependencies=ComCsrf)
def alterar_provider(
    provider_id: uuid.UUID, corpo: Annotated[dict[str, Any], Body()], usuario: UsuarioLogado,
    sessao: SessaoDB,
) -> JSONResponse:  # fmt: skip
    """Ativar/desativar e editar modelo, URL, limites ou trocar a chave (sem reenviar a antiga)."""
    config = _do_usuario(sessao, usuario, provider_id)
    if config is None:
        return JSONResponse({"erro": "provider não encontrado"}, 404)
    if "ativo" in corpo and not isinstance(corpo["ativo"], bool):
        return JSONResponse({"erros": {"ativo": "true ou false"}}, 422)
    if config.tipo == TipoProvider.CLI and set(corpo) - {"ativo"}:
        return JSONResponse({"erro": "provider CLI só é editado pelo terminal"}, 409)
    campos, erros = providers_web.validar(corpo, novo=False)
    if erros:
        return JSONResponse({"erros": erros}, 422)
    if chave := campos.pop("api_key", None):
        config.api_key_cifrada, config.api_key_sufixo = cifrar(chave), mascarar(chave)
    for campo, valor in campos.items():
        setattr(config, campo, valor)
    if "ativo" in corpo:
        config.ativo = corpo["ativo"]
    if campos or chave or config.ativo:  # mudou algo ou reativou: nova chance
        config.ultimo_erro = None
        config.ultimo_erro_em = None
    sessao.commit()
    return JSONResponse({"id": str(config.id), "ativo": config.ativo})


@router.delete("/providers/{provider_id}", dependencies=ComCsrf)
def remover_provider(
    provider_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    config = _do_usuario(sessao, usuario, provider_id)
    if config is None:
        return JSONResponse({"erro": "provider não encontrado"}, 404)
    sessao.delete(config)
    sessao.commit()
    log.info("provider removido", extra={"provider": str(provider_id), "usuario": str(usuario.id)})
    return JSONResponse({"ok": True})


@router.get("/providers/{provider_id}/modelos")
def modelos_provider(
    provider_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    """Modelos disponíveis para a chave salva (endpoint /models do provider)."""
    config = _do_usuario(sessao, usuario, provider_id)
    if config is None or config.tipo != TipoProvider.OPENAI_COMPATIBLE:
        return JSONResponse({"erro": "provider não encontrado"}, 404)
    try:
        provider = construir_provider(config)
        if not isinstance(provider, ProviderOpenAICompativel):
            return JSONResponse({"erro": "provider sem lista de modelos"}, 409)
        return JSONResponse({"modelos": sorted(provider.listar_modelos())})
    except (ErroProvider, ChaveFernetAusente, ChaveFernetInvalida) as erro:
        return JSONResponse({"erro": str(erro)[:300]}, 502)


@router.put("/providers/ordem", dependencies=ComCsrf)
def ordenar_providers(
    corpo: Annotated[dict[str, Any], Body()], usuario: UsuarioLogado, sessao: SessaoDB
) -> JSONResponse:
    """Recebe todos os ids na ordem desejada; o primeiro passa a ter prioridade 1."""
    lista = _providers(sessao, usuario)
    por_id = {str(p.id): p for p in lista}
    ids = corpo.get("ids")
    if not isinstance(ids, list) or sorted(map(str, ids)) != sorted(por_id):
        return JSONResponse({"erro": "envie todos os ids dos seus providers"}, 422)
    # prioridade é única por usuário: passa por valores negativos para não colidir
    for i, p in enumerate(lista, start=1):
        p.prioridade = -i
    sessao.flush()
    for i, id_ in enumerate(ids, start=1):
        por_id[str(id_)].prioridade = i
    sessao.commit()
    return JSONResponse({"ids": [str(i) for i in ids]})
