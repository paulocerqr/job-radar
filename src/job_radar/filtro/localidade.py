"""UFs e comparação de localidade da vaga com as localidades do perfil (RN11)."""

from collections.abc import Iterable, Mapping

from job_radar.texto import normalizar_chave

UFS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}  # fmt: skip
SIGLAS = frozenset(UFS.values())


def normalizar_uf(valor: str | None) -> str | None:
    """Aceita sigla ('df') ou nome ('Distrito Federal')."""
    if not valor:
        return None
    if valor.strip().upper() in SIGLAS:
        return valor.strip().upper()
    return UFS.get(normalizar_chave(valor))


def localidade_atende(
    cidade: str | None, uf: str | None, localidades: Iterable[Mapping[str, str]]
) -> bool | None:
    """True/False quando dá para decidir; None quando a vaga não informa o local.

    No DF qualquer cidade conta: as regiões administrativas (Taguatinga, Águas Claras...)
    aparecem como "cidade" nas fontes, mas fazem parte de Brasília.
    """
    if not cidade and not uf:
        return None
    for local in localidades:
        uf_local = normalizar_uf(local.get("uf"))
        cidade_local = normalizar_chave(local.get("cidade"))
        mesma_cidade = bool(cidade) and normalizar_chave(cidade) == cidade_local
        if uf and uf_local and uf == uf_local:
            if uf == "DF" or not cidade_local or mesma_cidade:
                return True
        elif not uf and mesma_cidade:
            return True
    return False
