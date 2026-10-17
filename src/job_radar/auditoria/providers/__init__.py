from job_radar.auditoria.providers.base import Provider
from job_radar.auditoria.providers.cli import ProviderCLI
from job_radar.auditoria.providers.openai_compatible import ProviderOpenAICompativel
from job_radar.models import ProviderIA
from job_radar.models.enums import TipoProvider
from job_radar.seguranca.cripto import decifrar


def construir_provider(config: ProviderIA) -> Provider:
    if config.tipo == TipoProvider.CLI:
        return ProviderCLI(comando=config.comando, modelo=config.modelo, timeout_s=config.timeout_s)
    return ProviderOpenAICompativel(
        base_url=config.base_url,
        api_key=decifrar(config.api_key_cifrada) if config.api_key_cifrada else "",
        modelo=config.modelo,
        timeout_s=config.timeout_s,
    )


__all__ = ["Provider", "ProviderCLI", "ProviderOpenAICompativel", "construir_provider"]
