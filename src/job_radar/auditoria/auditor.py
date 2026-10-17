"""Consome a fila: um lote por usuário a cada rodada (round-robin), com fallback de providers.

Regras: RN16 (um lote por vez), RN17 (lote por chamada), RN18 (JSON validado, 1 retry),
RN19 (score mínimo + compatibilidades → recomendada), RN20 (fallback e backoff),
RN21 (só audita com espaço nas recomendadas), RN22 (CLI só para admin).
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from job_radar.auditoria.limitador import dentro_do_limite, registrar_uso
from job_radar.auditoria.prompt import VERSAO_PROMPT, montar_prompt
from job_radar.auditoria.providers import construir_provider
from job_radar.auditoria.providers.base import (
    ErroProvider,
    Provider,
    RespostaInvalida,
    RespostaProvider,
    extrair_json,
)
from job_radar.fila.alimentador import contar_por_status
from job_radar.fila.estados import transicionar
from job_radar.models import Auditoria, Perfil, ProviderIA, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import OrigemTransicao, Papel, StatusVaga, TipoProvider
from job_radar.schemas.auditoria import RespostaAuditoria

log = logging.getLogger(__name__)

BACKOFF_MIN = (5, 15, 60)
MAX_TENTATIVAS = 5

FabricaProvider = Callable[[ProviderIA], Provider]
Lote = dict[str, tuple[VagaUsuario, Vaga]]


@dataclass
class ResumoAuditoria:
    recomendadas: list[uuid.UUID] = field(default_factory=list)
    descartadas: int = 0
    erros: int = 0
    adiadas: int = 0

    def somar(self, outro: "ResumoAuditoria") -> None:
        self.recomendadas += outro.recomendadas
        self.descartadas += outro.descartadas
        self.erros += outro.erros
        self.adiadas += outro.adiadas


def providers_do_usuario(sessao: Session, usuario: Usuario) -> list[ProviderIA]:
    providers = sessao.scalars(
        select(ProviderIA)
        .where(ProviderIA.usuario_id == usuario.id, ProviderIA.ativo)
        .order_by(ProviderIA.prioridade)
    ).all()
    if usuario.papel != Papel.ADMIN:  # RN22
        return [p for p in providers if p.tipo != TipoProvider.CLI]
    return list(providers)


def selecionar_lote(
    sessao: Session, usuario: Usuario, tamanho: int, agora: datetime
) -> list[VagaUsuario]:
    return list(
        sessao.scalars(
            select(VagaUsuario)
            .where(
                VagaUsuario.usuario_id == usuario.id,
                VagaUsuario.status == StatusVaga.FILA,
                or_(
                    VagaUsuario.proxima_tentativa_em.is_(None),
                    VagaUsuario.proxima_tentativa_em <= agora,
                ),
            )
            .order_by(VagaUsuario.score_prefiltro.desc())
            .limit(tamanho)
            .with_for_update(skip_locked=True)
        ).all()
    )


def _registrar_falha(
    sessao: Session, config: ProviderIA, lote: Lote, erro: str, duracao_ms: int, agora: datetime
) -> None:
    config.ultimo_erro = erro[:500]
    config.ultimo_erro_em = agora
    for vaga_usuario, _ in lote.values():
        sessao.add(
            Auditoria(
                vaga_usuario_id=vaga_usuario.id,
                provider_id=config.id,
                modelo=config.modelo,
                versao_prompt=VERSAO_PROMPT,
                sucesso=False,
                erro=erro[:1000],
                duracao_ms=duracao_ms,
            )
        )


def _aplicar(
    sessao: Session,
    perfil: Perfil,
    lote: Lote,
    validada: RespostaAuditoria,
    config: ProviderIA,
    resposta: RespostaProvider,
    duracao_ms: int,
    agora: datetime,
) -> ResumoAuditoria:
    resumo = ResumoAuditoria()
    por_id = {resultado.id: resultado for resultado in validada.resultados}
    n = len(lote)
    for id_curto, (vaga_usuario, _) in lote.items():
        resultado = por_id.get(id_curto)
        auditoria = Auditoria(
            vaga_usuario_id=vaga_usuario.id,
            provider_id=config.id,
            modelo=resposta.modelo,
            versao_prompt=VERSAO_PROMPT,
            sucesso=resultado is not None,
            resultado=resultado.model_dump(mode="json") if resultado else None,
            erro=None if resultado else "vaga ausente na resposta",
            duracao_ms=duracao_ms,
            tokens_entrada=resposta.tokens_entrada // n if resposta.tokens_entrada else None,
            tokens_saida=resposta.tokens_saida // n if resposta.tokens_saida else None,
        )
        sessao.add(auditoria)
        if resultado is None:
            transicionar(sessao, vaga_usuario, StatusVaga.ERRO, OrigemTransicao.IA, auditoria.erro)
            resumo.erros += 1
            continue

        vaga_usuario.score_ia = resultado.score
        aprovada = (
            resultado.score >= perfil.score_minimo
            and resultado.nivel_compativel
            and resultado.modalidade_compativel
        )
        if aprovada:  # RN19
            transicionar(
                sessao,
                vaga_usuario,
                StatusVaga.RECOMENDADA,
                OrigemTransicao.IA,
                f"score {resultado.score}",
            )
            vaga_usuario.expira_em = agora + timedelta(days=perfil.ttl_recomendada_dias)
            resumo.recomendadas.append(vaga_usuario.id)
        else:
            motivo = resultado.motivo_descarte or resultado.resumo
            transicionar(
                sessao,
                vaga_usuario,
                StatusVaga.DESCARTADA,
                OrigemTransicao.IA,
                f"score {resultado.score}: {motivo}"[:500],
            )
            resumo.descartadas += 1
    return resumo


def _adiar(sessao: Session, perfil: Perfil, lote: Lote, agora: datetime) -> ResumoAuditoria:
    """RN20: nenhum provider disponível → backoff; depois de 5 tentativas volta ao pool."""
    for vaga_usuario, _ in lote.values():
        vaga_usuario.tentativas += 1
        if vaga_usuario.tentativas >= MAX_TENTATIVAS:
            transicionar(
                sessao,
                vaga_usuario,
                StatusVaga.POOL,
                OrigemTransicao.SISTEMA,
                f"providers indisponíveis após {MAX_TENTATIVAS} tentativas",
            )
            vaga_usuario.tentativas = 0
            vaga_usuario.proxima_tentativa_em = None
            vaga_usuario.expira_em = agora + timedelta(days=perfil.ttl_pool_dias)
        else:
            indice = min(vaga_usuario.tentativas, len(BACKOFF_MIN)) - 1
            vaga_usuario.proxima_tentativa_em = agora + timedelta(minutes=BACKOFF_MIN[indice])
    return ResumoAuditoria(adiadas=len(lote))


def auditar_usuario(
    sessao: Session,
    usuario: Usuario,
    agora: datetime,
    fabrica: FabricaProvider = construir_provider,
) -> ResumoAuditoria:
    perfil = usuario.perfil
    if perfil is None:
        return ResumoAuditoria()
    espaco = usuario.limite_recomendadas - contar_por_status(
        sessao, usuario, StatusVaga.RECOMENDADA
    )
    if espaco <= 0:  # RN21
        return ResumoAuditoria()
    configs = providers_do_usuario(sessao, usuario)
    if not configs:
        log.warning("usuário sem provider de IA ativo", extra={"usuario": str(usuario.id)})
        return ResumoAuditoria()

    vagas_usuario = selecionar_lote(sessao, usuario, min(configs[0].tamanho_lote, espaco), agora)
    if not vagas_usuario:
        return ResumoAuditoria()
    lote: Lote = {
        str(i): (vu, sessao.get_one(Vaga, vu.vaga_id)) for i, vu in enumerate(vagas_usuario, 1)
    }
    sistema, conteudo = montar_prompt(perfil, [(i, vaga) for i, (_, vaga) in lote.items()])

    respostas_invalidas = 0
    falhas_de_chamada = 0
    for config in configs:
        if not dentro_do_limite(sessao, config, agora.date()):
            falhas_de_chamada += 1
            continue
        for _tentativa in range(2):  # RN18: uma nova tentativa para saída inválida
            inicio = time.monotonic()
            try:
                resposta = _construir(fabrica, config).completar(sistema, conteudo)
            except ErroProvider as erro:
                duracao = int((time.monotonic() - inicio) * 1000)
                registrar_uso(sessao, config, agora.date(), None, erro=True)
                _registrar_falha(sessao, config, lote, f"chamada: {erro}", duracao, agora)
                falhas_de_chamada += 1
                log.warning("provider falhou", extra={"provider": config.nome, "erro": str(erro)})
                break  # próximo provider
            duracao = int((time.monotonic() - inicio) * 1000)
            registrar_uso(sessao, config, agora.date(), resposta, erro=False)
            try:
                validada = RespostaAuditoria.model_validate(extrair_json(resposta.texto))
            except (RespostaInvalida, ValidationError) as erro:
                _registrar_falha(sessao, config, lote, f"saída inválida: {erro}", duracao, agora)
                respostas_invalidas += 1
                continue  # mesmo provider, mais uma vez
            return _aplicar(sessao, perfil, lote, validada, config, resposta, duracao, agora)

    if respostas_invalidas and not falhas_de_chamada:
        # todos responderam, mas nenhum em formato válido: problema de prompt/modelo
        for vaga_usuario, _ in lote.values():
            transicionar(
                sessao,
                vaga_usuario,
                StatusVaga.ERRO,
                OrigemTransicao.IA,
                "saída inválida em todos os providers",
            )
        return ResumoAuditoria(erros=len(lote))
    return _adiar(sessao, perfil, lote, agora)


def _construir(fabrica: FabricaProvider, config: ProviderIA) -> Provider:
    try:
        return fabrica(config)
    except ErroProvider:
        raise
    except Exception as erro:  # ex.: FERNET_KEY ausente/trocada
        raise ErroProvider(f"configuração inválida: {erro}", transitorio=False) from None


def auditar(
    sessao: Session,
    agora: datetime | None = None,
    fabrica: FabricaProvider = construir_provider,
) -> ResumoAuditoria:
    """Uma rodada: no máximo um lote por usuário ativo."""
    agora = agora or datetime.now(UTC)
    total = ResumoAuditoria()
    for usuario in sessao.scalars(select(Usuario).where(Usuario.ativo)).all():
        try:
            resumo = auditar_usuario(sessao, usuario, agora, fabrica)
            sessao.commit()
        except Exception:
            sessao.rollback()
            log.exception("falha ao auditar usuário", extra={"usuario": str(usuario.id)})
            continue
        total.somar(resumo)
    if total.recomendadas or total.descartadas or total.erros or total.adiadas:
        log.info(
            "rodada de auditoria",
            extra={
                "recomendadas": len(total.recomendadas),
                "descartadas": total.descartadas,
                "erros": total.erros,
                "adiadas": total.adiadas,
            },
        )
    return total
