import json
import logging
import sys
from datetime import UTC, datetime

_ATRIBUTOS_PADRAO = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class FormatadorJson(logging.Formatter):
    """Uma linha JSON por evento; campos de `extra=` viram chaves no objeto."""

    def format(self, record: logging.LogRecord) -> str:
        dados = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        dados.update({k: v for k, v in vars(record).items() if k not in _ATRIBUTOS_PADRAO})
        if record.exc_info:
            dados["exc"] = self.formatException(record.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar_logs(formato: str, nivel: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if formato == "json":
        handler.setFormatter(FormatadorJson())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.handlers.clear()
    raiz.addHandler(handler)
    raiz.setLevel(nivel.upper())
    # o httpx loga a URL de cada requisição em INFO; na API do Telegram o token do bot
    # faz parte da URL (/bot<TOKEN>/...), então esses logs nunca podem ir para a saída
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
