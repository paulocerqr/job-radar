"""Valores iniciais por provider. Modelos e limites mudam: confira no painel de cada um
e sobrescreva com --modelo/--rpm/--rpd no `job-radar provider adicionar`."""

from dataclasses import dataclass

from job_radar.models.enums import TipoProvider


@dataclass(frozen=True)
class Preset:
    tipo: TipoProvider
    modelo: str
    base_url: str | None = None
    comando: str | None = None
    rpm: int | None = None
    rpd: int | None = None
    tamanho_lote: int = 5
    timeout_s: int = 120


PRESETS: dict[str, Preset] = {
    "groq": Preset(
        tipo=TipoProvider.OPENAI_COMPATIBLE,
        base_url="https://api.groq.com/openai/v1",
        modelo="llama-3.3-70b-versatile",
        rpm=30,
        rpd=1000,
    ),
    "nvidia": Preset(
        tipo=TipoProvider.OPENAI_COMPATIBLE,
        base_url="https://integrate.api.nvidia.com/v1",
        modelo="nvidia/llama-3.3-nemotron-super-49b-v1",
        rpm=40,
    ),
    "gemini": Preset(
        tipo=TipoProvider.OPENAI_COMPATIBLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        modelo="gemini-2.5-flash",
        rpm=10,
        rpd=250,
    ),
    "codex": Preset(
        tipo=TipoProvider.CLI,
        # somente leitura, sem salvar sessão; o prompt vai pelo stdin ("-")
        comando=(
            "codex exec --skip-git-repo-check --ephemeral --sandbox read-only"
            " --color never -o {saida} -"
        ),
        modelo="codex (modelo padrão da conta)",
        timeout_s=300,
    ),
}
