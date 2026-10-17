"""Chaves de API dos providers cifradas em repouso (RNF04)."""

from cryptography.fernet import Fernet, InvalidToken

from job_radar.config import get_settings


class ChaveFernetAusente(Exception):
    pass


class ChaveFernetInvalida(Exception):
    pass


def gerar_chave() -> str:
    return Fernet.generate_key().decode()


def _fernet() -> Fernet:
    chave = get_settings().fernet_key
    if chave is None:
        raise ChaveFernetAusente("defina FERNET_KEY (gere com `job-radar chave-fernet`)")
    return Fernet(chave.get_secret_value())


def cifrar(texto: str) -> bytes:
    return _fernet().encrypt(texto.encode())


def decifrar(dados: bytes) -> str:
    try:
        return _fernet().decrypt(dados).decode()
    except InvalidToken:
        raise ChaveFernetInvalida("FERNET_KEY não decifra a chave salva (foi trocada?)") from None


def mascarar(chave: str) -> str:
    """Sufixo para exibição: nunca mostrar a chave inteira."""
    return chave[-4:] if len(chave) > 8 else "****"
