"""Prompt de auditoria. Toda mudança de texto ou critério sobe a versão (fica em `auditoria`)."""

import json
from collections.abc import Sequence

from job_radar.models import Perfil, Vaga

VERSAO_PROMPT = "v1"
LIMITE_DESCRICAO = 6000

SISTEMA = """\
Você é um recrutador técnico que audita vagas de emprego para UM candidato específico.
Para cada vaga recebida, avalie a aderência ao perfil do candidato e responda SOMENTE com um
objeto JSON, sem texto antes ou depois, neste formato:

{"resultados": [{
  "id": "<mesmo id da vaga>",
  "score": <inteiro 0-100>,
  "area": "devops" | "cloud" | "infra" | "backend" | "fullstack" | "outro",
  "nivel_compativel": <true|false>,
  "modalidade_compativel": <true|false>,
  "requisitos_atendidos": ["..."],
  "gaps": ["..."],
  "red_flags": ["..."],
  "resumo": "<1 a 3 frases em português>",
  "motivo_descarte": "<texto>" | null
}]}

Critérios:
- score: aderência geral (área, stack, nível, local).
  80+ excelente, 60-79 boa, abaixo de 60 fraca.
- nivel_compativel: a vaga aceita alguém no nível do candidato? Vaga sênior para quem busca
  estágio é false. Vaga de estágio exigindo anos de experiência também é false.
- modalidade_compativel: modalidade e local são viáveis para o candidato (ver localidades e
  aceita_remoto)?
- requisitos_atendidos / gaps: compare os requisitos da vaga com o currículo e as áreas
  de interesse.
- red_flags: sinais de vaga ruim (exigências incompatíveis com o nível, descrição genérica demais,
  vaga que não é da área de tecnologia, indícios de golpe).
- motivo_descarte: obrigatório quando score < 60 ou alguma compatibilidade for false; senão null.
- Responda exatamente um item por vaga, com o mesmo id. Não invente informação ausente na vaga.
"""


def _descricao(vaga: Vaga) -> str:
    texto = vaga.descricao or ""
    if len(texto) > LIMITE_DESCRICAO:
        return texto[:LIMITE_DESCRICAO] + " [...]"
    return texto


def montar_prompt(perfil: Perfil, vagas: Sequence[tuple[str, Vaga]]) -> tuple[str, str]:
    """Retorna (sistema, usuario). `vagas` são pares (id curto, vaga)."""
    conteudo = {
        "candidato": {
            "curriculo": perfil.curriculo_md or "(não informado)",
            "niveis_buscados": perfil.niveis,
            "areas_de_interesse": perfil.palavras_chave,
            "aceita_remoto": perfil.aceita_remoto,
            "localidades_presenciais": perfil.localidades,
        },
        "vagas": [
            {
                "id": id_curto,
                "titulo": vaga.titulo,
                "empresa": vaga.empresa,
                "local": ", ".join(filter(None, [vaga.cidade, vaga.uf])) or None,
                "modalidade": vaga.modalidade,
                "nivel_informado": vaga.nivel,
                "descricao": _descricao(vaga),
            }
            for id_curto, vaga in vagas
        ],
    }
    return SISTEMA, json.dumps(conteudo, ensure_ascii=False, indent=1)
