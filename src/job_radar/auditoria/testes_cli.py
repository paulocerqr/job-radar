"""A API solicita o teste; o worker autenticado executa antes de auditar vagas."""

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_radar.auditoria.providers import construir_provider
from job_radar.auditoria.providers.base import ErroProvider, RespostaInvalida, extrair_json
from job_radar.models import ProviderIA, Usuario
from job_radar.models.enums import Papel, TipoProvider

log = logging.getLogger(__name__)


def resultado_teste(config: ProviderIA) -> dict | None:
    teste = config.teste_conexao
    if (
        teste
        and teste.get("pendente")
        and datetime.now(UTC) - datetime.fromisoformat(teste["solicitado_em"])
        > timedelta(minutes=15)
    ):
        return {
            "ok": False,
            "erro": "O worker não concluiu o teste em 15 minutos. Tente novamente.",
        }
    return teste


def executar_teste_pendente(sessao: Session) -> None:
    config = sessao.scalar(
        select(ProviderIA)
        .join(Usuario, Usuario.id == ProviderIA.usuario_id)
        .where(
            ProviderIA.tipo == TipoProvider.CLI,
            ProviderIA.teste_conexao["pendente"].as_boolean().is_(True),
            Usuario.papel == Papel.ADMIN,
            Usuario.ativo,
        )
        .order_by(ProviderIA.teste_conexao["solicitado_em"].as_string())
        .limit(1)
        .with_for_update(of=ProviderIA, skip_locked=True)
    )
    if config is None:
        return
    resultado = resultado_teste(config)
    if resultado.get("pendente"):
        inicio = time.monotonic()
        try:
            resposta = construir_provider(config).completar(
                'Responda somente com o objeto JSON {"ok": true}.', "teste de conexão"
            )
            extrair_json(resposta.texto)
            resultado = {
                "ok": True,
                "segundos": round(time.monotonic() - inicio, 1),
                "modelo": resposta.modelo,
            }
        except (ErroProvider, RespostaInvalida) as erro:
            resultado = {"ok": False, "erro": str(erro)[:300]}
        except Exception:
            log.exception("falha inesperada no teste CLI", extra={"provider": str(config.id)})
            resultado = {"ok": False, "erro": "Falha interna no teste. Consulte os logs do worker."}
    config.teste_conexao = resultado
    sessao.commit()
