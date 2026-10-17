from datetime import datetime

from pydantic import BaseModel, Field

from job_radar.models.enums import Modalidade, Nivel


class VagaBruta(BaseModel):
    """Vaga como o coletor entende a fonte; o normalizador faz a limpeza genérica."""

    fonte_id: str
    id_externo: str
    url: str
    titulo: str
    empresa: str | None = None
    descricao: str | None = None
    cidade: str | None = None
    uf: str | None = None  # sigla ou nome do estado
    modalidade: Modalidade = Modalidade.DESCONHECIDA
    nivel: Nivel = Nivel.DESCONHECIDO
    publicada_em: datetime | None = None
    dados_brutos: dict = Field(default_factory=dict)


class VagaNormalizada(BaseModel):
    fonte_id: str
    id_externo: str
    url: str
    url_canonica: str
    hash_dedupe: str
    titulo: str
    empresa: str | None
    descricao: str
    cidade: str | None
    uf: str | None
    modalidade: Modalidade
    nivel: Nivel
    publicada_em: datetime | None
    dados_brutos: dict
