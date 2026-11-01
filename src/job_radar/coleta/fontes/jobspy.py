"""LinkedIn, Indeed e Glassdoor via JobSpy, sem login ou cookies pessoais."""

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from job_radar.coleta.base import registrar
from job_radar.coleta.normalizador import inferir_nivel
from job_radar.filtro.localidade import normalizar_uf
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta
from job_radar.texto import normalizar_chave

log = logging.getLogger(__name__)

CONFIG_PADRAO = {
    "buscas": [{"termo": "estágio tecnologia", "local": "Brasília, Distrito Federal, Brazil"}],
    "horas": 72,
    "pausa_s": 5,
}


class Busca(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    termo: str = Field(min_length=1, max_length=200)
    local: str = Field(min_length=1, max_length=200)


class ConfigJobSpy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buscas: list[Busca] = Field(min_length=1, max_length=5)
    horas: int = Field(default=72, ge=1, le=720, strict=True)
    pausa_s: float = Field(default=5, ge=0, le=60)


class ConfigPortaisJobSpy(ConfigJobSpy):
    somente_remoto: bool = Field(default=False, strict=True)
    tipo_contrato: Literal["internship", "fulltime", "parttime", "contract", "temporary"] | None = (
        None
    )


CONFIG_PORTAIS = {
    portal: {
        "buscas": [{"termo": "estágio tecnologia", "local": "Brasília"}],
        "horas": 72,
        "pausa_s": 5,
        "somente_remoto": False,
        "tipo_contrato": "internship",
    }
    for portal in ("indeed", "glassdoor")
}


def validar_config(fonte_id: str, config: dict[str, Any]) -> ConfigJobSpy:
    if fonte_id not in {"jobspy", "indeed", "glassdoor"}:
        raise ValueError("Fonte JobSpy desconhecida")
    modelo = ConfigJobSpy if fonte_id == "jobspy" else ConfigPortaisJobSpy
    return modelo.model_validate(config)


def mapear(item: dict[str, Any], fonte_id: str = "jobspy") -> VagaBruta:
    url = urlsplit(item["job_url"])
    if url.scheme != "https" or url.username or url.password or url.port not in {None, 443}:
        raise ValueError("URL de vaga inválida")
    if fonte_id == "jobspy":
        identificador = re.fullmatch(r"/jobs/view/(\d+)/?", url.path)
        if url.hostname not in {"linkedin.com", "www.linkedin.com"} or not identificador:
            raise ValueError("URL de vaga fora do LinkedIn ou sem ID válido")
        id_externo = identificador[1]
        url_canonica = f"https://www.linkedin.com/jobs/view/{id_externo}"
    elif fonte_id == "indeed":
        id_externo = parse_qs(url.query).get("jk", [""])[0]
        if (
            url.hostname not in {"br.indeed.com", "www.indeed.com", "indeed.com"}
            or url.path != "/viewjob"
            or not re.fullmatch(r"[a-zA-Z0-9]+", id_externo)
        ):
            raise ValueError("URL de vaga fora do Indeed ou sem ID válido")
        url_canonica = f"https://br.indeed.com/viewjob?jk={id_externo}"
    elif fonte_id == "glassdoor":
        id_externo = parse_qs(url.query).get("jl", [""])[0]
        if (
            url.hostname not in {"www.glassdoor.com.br", "glassdoor.com.br"}
            or url.path != "/job-listing/j"
            or not re.fullmatch(r"\d+", id_externo)
        ):
            raise ValueError("URL de vaga fora do Glassdoor ou sem ID válido")
        url_canonica = f"https://www.glassdoor.com.br/job-listing/j?jl={id_externo}"
    else:
        raise ValueError("Fonte JobSpy desconhecida")
    if not item["title"].strip():
        raise ValueError("Vaga sem título válido")

    partes = [p.strip() for p in (item.get("location") or "").split(",") if p.strip()]
    cidade = (
        partes[0]
        if partes and normalizar_chave(partes[0]) not in {"brazil", "brasil", "remoto", "remote"}
        else None
    )
    estado = partes[-2] if len(partes) >= 3 else None
    uf = "DF" if normalizar_chave(estado) == "federal district" else normalizar_uf(estado)
    nivel = inferir_nivel(item["title"])
    if nivel == Nivel.DESCONHECIDO:
        if "internship" in (item.get("job_type") or "").split(", "):
            nivel = Nivel.ESTAGIO
        else:
            nivel = {
                "internship": Nivel.ESTAGIO,
                "entry level": Nivel.JUNIOR,
                "mid senior level": Nivel.SENIOR,
            }.get(normalizar_chave(item.get("job_level")), Nivel.DESCONHECIDO)

    publicada = item.get("date_posted")
    if publicada:
        publicada = datetime.fromisoformat(publicada)
        publicada = publicada.replace(tzinfo=UTC) if publicada.tzinfo is None else publicada

    return VagaBruta(
        fonte_id=fonte_id,
        id_externo=id_externo,
        url=url_canonica,
        titulo=item["title"],
        empresa=item.get("company"),
        descricao=item.get("description"),
        cidade=cidade,
        uf=uf,
        # False significa ausência da indicação de remoto, não confirmação de presencial.
        modalidade=Modalidade.REMOTO if item.get("is_remote") is True else Modalidade.DESCONHECIDA,
        nivel=nivel,
        publicada_em=publicada,
        dados_brutos={
            k: item.get(k)
            for k in (
                "id",
                "job_url",
                "title",
                "company",
                "location",
                "date_posted",
                "is_remote",
                "job_level",
                "job_type",
            )
        },
    )


@registrar("jobspy")
class ColetorJobSpy:
    fonte_id = "jobspy"
    site = "linkedin"

    def __init__(self, http: httpx.Client) -> None:
        # JobSpy gerencia a própria sessão HTTP; mantemos o protocolo dos coletores.
        pass

    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        opcoes = validar_config(self.fonte_id, config)
        if not 1 <= limite <= 50:
            raise ValueError("JobSpy aceita limite de 1 a 50 vagas por execução")

        # Importação tardia: pandas/curl não devem pesar nas outras fontes ou no startup.
        from jobspy import scrape_jobs

        filtros = {}
        if isinstance(opcoes, ConfigPortaisJobSpy):
            filtros = {
                "country_indeed": "brazil",
                "is_remote": opcoes.somente_remoto,
                "job_type": opcoes.tipo_contrato,
            }
        vagas: dict[str, VagaBruta] = {}
        for indice, busca in enumerate(opcoes.buscas):
            if indice:
                time.sleep(opcoes.pausa_s)
            resultado = scrape_jobs(
                site_name=[self.site],
                search_term=busca.termo,
                location=busca.local,
                results_wanted=limite - len(vagas),
                hours_old=opcoes.horas,
                fetch_description=True,
                description_format="plain",
                verbose=1,
                **filtros,
            )
            if avisos := resultado.attrs.get("warnings"):
                log.warning("avisos do JobSpy", extra={"avisos": avisos})
            if erros := resultado.attrs.get("errors"):
                raise RuntimeError(f"{self.site} (JobSpy): {erros}")

            # to_json converte NaN/NaT, tipos numpy e datas antes de persistir em JSONB.
            itens = json.loads(resultado.to_json(orient="records", date_format="iso"))
            for item in itens:
                vaga = mapear(item, self.fonte_id)
                vagas.setdefault(vaga.id_externo, vaga)
                if len(vagas) == limite:
                    return list(vagas.values())
        return list(vagas.values())


@registrar("indeed")
class ColetorIndeed(ColetorJobSpy):
    fonte_id = "indeed"
    site = "indeed"


@registrar("glassdoor")
class ColetorGlassdoor(ColetorJobSpy):
    fonte_id = "glassdoor"
    site = "glassdoor"
