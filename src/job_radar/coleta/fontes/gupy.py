"""Gupy: endpoint JSON usado pelo próprio portal (portal.gupy.io/job-search).

Não é uma API oficial. O parâmetro `jobName` busca só no **título**, por trecho, e a
busca trata o termo como frase ("estágio devops" não acha "Estágio em DevOps"). Por isso
os termos são amplos ("ti", "tecnologia", ...) combinados com o filtro de tipo de vaga;
quem refina é o pré-filtro e a auditoria.
"""

import logging
import time
from typing import Any

import httpx

from job_radar.coleta.base import registrar
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta

log = logging.getLogger(__name__)

URL = "https://portal.gupy.io/api/job-search/jobs"
TAMANHO_PAGINA = 100

TERMOS_PADRAO = ["ti", "tecnologia", "desenvolvimento", "infraestrutura", "software"]
TIPOS_PADRAO = ["vacancy_type_internship"]

_MODALIDADES = {
    "on-site": Modalidade.PRESENCIAL,
    "hybrid": Modalidade.HIBRIDO,
    "remote": Modalidade.REMOTO,
}
_NIVEIS = {
    "vacancy_type_internship": Nivel.ESTAGIO,
    "vacancy_type_trainee": Nivel.TRAINEE,
}


def mapear(item: dict[str, Any]) -> VagaBruta:
    return VagaBruta(
        fonte_id="gupy",
        id_externo=str(item["id"]),
        url=item["jobUrl"],
        titulo=item["name"],
        empresa=item.get("careerPageName"),
        descricao=item.get("description"),
        cidade=item.get("city"),
        uf=item.get("state"),
        modalidade=_MODALIDADES.get(item.get("workplaceType") or "", Modalidade.DESCONHECIDA),
        nivel=_NIVEIS.get(item.get("type") or "", Nivel.DESCONHECIDO),
        publicada_em=item.get("publishedDate"),
        dados_brutos=item,
    )


@registrar("gupy")
class ColetorGupy:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        termos = config.get("termos", TERMOS_PADRAO)
        tipos = config.get("tipos", TIPOS_PADRAO)
        pausa_s = config.get("pausa_s", 1.0)

        vagas: dict[str, VagaBruta] = {}
        for termo in termos:
            for tipo in tipos:
                offset = 0
                while len(vagas) < limite:
                    resposta = self.http.get(
                        URL,
                        params={
                            "jobName": termo,
                            "type": tipo,
                            "limit": TAMANHO_PAGINA,
                            "offset": offset,
                        },
                    )
                    resposta.raise_for_status()
                    corpo = resposta.json()
                    itens = corpo.get("data") or []
                    for item in itens:
                        vagas.setdefault(str(item["id"]), mapear(item))
                    offset += len(itens)
                    total = (corpo.get("pagination") or {}).get("total", 0)
                    log.debug("gupy página", extra={"termo": termo, "offset": offset})
                    if not itens or offset >= total:
                        break
                    time.sleep(pausa_s)
                time.sleep(pausa_s)
        return list(vagas.values())[:limite]
