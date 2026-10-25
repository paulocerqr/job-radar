"""Pré-filtro de novo sobre vagas já coletadas, depois de mudar o perfil.

A nota do pré-filtro é calculada uma vez, na coleta; sem isto, uma palavra-chave nova só
valeria para vagas que ainda vão chegar.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_radar.fila.alimentador import SCORE_MINIMO_FILA
from job_radar.filtro.prefiltro import PerfilAvaliador, avaliar
from job_radar.models import Fonte, Vaga, VagaFonte, VagaUsuario
from job_radar.models.enums import StatusVaga


def _confiabilidade_por_vaga(sessao: Session) -> dict:
    linhas = sessao.execute(
        select(VagaFonte.vaga_id, func.max(Fonte.confiabilidade))
        .join(Fonte, Fonte.id == VagaFonte.fonte_id)
        .group_by(VagaFonte.vaga_id)
    )
    return dict(linhas.all())


@dataclass(frozen=True)
class Simulacao:
    avaliadas: int
    aprovadas: int
    para_fila: int
    exemplos: list[tuple[int, str]]  # (nota, título) das que iriam para a fila


def simular(sessao: Session, perfil: PerfilAvaliador, limite_exemplos: int = 15) -> Simulacao:
    """Quantas vagas ativas do banco passariam no pré-filtro com este perfil (sem gravar)."""
    agora = datetime.now(UTC)
    confiabilidade = _confiabilidade_por_vaga(sessao)
    aprovadas = 0
    fila: list[tuple[int, str]] = []
    vagas = sessao.scalars(select(Vaga).where(Vaga.ativa)).all()
    for vaga in vagas:
        resultado = avaliar(vaga, perfil, confiabilidade.get(vaga.id, 50), agora)
        if resultado.aprovada:
            aprovadas += 1
            if resultado.score >= SCORE_MINIMO_FILA:
                fila.append((resultado.score, vaga.titulo))
    fila.sort(key=lambda item: -item[0])
    return Simulacao(len(vagas), aprovadas, len(fila), fila[:limite_exemplos])


def recalcular_pool(sessao: Session, usuario_id, perfil: PerfilAvaliador) -> int:
    """Atualiza a nota das vagas do usuário no pool. Retorna quantas mudaram.

    Vaga que deixaria de passar no pré-filtro fica com nota 0 (não entra na fila e expira
    pelo TTL), em vez de ser apagada.
    """
    agora = datetime.now(UTC)
    confiabilidade = _confiabilidade_por_vaga(sessao)
    pares = sessao.execute(
        select(VagaUsuario, Vaga)
        .join(Vaga, Vaga.id == VagaUsuario.vaga_id)
        .where(VagaUsuario.usuario_id == usuario_id, VagaUsuario.status == StatusVaga.POOL)
    ).all()
    mudaram = 0
    for vaga_usuario, vaga in pares:
        resultado = avaliar(vaga, perfil, confiabilidade.get(vaga.id, 50), agora)
        nota = resultado.score if resultado.aprovada else 0
        if nota != vaga_usuario.score_prefiltro:
            vaga_usuario.score_prefiltro = nota
            mudaram += 1
    return mudaram
