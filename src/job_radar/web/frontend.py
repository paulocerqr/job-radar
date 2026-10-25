"""Frontend (Next.js, exportação estática em frontend/) servido pela própria API.

O Next coloca scripts inline no HTML (dados das páginas). Em vez de liberar
`'unsafe-inline'`, a CSP das páginas do frontend lista o hash SHA-256 de cada script
inline encontrado nos HTMLs do build: só esses rodam.
"""

import base64
import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

log = logging.getLogger(__name__)

_SCRIPT_INLINE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL)


def hashes_de_scripts(diretorio: Path) -> list[str]:
    hashes: set[str] = set()
    for html in diretorio.rglob("*.html"):
        for corpo in _SCRIPT_INLINE.findall(html.read_text(encoding="utf-8")):
            digest = hashlib.sha256(corpo.encode()).digest()
            hashes.add(f"'sha256-{base64.b64encode(digest).decode()}'")
    return sorted(hashes)


def csp_do_frontend(hashes: list[str]) -> str:
    # style-src com 'unsafe-inline': o React usa atributos style (risco baixo, sem script)
    return (
        f"default-src 'self'; script-src 'self' {' '.join(hashes)}; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )


class Frontend(StaticFiles):
    def __init__(self, diretorio: Path) -> None:
        super().__init__(directory=diretorio, html=True)
        hashes = hashes_de_scripts(diretorio)
        self.csp = csp_do_frontend(hashes)
        log.info("frontend carregado", extra={"dir": str(diretorio), "scripts": len(hashes)})

    async def get_response(self, path: str, scope) -> Response:
        resposta = await super().get_response(path, scope)
        # "/login" → "/login/": o StaticFiles monta a URL absoluta com o esquema que chega
        # ao pod (http, atrás do túnel e do Traefik); só o caminho mantém o https do navegador
        if resposta.status_code in (301, 302, 307, 308) and "location" in resposta.headers:
            destino = urlsplit(resposta.headers["location"])
            resposta.headers["location"] = urlunsplit(("", "", destino.path, destino.query, ""))
        return resposta

    def file_response(self, full_path, stat_result, scope, status_code=200) -> Response:
        resposta = super().file_response(full_path, stat_result, scope, status_code)
        if str(full_path).endswith(".html"):
            resposta.headers["Content-Security-Policy"] = self.csp
        elif "/_next/static/" in str(full_path):
            # nomes com hash do conteúdo: podem ficar em cache para sempre
            resposta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resposta


def diretorio_frontend(configurado: Path | None) -> Path | None:
    candidatos = [configurado] if configurado else [Path("/app/frontend")]
    for candidato in candidatos:
        if candidato and (candidato / "index.html").is_file():
            return candidato
    return None
