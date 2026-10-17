"""Textos e botões das mensagens do Telegram (HTML, com escape de tudo que vem de fora)."""

import html
import uuid

from job_radar.models import Vaga
from job_radar.models.enums import Modalidade
from job_radar.notificacao.telegram import Botoes

MOTIVOS_IGNORAR = {
    "nivel": "nível",
    "stack": "stack/área",
    "local": "local",
    "empresa": "empresa",
    "outro": "outro",
}

_MODALIDADE = {
    Modalidade.REMOTO: "remoto",
    Modalidade.HIBRIDO: "híbrido",
    Modalidade.PRESENCIAL: "presencial",
}


def _e(texto: object) -> str:
    return html.escape(str(texto), quote=False)


def _lista(itens: list[str], limite: int = 3) -> str:
    return "; ".join(_e(item) for item in itens[:limite])


def texto_recomendacao(vaga: Vaga, auditoria: dict | None, rodape: str | None = None) -> str:
    local = ", ".join(filter(None, [vaga.cidade, vaga.uf]))
    detalhes = " · ".join(
        filter(None, [_e(vaga.empresa) if vaga.empresa else None, _e(local) if local else None])
    )
    modalidade = _MODALIDADE.get(Modalidade(vaga.modalidade))
    linhas = [f"⭐ <b>{_e(vaga.titulo)}</b>"]
    if detalhes or modalidade:
        linhas.append(" · ".join(filter(None, [detalhes, modalidade])))
    if auditoria:
        linhas.append(f"🎯 Score {auditoria['score']} · {_e(auditoria.get('area', 'outro'))}")
        linhas.append("")
        linhas.append(_e(auditoria.get("resumo", "")))
        if auditoria.get("requisitos_atendidos"):
            linhas.append(f"✅ {_lista(auditoria['requisitos_atendidos'])}")
        if auditoria.get("gaps"):
            linhas.append(f"⚠️ {_lista(auditoria['gaps'])}")
        if auditoria.get("red_flags"):
            linhas.append(f"🚩 {_lista(auditoria['red_flags'])}")
    if rodape:
        linhas.append("")
        linhas.append(rodape)
    return "\n".join(linhas)


def botao_abrir(url: str) -> list[dict[str, str]]:
    return [{"text": "🔗 Abrir vaga", "url": url}]


def botoes_recomendacao(vaga_usuario_id: uuid.UUID, url: str) -> Botoes:
    return [
        [
            {"text": "✅ Vou aplicar", "callback_data": f"c:{vaga_usuario_id}"},
            {"text": "❌ Ignorar", "callback_data": f"i:{vaga_usuario_id}"},
        ],
        botao_abrir(url),
    ]


def botoes_motivo(vaga_usuario_id: uuid.UUID, url: str) -> Botoes:
    motivos = [
        {"text": rotulo, "callback_data": f"m:{vaga_usuario_id}:{codigo}"}
        for codigo, rotulo in MOTIVOS_IGNORAR.items()
    ]
    return [motivos[:3], motivos[3:], botao_abrir(url)]
