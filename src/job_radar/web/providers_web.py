"""Cadastro e edição de providers pela Web UI: validação.

Só `openai_compatible` (o tipo `cli` depende de binário no host, D18). A URL vem do
usuário e o servidor chama ela levando a chave: para não virar SSRF (ex.: servidor de
metadados da GCP em 169.254.169.254, serviços internos do cluster), exige https e um
host que resolva só para IPs públicos. Resta o risco de DNS rebinding entre a validação
e a chamada, aceito para um app de poucos usuários convidados.
"""

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

from job_radar.auditoria.presets import PRESETS
from job_radar.models.enums import TipoProvider

_resolver = socket.getaddrinfo  # ponto de troca nos testes

PRESETS_WEB = {nome: p for nome, p in PRESETS.items() if p.tipo == TipoProvider.OPENAI_COMPATIBLE}


def url_publica(url: str) -> str | None:
    """Mensagem de erro, ou None se a URL é https e o host só tem IPs públicos."""
    partes = urlsplit(url)
    if partes.scheme != "https" or not partes.hostname:
        return "use uma URL https://"
    if partes.username or partes.password:
        return "a URL não pode ter usuário e senha"
    try:
        enderecos = {info[4][0] for info in _resolver(partes.hostname, partes.port or 443)}
    except (socket.gaierror, UnicodeError):
        return "não foi possível resolver o endereço"
    if not enderecos or not all(ipaddress.ip_address(ip).is_global for ip in enderecos):
        return "o endereço precisa ser público (rede interna não é permitida)"
    return None


def _inteiro(valor: Any, minimo: int, maximo: int, opcional: bool) -> tuple[int | None, bool]:
    if valor in (None, "") and opcional:
        return None, True
    if isinstance(valor, bool):
        return None, False
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None, False
    return numero, minimo <= numero <= maximo


def validar(corpo: dict, novo: bool) -> tuple[dict, dict[str, str]]:
    """Campos validados e erros. Em edição (novo=False), só valida o que veio no corpo."""
    erros: dict[str, str] = {}
    campos: dict[str, Any] = {}

    def presente(campo: str) -> bool:
        return novo or campo in corpo

    if novo:
        nome = " ".join(str(corpo.get("nome", "")).split())
        if not 1 <= len(nome) <= 40:
            erros["nome"] = "Informe um nome (até 40 caracteres)"
        campos["nome"] = nome
    if presente("base_url"):
        url = str(corpo.get("base_url", "")).strip().rstrip("/")
        # o cliente acrescenta /chat/completions; colar a URL do endpoint é um erro comum
        url = url.removesuffix("/chat/completions").rstrip("/")
        if problema := url_publica(url):
            erros["base_url"] = problema
        campos["base_url"] = url
    if presente("modelo"):
        modelo = str(corpo.get("modelo", "")).strip()
        if not 1 <= len(modelo) <= 120:
            erros["modelo"] = "Informe o modelo"
        campos["modelo"] = modelo
    for campo, minimo, maximo, opcional in (
        ("rpm", 1, 10_000, True), ("rpd", 1, 1_000_000, True),
        ("tamanho_lote", 1, 20, False), ("timeout_s", 10, 600, False),
    ):  # fmt: skip
        if presente(campo):
            padrao = {"tamanho_lote": 5, "timeout_s": 120}.get(campo)
            valor, ok = _inteiro(corpo.get(campo, padrao), minimo, maximo, opcional)
            if not ok:
                erros[campo] = f"De {minimo} a {maximo}"
            campos[campo] = valor
    chave = str(corpo.get("api_key") or "").strip()
    if novo and not chave:
        erros["api_key"] = "Informe a chave de API"
    if chave:
        if len(chave) > 500 or any(c.isspace() for c in chave):
            erros["api_key"] = "Chave inválida"
        campos["api_key"] = chave
    return campos, erros
