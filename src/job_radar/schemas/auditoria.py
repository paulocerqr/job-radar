"""Contrato da resposta da IA (PLANO §5.2), validado antes de qualquer transição (RN18)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Area(StrEnum):
    DEVOPS = "devops"
    CLOUD = "cloud"
    INFRA = "infra"
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    OUTRO = "outro"


class ResultadoAuditoria(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    score: int = Field(ge=0, le=100)
    area: Area = Area.OUTRO
    nivel_compativel: bool
    modalidade_compativel: bool = True
    requisitos_atendidos: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    resumo: str
    motivo_descarte: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_como_texto(cls, valor: Any) -> str:
        return str(valor)

    @field_validator("area", mode="before")
    @classmethod
    def _area_desconhecida_vira_outro(cls, valor: Any) -> str:
        valor = str(valor or "").strip().lower()
        return valor if valor in Area._value2member_map_ else Area.OUTRO


class RespostaAuditoria(BaseModel):
    resultados: list[ResultadoAuditoria]
