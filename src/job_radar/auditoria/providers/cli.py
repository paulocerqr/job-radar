"""CLI local autenticado na conta do admin (Codex, Claude Code). Só para o admin (RN22, D08).

O prompt vai pelo stdin. Se o comando contiver `{saida}`, a resposta é lida desse arquivo
(ex.: `codex exec ... -o {saida} -`); senão, do stdout. Roda numa pasta temporária vazia,
para o agente não enxergar nenhum repositório.
"""

import shlex
import subprocess
import tempfile
from pathlib import Path

from job_radar.auditoria.providers.base import ErroProvider, RespostaProvider

MARCADOR_SAIDA = "{saida}"
MARCADOR_MODELO = "{modelo}"


class ProviderCLI:
    def __init__(self, comando: str, modelo: str, timeout_s: int = 300) -> None:
        self.comando = comando
        self.modelo = modelo
        self.timeout_s = timeout_s

    def completar(self, sistema: str, usuario: str) -> RespostaProvider:
        prompt = f"{sistema}\n\n{usuario}"
        with tempfile.TemporaryDirectory(prefix="job-radar-cli-") as pasta:
            saida = Path(pasta) / "resposta.txt"
            argumentos = [
                arg.replace(MARCADOR_SAIDA, str(saida)).replace(MARCADOR_MODELO, self.modelo)
                for arg in shlex.split(self.comando)
            ]
            try:
                processo = subprocess.run(
                    argumentos,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    cwd=pasta,
                    check=False,
                )
            except FileNotFoundError:
                raise ErroProvider(
                    f"comando não encontrado: {argumentos[0]}", transitorio=False
                ) from None
            except subprocess.TimeoutExpired:
                raise ErroProvider(f"tempo esgotado ({self.timeout_s}s)") from None

            if processo.returncode != 0:
                raise ErroProvider(f"código {processo.returncode}: {processo.stderr[-300:]}")
            if MARCADOR_SAIDA in self.comando:
                if not saida.exists():
                    raise ErroProvider("o comando não gravou a resposta em {saida}")
                texto = saida.read_text()
            else:
                texto = processo.stdout
        return RespostaProvider(texto=texto, modelo=self.modelo)
