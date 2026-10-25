"""API das vagas para o frontend: resumo da Visão geral, lista, detalhe e decisões.

Confirmar e ignorar usam a mesma máquina de estados do Telegram (fila/estados.py);
uma vaga decidida aqui aparece como já decidida se o botão do Telegram for usado depois.
"""

import uuid
from datetime import datetime, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from job_radar.config import get_settings
from job_radar.fila.estados import TransicaoInvalida, transicionar
from job_radar.models import (
    Auditoria,
    ExecucaoColeta,
    Fonte,
    HistoricoStatus,
    Usuario,
    Vaga,
    VagaFonte,
    VagaUsuario,
)
from job_radar.models.enums import OrigemTransicao, StatusVaga
from job_radar.notificacao.mensagens import MOTIVOS_IGNORAR
from job_radar.web.sessao import SessaoDB, UsuarioLogado, exigir_csrf

router = APIRouter(prefix="/api", tags=["vagas"])
ComCsrf = [Depends(exigir_csrf)]
POR_PAGINA = 25
LIMITE_DESCRICAO = 20_000

# ordem de cada aba: o que importa primeiro para decidir
_ORDEM = {
    StatusVaga.RECOMENDADA: [
        VagaUsuario.score_ia.desc().nulls_last(),
        VagaUsuario.status_em.desc(),
    ],
    StatusVaga.FILA: [VagaUsuario.score_prefiltro.desc()],
    StatusVaga.POOL: [VagaUsuario.score_prefiltro.desc()],
}


def _inicio_do_dia() -> datetime:
    fuso = ZoneInfo(get_settings().tz)
    return datetime.combine(datetime.now(fuso).date(), time.min, tzinfo=fuso)


def _auditorias(sessao: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Resultado da última auditoria bem-sucedida de cada vaga_usuario (DISTINCT ON)."""
    if not ids:
        return {}
    linhas = sessao.execute(
        select(
            Auditoria.vaga_usuario_id, Auditoria.resultado, Auditoria.modelo, Auditoria.criado_em
        )
        .where(Auditoria.vaga_usuario_id.in_(ids), Auditoria.sucesso)
        .order_by(Auditoria.vaga_usuario_id, Auditoria.criado_em.desc())
        .ext(distinct_on(Auditoria.vaga_usuario_id))
    )
    return {
        vu_id: {"resultado": resultado or {}, "modelo": modelo, "em": em.isoformat()}
        for vu_id, resultado, modelo, em in linhas
    }


def _fontes(sessao: Session, vaga_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    resultado: dict[uuid.UUID, list[str]] = {}
    if vaga_ids:
        linhas = sessao.execute(
            select(VagaFonte.vaga_id, Fonte.nome)
            .join(Fonte, Fonte.id == VagaFonte.fonte_id)
            .where(VagaFonte.vaga_id.in_(vaga_ids))
            .order_by(Fonte.nome)
        )
        for vaga_id, nome in linhas:
            resultado.setdefault(vaga_id, []).append(nome)
    return resultado


def _item(vu: VagaUsuario, vaga: Vaga, auditoria: dict | None, fontes: list[str]) -> dict:
    resultado = (auditoria or {}).get("resultado", {})
    return {
        "id": str(vu.id),
        "titulo": vaga.titulo,
        "empresa": vaga.empresa,
        "cidade": vaga.cidade,
        "uf": vaga.uf,
        "modalidade": vaga.modalidade,
        "nivel": vaga.nivel,
        "url": vaga.url_canonica,
        "fontes": fontes,
        "publicada_em": vaga.publicada_em.isoformat() if vaga.publicada_em else None,
        "status": vu.status,
        "status_em": vu.status_em.isoformat(),
        "score_prefiltro": vu.score_prefiltro,
        "score_ia": vu.score_ia,
        "area": resultado.get("area"),
        "resumo": resultado.get("resumo"),
        "motivo_usuario": vu.motivo_usuario,
    }


def _da_pessoa(sessao: Session, usuario: Usuario, vaga_usuario_id: uuid.UUID) -> VagaUsuario | None:
    vu = sessao.get(VagaUsuario, vaga_usuario_id)
    return vu if vu is not None and vu.usuario_id == usuario.id else None


@router.get("/resumo")
def resumo(usuario: UsuarioLogado, sessao: SessaoDB) -> dict:
    contagens = dict(
        sessao.execute(
            select(VagaUsuario.status, func.count())
            .where(VagaUsuario.usuario_id == usuario.id)
            .group_by(VagaUsuario.status)
        ).all()
    )
    hoje = _inicio_do_dia()
    recomendadas_hoje = sessao.scalar(
        select(func.count())
        .select_from(HistoricoStatus)
        .join(VagaUsuario, VagaUsuario.id == HistoricoStatus.vaga_usuario_id)
        .where(
            VagaUsuario.usuario_id == usuario.id,
            HistoricoStatus.para == StatusVaga.RECOMENDADA,
            HistoricoStatus.criado_em >= hoje,
        )
    )
    vagas_novas_hoje = sessao.scalar(
        select(func.coalesce(func.sum(ExecucaoColeta.itens_novos), 0)).where(
            ExecucaoColeta.iniciada_em >= hoje
        )
    )

    ultima = (
        select(ExecucaoColeta)
        .order_by(ExecucaoColeta.fonte_id, ExecucaoColeta.iniciada_em.desc())
        .ext(distinct_on(ExecucaoColeta.fonte_id))
        .subquery()
    )
    fontes = [
        {
            "id": fonte.id,
            "nome": fonte.nome,
            "iniciada_em": iniciada.isoformat() if iniciada else None,
            "status": status,
            "coletadas": coletadas,
            "novas": novas,
            "erro": erro,
        }
        for fonte, iniciada, status, coletadas, novas, erro in sessao.execute(
            select(
                Fonte,
                ultima.c.iniciada_em,
                ultima.c.status,
                ultima.c.itens_coletados,
                ultima.c.itens_novos,
                ultima.c.erro,
            )
            .outerjoin(ultima, ultima.c.fonte_id == Fonte.id)
            .where(Fonte.ativa)
            .order_by(Fonte.nome)
        )
    ]

    atividade = [
        {
            "vaga_id": str(h.vaga_usuario_id),
            "titulo": titulo,
            "de": h.de,
            "para": h.para,
            "origem": h.origem,
            "detalhe": h.detalhe,
            "em": h.criado_em.isoformat(),
        }
        for h, titulo in sessao.execute(
            select(HistoricoStatus, Vaga.titulo)
            .join(VagaUsuario, VagaUsuario.id == HistoricoStatus.vaga_usuario_id)
            .join(Vaga, Vaga.id == VagaUsuario.vaga_id)
            .where(
                VagaUsuario.usuario_id == usuario.id,
                HistoricoStatus.para.in_(
                    [StatusVaga.RECOMENDADA, StatusVaga.CONFIRMADA, StatusVaga.IGNORADA]
                ),
            )
            .order_by(HistoricoStatus.criado_em.desc())
            .limit(8)
        )
    ]

    return {
        "contagens": {s.value: contagens.get(s.value, 0) for s in StatusVaga},
        "limites": {"fila": usuario.limite_fila, "recomendadas": usuario.limite_recomendadas},
        "recomendadas_hoje": recomendadas_hoje,
        "vagas_novas_hoje": vagas_novas_hoje,
        "fontes": fontes,
        "atividade": atividade,
        "motivos_ignorar": MOTIVOS_IGNORAR,
    }


@router.get("/vagas")
def listar(
    usuario: UsuarioLogado,
    sessao: SessaoDB,
    status: Annotated[StatusVaga, Query()] = StatusVaga.RECOMENDADA,
    busca: Annotated[str, Query(max_length=100)] = "",
    pagina: Annotated[int, Query(ge=1, le=1000)] = 1,
) -> dict:
    filtro = [VagaUsuario.usuario_id == usuario.id, VagaUsuario.status == status]
    if termo := busca.strip():
        padrao = f"%{termo}%"
        filtro.append(or_(Vaga.titulo.ilike(padrao), Vaga.empresa.ilike(padrao)))
    base = select(VagaUsuario, Vaga).join(Vaga, Vaga.id == VagaUsuario.vaga_id).where(*filtro)
    total = sessao.scalar(select(func.count()).select_from(base.subquery()))
    pares = sessao.execute(
        base.order_by(*_ORDEM.get(status, [VagaUsuario.status_em.desc()]))
        .limit(POR_PAGINA)
        .offset((pagina - 1) * POR_PAGINA)
    ).all()
    auditorias = _auditorias(sessao, [vu.id for vu, _ in pares])
    fontes = _fontes(sessao, [vaga.id for _, vaga in pares])
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": POR_PAGINA,
        "itens": [
            _item(vu, vaga, auditorias.get(vu.id), fontes.get(vaga.id, [])) for vu, vaga in pares
        ],
    }


@router.get("/vagas/{vaga_usuario_id}")
def detalhe(vaga_usuario_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    vu = _da_pessoa(sessao, usuario, vaga_usuario_id)
    if vu is None:
        return JSONResponse({"erro": "vaga não encontrada"}, 404)
    vaga = sessao.get_one(Vaga, vu.vaga_id)
    auditoria = _auditorias(sessao, [vu.id]).get(vu.id)
    historico = sessao.scalars(
        select(HistoricoStatus)
        .where(HistoricoStatus.vaga_usuario_id == vu.id)
        .order_by(HistoricoStatus.criado_em)
    )
    dados = _item(vu, vaga, auditoria, _fontes(sessao, [vaga.id]).get(vaga.id, []))
    dados["descricao"] = (vaga.descricao or "")[:LIMITE_DESCRICAO]
    dados["auditoria"] = auditoria
    dados["historico"] = [
        {"de": h.de, "para": h.para, "origem": h.origem, "detalhe": h.detalhe,
         "em": h.criado_em.isoformat()}
        for h in historico
    ]  # fmt: skip
    return JSONResponse(dados)


def _decidir(
    vaga_usuario_id: uuid.UUID, usuario: Usuario, sessao: Session, para: StatusVaga,
    motivo: str | None = None,
) -> JSONResponse:  # fmt: skip
    vu = _da_pessoa(sessao, usuario, vaga_usuario_id)
    if vu is None:
        return JSONResponse({"erro": "vaga não encontrada"}, 404)
    if motivo is not None and motivo not in MOTIVOS_IGNORAR:
        return JSONResponse({"erro": "motivo inválido"}, 422)
    try:
        transicionar(sessao, vu, para, OrigemTransicao.USUARIO, "web")
    except TransicaoInvalida:
        return JSONResponse({"erro": f"essa vaga já está: {vu.status}"}, 409)
    if motivo:
        vu.motivo_usuario = motivo
    sessao.commit()
    sessao.refresh(vu)
    return JSONResponse({"id": str(vu.id), "status": vu.status, "motivo_usuario": motivo})


@router.post("/vagas/{vaga_usuario_id}/confirmar", dependencies=ComCsrf)
def confirmar(vaga_usuario_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB) -> JSONResponse:
    return _decidir(vaga_usuario_id, usuario, sessao, StatusVaga.CONFIRMADA)


@router.post("/vagas/{vaga_usuario_id}/ignorar", dependencies=ComCsrf)
def ignorar(
    vaga_usuario_id: uuid.UUID, usuario: UsuarioLogado, sessao: SessaoDB,
    corpo: Annotated[dict[str, Any], Body()],
) -> JSONResponse:  # fmt: skip
    motivo = corpo.get("motivo")
    return _decidir(vaga_usuario_id, usuario, sessao, StatusVaga.IGNORADA, motivo or None)
