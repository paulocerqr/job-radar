"""Qualquer API compatível com /chat/completions da OpenAI: Groq, NVIDIA NIM, Gemini, OpenRouter."""

from typing import Any

import httpx

from job_radar.auditoria.providers.base import ErroProvider, LimiteExcedido, RespostaProvider


class ProviderOpenAICompativel:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        modelo: str,
        timeout_s: int = 120,
        http: httpx.Client | None = None,
    ) -> None:
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.modelo = modelo
        self.http = http or httpx.Client(timeout=timeout_s)

    def _post(self, corpo: dict[str, Any]) -> httpx.Response:
        try:
            return self.http.post(
                self.url, json=corpo, headers={"Authorization": f"Bearer {self.api_key}"}
            )
        except httpx.HTTPError as erro:
            raise ErroProvider(f"falha de rede: {erro!r}") from None

    def completar(self, sistema: str, usuario: str) -> RespostaProvider:
        corpo: dict[str, Any] = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        resposta = self._post(corpo)
        # Nem todo modelo aceita JSON mode; nesse caso o prompt + extrair_json resolvem
        if resposta.status_code == 400 and "response_format" in resposta.text:
            corpo.pop("response_format")
            resposta = self._post(corpo)

        if resposta.status_code == 429:
            retry_after = resposta.headers.get("retry-after")
            raise LimiteExcedido(
                f"429: {resposta.text[:200]}",
                retry_after_s=float(retry_after) if retry_after else None,
            )
        if resposta.status_code in (400, 401, 403, 404):
            raise ErroProvider(f"{resposta.status_code}: {resposta.text[:300]}", transitorio=False)
        if resposta.status_code >= 400:
            raise ErroProvider(f"{resposta.status_code}: {resposta.text[:300]}")

        dados = resposta.json()
        try:
            texto = dados["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ErroProvider(f"resposta fora do formato esperado: {str(dados)[:300]}") from None
        uso = dados.get("usage") or {}
        return RespostaProvider(
            texto=texto,
            modelo=dados.get("model") or self.modelo,
            tokens_entrada=uso.get("prompt_tokens"),
            tokens_saida=uso.get("completion_tokens"),
        )
