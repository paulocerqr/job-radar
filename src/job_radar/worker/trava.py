"""Trava de worker único no Postgres (D16).

A estratégia `Recreate` do Kubernetes só garante 1 worker em rollouts: quando o pod é
apagado, despejado (drain) ou cai com o nó, o substituto sobe enquanto o antigo ainda
encerra. Com a trava, o worker novo só agenda os jobs e faz polling do Telegram depois
que o antigo soltar a conexão (padrão de leader election).

A trava é um advisory lock de sessão: fica presa a uma conexão dedicada e o Postgres a
libera sozinho quando essa conexão fecha, inclusive se o processo morrer.
"""

import logging

from sqlalchemy import Connection, Engine, text

log = logging.getLogger(__name__)

CHAVE = 4_652_001  # identificador da trava do worker; qualquer inteiro fixo e único

# Keepalive da sessão no lado do Postgres: se o nó do worker cair sem fechar a conexão,
# a trava é liberada em ~1 min (30 s + 3 x 10 s) em vez das ~2 h do padrão do sistema.
KEEPALIVE = {"tcp_keepalives_idle": 30, "tcp_keepalives_interval": 10, "tcp_keepalives_count": 3}


class TravaWorker:
    def __init__(self, engine: Engine, chave: int = CHAVE) -> None:
        self.engine = engine
        self.chave = chave
        self._conexao: Connection | None = None

    def tentar(self) -> bool:
        """Tenta pegar a trava sem bloquear; True se este processo ficou com ela."""
        self.liberar()
        conexao = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            for parametro, valor in KEEPALIVE.items():
                conexao.execute(text(f"SET {parametro} = {int(valor)}"))
            obtida = conexao.execute(
                text("SELECT pg_try_advisory_lock(:chave)"), {"chave": self.chave}
            ).scalar_one()
        except Exception:
            conexao.close()
            raise
        if obtida:
            self._conexao = conexao
        else:
            conexao.close()
        return bool(obtida)

    def mantida(self) -> bool:
        """True se a conexão da trava continua viva e ainda segura a trava."""
        if self._conexao is None:
            return False
        try:
            return bool(
                self._conexao.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory'"
                        # chave de 1 bigint < 2^32: classid 0, objid = chave, objsubid 1
                        " AND classid = 0 AND objid = :chave AND objsubid = 1"
                        " AND pid = pg_backend_pid() AND granted)"
                    ),
                    {"chave": self.chave},
                ).scalar_one()
            )
        except Exception:
            log.warning("conexão da trava do worker perdida", exc_info=True)
            return False

    def liberar(self) -> None:
        if self._conexao is None:
            return
        conexao, self._conexao = self._conexao, None
        try:
            conexao.execute(text("SELECT pg_advisory_unlock(:chave)"), {"chave": self.chave})
        except Exception:
            pass  # conexão já caiu: o Postgres soltou a trava junto
        finally:
            conexao.close()
