"""Perfil & Regras na API JSON: validação do que vem do frontend e formato de resposta.

Localidades trafegam como texto "Cidade/UF" (ou só "UF"), o mesmo que a pessoa digita;
no banco ficam como [{"cidade": ..., "uf": ...}].
"""

from dataclasses import dataclass, field
from typing import Any

from job_radar.filtro.localidade import normalizar_uf
from job_radar.models import Perfil
from job_radar.models.enums import Nivel

NIVEIS_EDITAVEIS = [n.value for n in Nivel if n != Nivel.DESCONHECIDO]
LIMITE_CURRICULO = 30_000
LIMITE_INSTRUCOES = 2_000
LIMITE_TERMOS = 200


def lista_de_termos(valores: Any) -> list[str]:
    """Sem vazios e sem repetição (ignorando maiúsculas), na ordem recebida."""
    if not isinstance(valores, list):
        return []
    vistos: dict[str, str] = {}
    for valor in valores:
        termo = " ".join(str(valor).split())
        if termo and termo.lower() not in vistos:
            vistos[termo.lower()] = termo
    return list(vistos.values())


def localidade_para_texto(local: dict) -> str:
    return f"{local['cidade']}/{local['uf']}" if local.get("cidade") else local.get("uf", "")


def _inteiro(valor: Any, minimo: int, maximo: int) -> int | None:
    if isinstance(valor, bool):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if minimo <= numero <= maximo else None


@dataclass
class DadosPerfil:
    palavras_chave: list[str]
    palavras_excluidas: list[str]
    niveis: list[str]
    aceita_remoto: bool
    localidades: list[dict]
    score_minimo: int
    ttl_pool_dias: int
    ttl_recomendada_dias: int
    curriculo_md: str
    instrucoes_ia: str
    erros: dict[str, str] = field(default_factory=dict)


CAMPOS_PERFIL = (
    "palavras_chave", "palavras_excluidas", "niveis", "aceita_remoto", "localidades",
    "score_minimo", "ttl_pool_dias", "ttl_recomendada_dias", "curriculo_md", "instrucoes_ia",
)  # fmt: skip


def _localidades(valores: Any, erros: dict[str, str]) -> list[dict]:
    resultado = []
    for linha in lista_de_termos(valores):
        cidade, _, uf_bruta = linha.rpartition("/")
        uf = normalizar_uf(uf_bruta)
        if uf is None:
            erros["localidades"] = f"UF inválida em “{linha}”: use Cidade/UF (ex.: Brasília/DF)"
            continue
        resultado.append({"cidade": cidade.strip(), "uf": uf} if cidade.strip() else {"uf": uf})
    return resultado


def validar(corpo: dict) -> DadosPerfil:
    erros: dict[str, str] = {}
    palavras = lista_de_termos(corpo.get("palavras_chave"))
    excluidas = lista_de_termos(corpo.get("palavras_excluidas"))
    if not palavras:
        erros["palavras_chave"] = "Informe ao menos uma palavra-chave"
    if len(palavras) > LIMITE_TERMOS or len(excluidas) > LIMITE_TERMOS:
        erros["palavras_chave"] = f"Máximo de {LIMITE_TERMOS} termos por lista"
    niveis = [n for n in lista_de_termos(corpo.get("niveis")) if n in NIVEIS_EDITAVEIS]
    if not niveis:
        erros["niveis"] = "Escolha ao menos um nível"

    score = _inteiro(corpo.get("score_minimo"), 0, 100)
    if score is None:
        erros["score_minimo"] = "Número de 0 a 100"
    ttl_pool = _inteiro(corpo.get("ttl_pool_dias"), 1, 60)
    if ttl_pool is None:
        erros["ttl_pool_dias"] = "De 1 a 60 dias"
    ttl_rec = _inteiro(corpo.get("ttl_recomendada_dias"), 1, 60)
    if ttl_rec is None:
        erros["ttl_recomendada_dias"] = "De 1 a 60 dias"

    curriculo = str(corpo.get("curriculo_md") or "").strip()
    if len(curriculo) > LIMITE_CURRICULO:
        erros["curriculo_md"] = f"Máximo de {LIMITE_CURRICULO} caracteres"
    instrucoes = str(corpo.get("instrucoes_ia") or "").strip()
    if len(instrucoes) > LIMITE_INSTRUCOES:
        erros["instrucoes_ia"] = f"Máximo de {LIMITE_INSTRUCOES} caracteres"

    return DadosPerfil(
        palavras_chave=palavras,
        palavras_excluidas=excluidas,
        niveis=niveis,
        aceita_remoto=corpo.get("aceita_remoto") is True,
        localidades=_localidades(corpo.get("localidades"), erros),
        score_minimo=score if score is not None else 60,
        ttl_pool_dias=ttl_pool or 7,
        ttl_recomendada_dias=ttl_rec or 14,
        curriculo_md=curriculo,
        instrucoes_ia=instrucoes,
        erros=erros,
    )


def para_json(perfil: Perfil | DadosPerfil) -> dict:
    dados = {campo: getattr(perfil, campo) for campo in CAMPOS_PERFIL}
    dados["localidades"] = [localidade_para_texto(loc) for loc in perfil.localidades]
    return dados


def limites() -> dict:
    return {
        "niveis": NIVEIS_EDITAVEIS,
        "curriculo": LIMITE_CURRICULO,
        "instrucoes": LIMITE_INSTRUCOES,
    }
