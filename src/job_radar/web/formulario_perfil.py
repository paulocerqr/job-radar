"""Formulário de Perfil & Regras: texto do navegador → valores validados do perfil."""

import re
from dataclasses import dataclass, field

from job_radar.filtro.localidade import normalizar_uf
from job_radar.models.enums import Nivel

NIVEIS_EDITAVEIS = [n.value for n in Nivel if n != Nivel.DESCONHECIDO]
LIMITE_CURRICULO = 30_000
LIMITE_INSTRUCOES = 2_000
_SEPARADOR = re.compile(r"[\n,;]+")


def lista_de_termos(texto: str) -> list[str]:
    """Um termo por linha (ou separados por vírgula), sem repetição, na ordem digitada."""
    vistos: dict[str, None] = {}
    for termo in _SEPARADOR.split(texto or ""):
        termo = " ".join(termo.split())
        if termo and termo.lower() not in (t.lower() for t in vistos):
            vistos[termo] = None
    return list(vistos)


def localidades_para_texto(localidades: list[dict]) -> str:
    return "\n".join(
        f"{loc['cidade']}/{loc['uf']}" if loc.get("cidade") else loc.get("uf", "")
        for loc in localidades
    )


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


def _inteiro(valor: str | None, minimo: int, maximo: int) -> int | None:
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return numero if minimo <= numero <= maximo else None


def _localidades(texto: str, erros: dict[str, str]) -> list[dict]:
    resultado = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        cidade, _, uf_bruta = linha.rpartition("/")
        uf = normalizar_uf(uf_bruta)
        if uf is None:
            erros["localidades"] = f"UF inválida em “{linha}”: use Cidade/UF (ex.: Brasília/DF)"
            continue
        item = {"cidade": cidade.strip(), "uf": uf} if cidade.strip() else {"uf": uf}
        resultado.append(item)
    return resultado


def ler_formulario(form) -> DadosPerfil:
    erros: dict[str, str] = {}
    palavras = lista_de_termos(form.get("palavras_chave", ""))
    if not palavras:
        erros["palavras_chave"] = "Informe ao menos uma palavra-chave"
    niveis = [n for n in form.getlist("niveis") if n in NIVEIS_EDITAVEIS]
    if not niveis:
        erros["niveis"] = "Escolha ao menos um nível"

    score = _inteiro(form.get("score_minimo"), 0, 100)
    if score is None:
        erros["score_minimo"] = "Número de 0 a 100"
    ttl_pool = _inteiro(form.get("ttl_pool_dias"), 1, 60)
    if ttl_pool is None:
        erros["ttl_pool_dias"] = "De 1 a 60 dias"
    ttl_rec = _inteiro(form.get("ttl_recomendada_dias"), 1, 60)
    if ttl_rec is None:
        erros["ttl_recomendada_dias"] = "De 1 a 60 dias"

    curriculo = (form.get("curriculo_md") or "").strip()
    if len(curriculo) > LIMITE_CURRICULO:
        erros["curriculo_md"] = f"Máximo de {LIMITE_CURRICULO} caracteres"
    instrucoes = (form.get("instrucoes_ia") or "").strip()
    if len(instrucoes) > LIMITE_INSTRUCOES:
        erros["instrucoes_ia"] = f"Máximo de {LIMITE_INSTRUCOES} caracteres"

    return DadosPerfil(
        palavras_chave=palavras,
        palavras_excluidas=lista_de_termos(form.get("palavras_excluidas", "")),
        niveis=niveis,
        aceita_remoto=form.get("aceita_remoto") == "on",
        localidades=_localidades(form.get("localidades", ""), erros),
        score_minimo=score if score is not None else 60,
        ttl_pool_dias=ttl_pool or 7,
        ttl_recomendada_dias=ttl_rec or 14,
        curriculo_md=curriculo,
        instrucoes_ia=instrucoes,
        erros=erros,
    )


CAMPOS_PERFIL = (
    "palavras_chave",
    "palavras_excluidas",
    "niveis",
    "aceita_remoto",
    "localidades",
    "score_minimo",
    "ttl_pool_dias",
    "ttl_recomendada_dias",
    "curriculo_md",
    "instrucoes_ia",
)
