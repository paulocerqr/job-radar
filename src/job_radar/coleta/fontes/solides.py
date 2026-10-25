"""Solides: endpoint JSON usado pelo próprio portal (vagas.solides.com.br).

Não é uma API oficial nem documentada (achada no bundle do portal, 25/10/2026). Filtra no
servidor por tipo de contrato, modalidade e UF; `take` aceita no máximo 25. A área
"tecnologia" é marcada pelo recrutador e é ruidosa, por isso as buscas não dependem dela:
quem refina é o pré-filtro e a auditoria.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from job_radar.coleta.base import registrar
from job_radar.models.enums import Modalidade, Nivel
from job_radar.schemas.vaga import VagaBruta

log = logging.getLogger(__name__)

URL = "https://apigw.solides.com.br/jobs/v3/vacancies"
TAMANHO_PAGINA = 25

BUSCAS_PADRAO: list[dict[str, str]] = [
    {"contractsType": "estagio", "locations": "DF"},
    {"contractsType": "estagio", "jobsType": "remoto"},
]

_MODALIDADES = {
    "remoto": Modalidade.REMOTO,
    "hibrido": Modalidade.HIBRIDO,
    "presencial": Modalidade.PRESENCIAL,
}


def _nivel(item: dict[str, Any]) -> Nivel:
    contratos = {c.get("name", "").lower() for c in item.get("recruitmentContractType") or []}
    if "estágio" in contratos or "estagio" in contratos:
        return Nivel.ESTAGIO
    return Nivel.DESCONHECIDO


def _publicada_em(item: dict[str, Any]) -> datetime | None:
    # vem só a data ("2026-10-15"); sem fuso, a conta de recência quebraria
    valor = item.get("createdAt")
    if not valor:
        return None
    return datetime.fromisoformat(valor[:10]).replace(tzinfo=UTC)


def mapear(item: dict[str, Any]) -> VagaBruta:
    modalidade = _MODALIDADES.get(item.get("jobType") or "", Modalidade.DESCONHECIDA)
    if item.get("homeOffice"):
        modalidade = Modalidade.REMOTO
    return VagaBruta(
        fonte_id="solides",
        id_externo=str(item["id"]),  # às vezes é texto (vagas integradas de outro sistema)
        # `redirectLink` vem quebrado ("https://empresa./vacancies/..."); este formato abre
        url=f"https://{item['slug']}.vagas.solides.com.br/vaga/{item['id']}",
        titulo=item["title"].strip(),
        empresa=item.get("companyName"),
        descricao=item.get("description"),
        cidade=(item.get("city") or {}).get("name"),
        uf=(item.get("state") or {}).get("code"),
        modalidade=modalidade,
        nivel=_nivel(item),
        publicada_em=_publicada_em(item),
        dados_brutos=item,
    )


@registrar("solides")
class ColetorSolides:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def buscar(self, config: dict[str, Any], limite: int) -> list[VagaBruta]:
        buscas = config.get("buscas", BUSCAS_PADRAO)
        pausa_s = config.get("pausa_s", 1.0)

        vagas: dict[str, VagaBruta] = {}
        for busca in buscas:
            pagina = 1
            while len(vagas) < limite:
                resposta = self.http.get(
                    URL, params={**busca, "page": pagina, "take": TAMANHO_PAGINA}
                )
                resposta.raise_for_status()
                corpo = resposta.json()
                for item in corpo.get("data") or []:
                    if item.get("currentState", "em_andamento") != "em_andamento":
                        continue
                    vagas.setdefault(str(item["id"]), mapear(item))
                log.debug("solides página", extra={"busca": busca, "pagina": pagina})
                if pagina >= (corpo.get("totalPages") or 0):
                    break
                pagina += 1
                time.sleep(pausa_s)
            time.sleep(pausa_s)
        return list(vagas.values())[:limite]
