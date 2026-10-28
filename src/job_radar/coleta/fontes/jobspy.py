"""LinkedIn público via JobSpy; sem contas, cookies pessoais ou outros portais."""

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

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


def mapear(item: dict[str, Any]) -> VagaBruta:
    url = urlsplit(item["job_url"])
    identificador = re.fullmatch(r"/jobs/view/(\d+)/?", url.path)
    if url.scheme != "https" or url.hostname not in {"linkedin.com", "www.linkedin.com"}:
        raise ValueError("URL de vaga fora do LinkedIn")
    if not identificador or not item["title"].strip():
        raise ValueError("Vaga do LinkedIn sem ID ou título válido")

    partes = [p.strip() for p in (item.get("location") or "").split(",") if p.strip()]
    cidade = (
        partes[0] if partes and normalizar_chave(partes[0]) not in {"brazil", "brasil"} else None
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
        fonte_id="jobspy",
        id_externo=identificador[1],
        url=f"https://www.linkedin.com/jobs/view/{identificador[1]}",
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
    def __init__(self, http: httpx.Client) -> None:
        # JobSpy gerencia a própria sessão HTTP; mantemos o protocolo dos coletores.
        pass

    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        opcoes = ConfigJobSpy.model_validate(config)
        if not 1 <= limite <= 50:
            raise ValueError("JobSpy aceita limite de 1 a 50 vagas por execução")

        # Importação tardia: pandas/curl não devem pesar nas outras fontes ou no startup.
        from jobspy import scrape_jobs

        vagas: dict[str, VagaBruta] = {}
        for indice, busca in enumerate(opcoes.buscas):
            if indice:
                time.sleep(opcoes.pausa_s)
            resultado = scrape_jobs(
                site_name=["linkedin"],
                search_term=busca.termo,
                location=busca.local,
                results_wanted=limite - len(vagas),
                hours_old=opcoes.horas,
                fetch_description=True,
                description_format="plain",
                verbose=1,
            )
            if avisos := resultado.attrs.get("warnings"):
                log.warning("avisos do JobSpy", extra={"avisos": avisos})
            if erros := resultado.attrs.get("errors"):
                raise RuntimeError(f"LinkedIn (JobSpy): {erros}")

            # to_json converte NaN/NaT, tipos numpy e datas antes de persistir em JSONB.
            itens = json.loads(resultado.to_json(orient="records", date_format="iso"))
            for item in itens:
                vaga = mapear(item)
                vagas.setdefault(vaga.id_externo, vaga)
                if len(vagas) == limite:
                    return list(vagas.values())
        return list(vagas.values())
