"""Valores iniciais por provider (modelos verificados em 21/10/2026).

Modelos são aposentados com frequência: liste os disponíveis com `job-radar provider modelos`
e troque com `job-radar provider editar <nome> --modelo ...`. A NVIDIA lista modelos que já
não atendem (404 "Function ... Not found"): confirme sempre com `job-radar provider testar`."""

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
        modelo="openai/gpt-oss-120b",
        rpm=30,
        rpd=1000,
    ),
    "nvidia": Preset(
        tipo=TipoProvider.OPENAI_COMPATIBLE,
        base_url="https://integrate.api.nvidia.com/v1",
        modelo="nvidia/nemotron-3.5-lightning-30b-a3b",  # o 3-super saiu do ar (404) em 21/10
        rpm=40,
    ),
    "gemini": Preset(
        tipo=TipoProvider.OPENAI_COMPATIBLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        modelo="gemini-3.8-flash",
        rpm=10,
        rpd=250,
        timeout_s=300,  # modelo com raciocínio: ~50-90 s mesmo para respostas curtas
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
