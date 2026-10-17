"""Interface dos coletores e registro por id de fonte."""

from collections.abc import Callable
from typing import Any, Protocol

import httpx

from job_radar.schemas.vaga import VagaBruta


class Coletor(Protocol):
    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        """Busca até `limite` vagas usando a `fonte.config` da fonte."""
        ...


FabricaColetor = Callable[[httpx.Client], Coletor]


class FonteDesconhecida(Exception):
    pass


_REGISTRO: dict[str, FabricaColetor] = {}


def registrar(fonte_id: str) -> Callable[[FabricaColetor], FabricaColetor]:
    def decorador(fabrica: FabricaColetor) -> FabricaColetor:
        _REGISTRO[fonte_id] = fabrica
        return fabrica

    return decorador


def _carregar_fontes() -> None:
    import job_radar.coleta.fontes  # noqa: F401  (registra os coletores ao importar)


def fontes_registradas() -> list[str]:
    _carregar_fontes()
    return sorted(_REGISTRO)


def obter_coletor(fonte_id: str, http: httpx.Client) -> Coletor:
    _carregar_fontes()
    try:
        fabrica = _REGISTRO[fonte_id]
    except KeyError:
        raise FonteDesconhecida(fonte_id) from None
    return fabrica(http)
