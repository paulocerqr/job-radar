"""Limites por provider: rpm em memória (worker é singleton, D16) e rpd persistido no banco."""

import time
from collections import defaultdict, deque
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from job_radar.auditoria.providers.base import RespostaProvider
from job_radar.models import ProviderIA, UsoProvider

_chamadas_recentes: dict[object, deque[float]] = defaultdict(deque)


def dentro_do_limite(sessao: Session, provider: ProviderIA, hoje: date) -> bool:
    if provider.rpm:
        janela = _chamadas_recentes[provider.id]
        agora = time.monotonic()
        while janela and agora - janela[0] >= 60:
            janela.popleft()
        if len(janela) >= provider.rpm:
            return False
    if provider.rpd:
        uso = sessao.get(UsoProvider, (provider.id, hoje))
        if uso is not None and uso.requisicoes >= provider.rpd:
            return False
    return True


def registrar_uso(
    sessao: Session,
    provider: ProviderIA,
    hoje: date,
    resposta: RespostaProvider | None,
    erro: bool,
) -> None:
    _chamadas_recentes[provider.id].append(time.monotonic())
    incremento = {
        "requisicoes": 1,
        "tokens_entrada": (resposta.tokens_entrada or 0) if resposta else 0,
        "tokens_saida": (resposta.tokens_saida or 0) if resposta else 0,
        "erros": int(erro),
    }
    comando = insert(UsoProvider).values(provider_id=provider.id, dia=hoje, **incremento)
    sessao.execute(
        comando.on_conflict_do_update(
            index_elements=["provider_id", "dia"],
            set_={
                campo: getattr(UsoProvider, campo) + valor for campo, valor in incremento.items()
            },
        )
    )
