import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_radar.filtro.localidade import normalizar_uf
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta, VagaNormalizada
from job_radar.texto import contem_termo, html_para_texto, normalizar_chave, normalizar_empresa

_PARAMETROS_RASTREIO = {"jobboardsource", "ref", "source", "origin", "gh_src"}

# Ordem importa: o primeiro nível encontrado no título vence.
_NIVEL_POR_TERMO: list[tuple[Nivel, tuple[str, ...]]] = [
    (Nivel.ESTAGIO, ("estagio", "estagiario", "estagiaria", "intern", "internship")),
    (Nivel.TRAINEE, ("trainee",)),
    (Nivel.JUNIOR, ("junior", "jr")),
    (Nivel.PLENO, ("pleno",)),
    (Nivel.SENIOR, ("senior", "sr", "especialista", "specialist", "lead")),
]


def url_canonica(url: str) -> str:
    partes = urlsplit(url.strip())
    query = [
        (chave, valor)
        for chave, valor in parse_qsl(partes.query, keep_blank_values=True)
        if not chave.lower().startswith("utm_") and chave.lower() not in _PARAMETROS_RASTREIO
    ]
    return urlunsplit(
        (partes.scheme.lower(), partes.netloc.lower(), partes.path, urlencode(query), "")
    )


def inferir_nivel(titulo: str) -> Nivel:
    titulo_normalizado = normalizar_chave(titulo)
    for nivel, termos in _NIVEL_POR_TERMO:
        if any(contem_termo(titulo_normalizado, termo) for termo in termos):
            return nivel
    return Nivel.DESCONHECIDO


def calcular_hash_dedupe(
    empresa: str | None, titulo: str, cidade: str | None, modalidade: Modalidade
) -> str:
    """RN05: mesma empresa + título + local = mesma vaga, independente da fonte."""
    local = "remoto" if modalidade == Modalidade.REMOTO else normalizar_chave(cidade)
    chave = f"{normalizar_empresa(empresa)}|{normalizar_chave(titulo)}|{local}"
    return hashlib.sha256(chave.encode()).hexdigest()


def _limpo(valor: str | None) -> str | None:
    valor = " ".join((valor or "").split())
    return valor or None


def normalizar(bruta: VagaBruta) -> VagaNormalizada:
    titulo = _limpo(bruta.titulo) or ""
    empresa = _limpo(bruta.empresa)
    cidade = _limpo(bruta.cidade)
    nivel = bruta.nivel if bruta.nivel != Nivel.DESCONHECIDO else inferir_nivel(titulo)
    return VagaNormalizada(
        fonte_id=bruta.fonte_id,
        id_externo=bruta.id_externo,
        url=bruta.url,
        url_canonica=url_canonica(bruta.url),
        hash_dedupe=calcular_hash_dedupe(empresa, titulo, cidade, bruta.modalidade),
        titulo=titulo,
        empresa=empresa,
        descricao=html_para_texto(bruta.descricao),
        cidade=cidade,
        uf=normalizar_uf(bruta.uf),
        modalidade=bruta.modalidade,
        nivel=nivel,
        publicada_em=bruta.publicada_em,
        dados_brutos=bruta.dados_brutos,
    )
