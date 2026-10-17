"""Repositórios de vagas no GitHub (backend-br/vagas e similares): cada issue é uma vaga.

Modalidade e nível vêm das labels padronizadas; issues com label "Stale" são ignoradas.
"""

import re
from typing import Any

import httpx

from job_radar.coleta.base import registrar
from job_radar.config import get_settings
from job_radar.filtro.localidade import SIGLAS
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta
from job_radar.texto import normalizar_chave

API = "https://api.github.com"

_LABEL_MODALIDADE = {
    "remoto": Modalidade.REMOTO,
    "hibrido": Modalidade.HIBRIDO,
    "presencial": Modalidade.PRESENCIAL,
}
_LABEL_NIVEL = {
    "estagio": Nivel.ESTAGIO,
    "estagiario": Nivel.ESTAGIO,
    "trainee": Nivel.TRAINEE,
    "junior": Nivel.JUNIOR,
    "pleno": Nivel.PLENO,
    "senior": Nivel.SENIOR,
    "especialista": Nivel.SENIOR,
}
# Com várias labels, vale a mais flexível / a mais júnior (a vaga aceita esse perfil)
_PRIORIDADE_MODALIDADE = [Modalidade.REMOTO, Modalidade.HIBRIDO, Modalidade.PRESENCIAL]
_PRIORIDADE_NIVEL = [Nivel.ESTAGIO, Nivel.TRAINEE, Nivel.JUNIOR, Nivel.PLENO, Nivel.SENIOR]

_TAGS_TITULO = re.compile(r"\[([^\]]*)\]")
# "Software Engineer na Google" / "Backend Developer at ACME"
_EMPRESA_NO_FIM = re.compile(r"^(?P<cargo>.*\S)\s+(?:na|no|at)\s+(?P<empresa>[A-Z0-9][^,()]*)$")


def _primeiro(encontrados: set, prioridade: list, padrao):
    return next((item for item in prioridade if item in encontrados), padrao)


def _uf_nas_tags(tags: list[str]) -> str | None:
    for tag in tags:
        for token in re.split(r"[\s\-/,|]+", tag):
            if token.upper() in SIGLAS:
                return token.upper()
    return None


def mapear(issue: dict[str, Any], fonte_id: str) -> VagaBruta:
    labels = {normalizar_chave(label["name"]) for label in issue.get("labels", [])}
    tags = _TAGS_TITULO.findall(issue["title"])
    titulo = _TAGS_TITULO.sub("", issue["title"]).strip(" -")
    empresa = None
    if " - " in titulo:
        titulo, empresa = (parte.strip() for parte in titulo.rsplit(" - ", 1))
    elif casamento := _EMPRESA_NO_FIM.match(titulo):
        titulo, empresa = casamento["cargo"], casamento["empresa"].strip()

    # "[Híbrido -SP]" no título também indica modalidade
    palavras = set().union(*(t.split() for t in labels | {normalizar_chave(t) for t in tags}))
    modalidades = {m for chave, m in _LABEL_MODALIDADE.items() if chave in palavras}
    niveis = {n for chave, n in _LABEL_NIVEL.items() if chave in labels}

    return VagaBruta(
        fonte_id=fonte_id,
        id_externo=str(issue["number"]),
        url=issue["html_url"],
        titulo=titulo,
        empresa=empresa,
        descricao=issue.get("body"),
        uf=_uf_nas_tags(tags),
        modalidade=_primeiro(modalidades, _PRIORIDADE_MODALIDADE, Modalidade.DESCONHECIDA),
        nivel=_primeiro(niveis, _PRIORIDADE_NIVEL, Nivel.DESCONHECIDO),
        publicada_em=issue.get("created_at"),
        dados_brutos={k: issue.get(k) for k in ("number", "title", "labels", "updated_at")},
    )


class ColetorGitHubIssues:
    def __init__(self, http: httpx.Client, fonte_id: str) -> None:
        self.http = http
        self.fonte_id = fonte_id

    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        repositorio = config["repositorio"]
        headers = {"Accept": "application/vnd.github+json"}
        token = get_settings().github_token
        if token:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"

        vagas: list[VagaBruta] = []
        pagina = 1
        while len(vagas) < limite:
            resposta = self.http.get(
                f"{API}/repos/{repositorio}/issues",
                params={
                    "state": "open",
                    "sort": "created",
                    "direction": "desc",
                    "per_page": 100,
                    "page": pagina,
                },
                headers=headers,
            )
            resposta.raise_for_status()
            issues = resposta.json()
            if not issues:
                break
            for issue in issues:
                if "pull_request" in issue:
                    continue
                if any(normalizar_chave(lb["name"]) == "stale" for lb in issue.get("labels", [])):
                    continue
                vagas.append(mapear(issue, self.fonte_id))
            pagina += 1
        return vagas[:limite]


registrar("github_backendbr")(lambda http: ColetorGitHubIssues(http, "github_backendbr"))
