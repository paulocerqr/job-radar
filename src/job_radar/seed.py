"""Dados iniciais idempotentes: fontes e usuário admin com perfil (PLANO, Fase 0)."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from job_radar.coleta.fontes.gupy import FILTROS_PADRAO, TERMOS_PADRAO
from job_radar.config import Settings
from job_radar.models import Fonte, Perfil, Usuario
from job_radar.models.enums import Nivel, Papel
from job_radar.seguranca.auth import gerar_hash_senha

log = logging.getLogger(__name__)

FONTES_PADRAO = [
    {
        "id": "gupy",
        "nome": "Gupy",
        "ativa": True,
        "intervalo_min": 60,
        "max_itens_execucao": 400,
        "confiabilidade": 80,
        "config": {
            "termos": TERMOS_PADRAO,
            "filtros": FILTROS_PADRAO,
            "tipos": ["vacancy_type_internship"],
        },
    },
    {
        "id": "github_backendbr",
        "nome": "GitHub backend-br/vagas",
        "ativa": True,
        "intervalo_min": 120,
        "max_itens_execucao": 30,
        "confiabilidade": 70,
        "config": {"repositorio": "backend-br/vagas"},
    },
    {
        "id": "greenhouse",
        "nome": "Greenhouse",
        "ativa": False,
        "intervalo_min": 240,
        "max_itens_execucao": 50,
        "confiabilidade": 90,
        "config": {"empresas": []},
    },
    {
        "id": "lever",
        "nome": "Lever",
        "ativa": False,
        "intervalo_min": 240,
        "max_itens_execucao": 50,
        "confiabilidade": 90,
        "config": {"empresas": []},
    },
]

PERFIL_ADMIN_PADRAO = {
    "palavras_chave": [
        "devops", "sre", "infraestrutura", "infra", "cloud", "aws", "gcp", "azure",
        "kubernetes", "docker", "linux", "terraform",
        "backend", "back-end", "fullstack", "full stack", "full-stack",
        "python", "django", "fastapi", "node", "java", "golang",
        # amplos: títulos de estágio raramente citam a stack (a IA refina)
        "ti", "tecnologia da informacao", "tecnologia", "software", "sistemas",
        "desenvolvimento de software", "programacao", "redes",
        # de área: sem nenhuma no título a nota máxima é 43 (< 50 da fila); medido em 25/10
        "machine learning", "inteligencia artificial",
        "dados", "ciencia de dados", "engenharia de dados",
        "desenvolvedor", "programador", "desenvolvimento de sistemas",
        "computacao", "engenharia de software", "ciencia da computacao",
        "suporte", "suporte tecnico", "help desk", "service desk",
        "seguranca da informacao", "ciberseguranca",
        "automacao", "monitoracao", "monitoramento",
        "sql", "javascript", "typescript", "react", "api",
    ],
    "palavras_excluidas": [
        "senior", "sênior", "pleno", "especialista", "lead", "coordenador",
        "gerente", "staff", "principal", "manager", "head", "diretor", "director",
    ],
    "niveis": [Nivel.ESTAGIO.value],
    "aceita_remoto": True,
    "localidades": [{"cidade": "Brasília", "uf": "DF"}],
}  # fmt: skip


class ConfiguracaoSeedInvalida(Exception):
    pass


@dataclass
class ResumoSeed:
    fontes_criadas: int
    admin_criado: bool


def executar_seed(sessao: Session, settings: Settings) -> ResumoSeed:
    # rowcount não é confiável em INSERT de várias linhas; RETURNING lista só as inseridas
    inseridas = sessao.scalars(
        insert(Fonte)
        .values(FONTES_PADRAO)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Fonte.id)
    ).all()
    fontes_criadas = len(inseridas)

    admin_criado = False
    if settings.admin_email:
        existente = sessao.scalar(select(Usuario).where(Usuario.email == settings.admin_email))
        if existente is None:
            if settings.admin_senha is None:
                raise ConfiguracaoSeedInvalida("ADMIN_SENHA é obrigatória para criar o admin")
            sessao.add(
                Usuario(
                    email=settings.admin_email,
                    nome=settings.admin_nome,
                    senha_hash=gerar_hash_senha(settings.admin_senha.get_secret_value()),
                    papel=Papel.ADMIN,
                    perfil=Perfil(**PERFIL_ADMIN_PADRAO),
                )
            )
            admin_criado = True
    else:
        log.warning("ADMIN_EMAIL não definido; usuário admin não será criado")

    sessao.commit()
    return ResumoSeed(fontes_criadas=fontes_criadas, admin_criado=admin_criado)
