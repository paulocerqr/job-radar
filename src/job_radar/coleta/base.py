"""Interface dos coletores e registro por id de fonte.

Os coletores concretos (Gupy, GitHub, ...) entram na Fase 1 em `coleta/fontes/`.
"""

from collections.abc import Callable
from typing import Protocol


class Coletor(Protocol):
    fonte_id: str

    def executar(self) -> None: ...


class FonteDesconhecida(Exception):
    pass


_REGISTRO: dict[str, Callable[[], Coletor]] = {}


def registrar(fonte_id: str) -> Callable[[Callable[[], Coletor]], Callable[[], Coletor]]:
    def decorador(fabrica: Callable[[], Coletor]) -> Callable[[], Coletor]:
        _REGISTRO[fonte_id] = fabrica
        return fabrica

    return decorador


def fontes_registradas() -> list[str]:
    return sorted(_REGISTRO)


def obter_coletor(fonte_id: str) -> Coletor:
    try:
        return _REGISTRO[fonte_id]()
    except KeyError:
        raise FonteDesconhecida(fonte_id) from None
