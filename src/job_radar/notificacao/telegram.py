"""Cliente mínimo da Bot API do Telegram (sem dependências além do httpx).

O token faz parte da URL; por isso as mensagens de erro nunca incluem a URL nem o
`repr` da exceção do httpx, e os logs do httpx ficam em WARNING (ver logs.py).
"""

from typing import Any

import httpx

API = "https://api.telegram.org"

Botoes = list[list[dict[str, str]]]


class ErroTelegram(Exception):
    pass


class ClienteTelegram:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"{API}/bot{token}"
        self.http = http or httpx.Client(timeout=40)

    def _chamar(self, metodo: str, **parametros: Any) -> Any:
        corpo = {chave: valor for chave, valor in parametros.items() if valor is not None}
        try:
            resposta = self.http.post(f"{self._base}/{metodo}", json=corpo)
        except httpx.HTTPError as erro:
            raise ErroTelegram(f"{metodo}: falha de rede ({type(erro).__name__})") from None
        try:
            dados = resposta.json()
        except ValueError:
            raise ErroTelegram(f"{metodo}: HTTP {resposta.status_code}") from None
        if not dados.get("ok"):
            raise ErroTelegram(f"{metodo}: {dados.get('description', resposta.status_code)}")
        return dados["result"]

    @staticmethod
    def _teclado(botoes: Botoes | None) -> dict | None:
        return {"inline_keyboard": botoes} if botoes is not None else None

    def eu(self) -> dict:
        return self._chamar("getMe")

    def enviar_mensagem(self, chat_id: int, texto: str, botoes: Botoes | None = None) -> dict:
        return self._chamar(
            "sendMessage",
            chat_id=chat_id,
            text=texto,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
            reply_markup=self._teclado(botoes),
        )

    def editar_mensagem(
        self, chat_id: int, message_id: int, texto: str, botoes: Botoes | None = None
    ) -> dict:
        return self._chamar(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=texto,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
            reply_markup=self._teclado(botoes) or {"inline_keyboard": []},
        )

    def responder_callback(self, callback_id: str, texto: str | None = None) -> None:
        self._chamar("answerCallbackQuery", callback_query_id=callback_id, text=texto)

    def obter_updates(self, offset: int | None, timeout_s: int = 20) -> list[dict]:
        return self._chamar(
            "getUpdates",
            offset=offset,
            timeout=timeout_s,
            allowed_updates=["message", "callback_query"],
        )
