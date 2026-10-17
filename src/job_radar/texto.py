"""Normalização de texto usada em dedupe, pré-filtro e mapeamento de fontes."""

import html
import re
import unicodedata

_NAO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")
_SUFIXO_EMPRESA = re.compile(r"\s+(ltda|s a|sa|eireli|epp|me)$")
_QUEBRA_HTML = re.compile(r"<\s*(br|/p|/li|/div|/h[1-6]|/tr)\s*/?\s*>", re.IGNORECASE)
_TAG_HTML = re.compile(r"<[^>]+>")


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar_chave(texto: str | None) -> str:
    """Minúsculas, sem acento, só [a-z0-9] separados por um espaço."""
    if not texto:
        return ""
    return _NAO_ALFANUMERICO.sub(" ", sem_acentos(texto).lower()).strip()


def normalizar_empresa(texto: str | None) -> str:
    chave = normalizar_chave(texto)
    while (sem_sufixo := _SUFIXO_EMPRESA.sub("", chave)) != chave:
        chave = sem_sufixo
    return chave


def contem_termo(texto_normalizado: str, termo: str) -> bool:
    """Busca por palavra inteira: 'ti' casa com 'estagio em ti', não com 'tipo'.

    `texto_normalizado` deve ter passado por `normalizar_chave`.
    """
    termo_normalizado = normalizar_chave(termo)
    if not termo_normalizado:
        return False
    return f" {termo_normalizado} " in f" {texto_normalizado} "


def html_para_texto(texto: str | None) -> str:
    if not texto:
        return ""
    texto = _QUEBRA_HTML.sub("\n", texto)
    texto = html.unescape(_TAG_HTML.sub("", texto))
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    texto = re.sub(r" *\n\s*\n+", "\n\n", texto)
    return texto.strip()
