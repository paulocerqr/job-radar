from enum import StrEnum


class Papel(StrEnum):
    ADMIN = "admin"
    USUARIO = "usuario"


class TipoProvider(StrEnum):
    CLI = "cli"
    OPENAI_COMPATIBLE = "openai_compatible"


class TipoCanal(StrEnum):
    TELEGRAM = "telegram"
    EMAIL = "email"


class StatusExecucao(StrEnum):
    RODANDO = "rodando"
    OK = "ok"
    ERRO = "erro"
    PARCIAL = "parcial"


class Modalidade(StrEnum):
    REMOTO = "remoto"
    PRESENCIAL = "presencial"
    HIBRIDO = "hibrido"
    DESCONHECIDA = "desconhecida"


class Nivel(StrEnum):
    ESTAGIO = "estagio"
    TRAINEE = "trainee"
    JUNIOR = "junior"
    PLENO = "pleno"
    SENIOR = "senior"
    DESCONHECIDO = "desconhecido"


class StatusVaga(StrEnum):
    POOL = "pool"
    FILA = "fila"
    RECOMENDADA = "recomendada"
    CONFIRMADA = "confirmada"
    DESCARTADA = "descartada"
    IGNORADA = "ignorada"
    EXPIRADA = "expirada"
    ERRO = "erro"


class OrigemTransicao(StrEnum):
    SISTEMA = "sistema"
    IA = "ia"
    USUARIO = "usuario"
