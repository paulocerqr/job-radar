"""Pré-filtro por regras, sem IA (RN08-RN12). Corta o grosso antes da auditoria."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from job_radar.filtro.localidade import localidade_atende
from job_radar.models.enums import Modalidade, Nivel
from job_radar.texto import contem_termo, normalizar_chave

PENALIDADE_DESCONHECIDO = 10


class VagaAvaliavel(Protocol):
    titulo: str
    descricao: str | None
    cidade: str | None
    uf: str | None
    modalidade: str
    nivel: str
    publicada_em: datetime | None


class PerfilAvaliador(Protocol):
    palavras_chave: list[str]
    palavras_excluidas: list[str]
    niveis: list[str]
    aceita_remoto: bool
    localidades: list[dict]


@dataclass(frozen=True)
class ResultadoPrefiltro:
    aprovada: bool
    score: int
    motivo: str | None = None


def _reprovada(motivo: str) -> ResultadoPrefiltro:
    return ResultadoPrefiltro(aprovada=False, score=0, motivo=motivo)


def _pontos_recencia(publicada_em: datetime | None, agora: datetime) -> int:
    if publicada_em is None:
        return 0
    dias = (agora - publicada_em).days
    if dias <= 3:
        return 15
    if dias <= 7:
        return 10
    if dias <= 14:
        return 5
    return 0


def avaliar(
    vaga: VagaAvaliavel, perfil: PerfilAvaliador, confiabilidade_fonte: int, agora: datetime
) -> ResultadoPrefiltro:
    titulo = normalizar_chave(vaga.titulo)
    descricao = normalizar_chave(vaga.descricao)

    # RN09: termos excluídos só no título (descrições citam "sênior" no time, plano de carreira...)
    excluidos = [t for t in perfil.palavras_excluidas if contem_termo(titulo, t)]
    if excluidos:
        return _reprovada(f"termo excluído no título: {excluidos[0]}")

    # RN10
    if vaga.nivel != Nivel.DESCONHECIDO and vaga.nivel not in perfil.niveis:
        return _reprovada(f"nível fora do perfil: {vaga.nivel}")

    # RN08
    no_titulo = [t for t in perfil.palavras_chave if contem_termo(titulo, t)]
    na_descricao = [
        t for t in perfil.palavras_chave if t not in no_titulo and contem_termo(descricao, t)
    ]
    if not no_titulo and not na_descricao:
        return _reprovada("nenhuma palavra-chave do perfil")

    # RN11
    penalidade = PENALIDADE_DESCONHECIDO if vaga.nivel == Nivel.DESCONHECIDO else 0
    if vaga.modalidade == Modalidade.REMOTO:
        if not perfil.aceita_remoto:
            return _reprovada("vaga remota e perfil não aceita remoto")
    else:
        atende = localidade_atende(vaga.cidade, vaga.uf, perfil.localidades)
        if atende is False and vaga.modalidade != Modalidade.DESCONHECIDA:
            return _reprovada(f"fora das localidades do perfil: {vaga.cidade}/{vaga.uf}")
        if atende is None or vaga.modalidade == Modalidade.DESCONHECIDA:
            penalidade += PENALIDADE_DESCONHECIDO

    # RN12
    score = 0
    if no_titulo:
        score += min(60, 40 + 10 * (len(no_titulo) - 1))
    score += min(20, 5 * len(na_descricao))
    score += _pontos_recencia(vaga.publicada_em, agora)
    score += confiabilidade_fonte // 10
    score -= penalidade
    return ResultadoPrefiltro(aprovada=True, score=max(0, min(100, score)))
