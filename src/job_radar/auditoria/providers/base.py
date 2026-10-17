import json
import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class RespostaProvider:
    texto: str
    modelo: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class ErroProvider(Exception):
    """Falha ao chamar o provider. `transitorio=False` indica config errada (chave, modelo...)."""

    def __init__(self, mensagem: str, *, transitorio: bool = True) -> None:
        super().__init__(mensagem)
        self.transitorio = transitorio


class LimiteExcedido(ErroProvider):
    def __init__(self, mensagem: str, retry_after_s: float | None = None) -> None:
        super().__init__(mensagem, transitorio=True)
        self.retry_after_s = retry_after_s


class RespostaInvalida(Exception):
    pass


class Provider(Protocol):
    modelo: str

    def completar(self, sistema: str, usuario: str) -> RespostaProvider: ...


_CERCA_MARKDOWN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extrair_json(texto: str) -> dict[str, Any]:
    """Aceita JSON puro, dentro de ```json``` ou cercado de texto (modelos que "explicam")."""
    limpo = _CERCA_MARKDOWN.sub("", texto.strip())
    inicio, fim = limpo.find("{"), limpo.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise RespostaInvalida(f"sem objeto JSON na resposta: {texto[:200]!r}")
    try:
        dados = json.loads(limpo[inicio : fim + 1])
    except json.JSONDecodeError as erro:
        raise RespostaInvalida(f"JSON inválido: {erro}") from None
    if not isinstance(dados, dict):
        raise RespostaInvalida("a resposta não é um objeto JSON")
    return dados
