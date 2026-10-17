"""Comandos de configuração por usuário: providers de IA e perfil.

Saída voltada a pessoas (typer.echo), não a logs.
"""

import os
import time
from pathlib import Path

import typer
from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_radar.config import get_settings
from job_radar.db import nova_sessao
from job_radar.models import ProviderIA, Usuario
from job_radar.models.enums import Papel, TipoProvider

provider_app = typer.Typer(help="Providers de IA usados na auditoria.", no_args_is_help=True)
perfil_app = typer.Typer(help="Perfil usado no pré-filtro e na auditoria.", no_args_is_help=True)

OpcaoUsuario = typer.Option(None, "--usuario", "-u", help="E-mail do usuário (padrão: ADMIN_EMAIL)")


def _falhar(mensagem: str) -> typer.Exit:
    typer.secho(mensagem, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def _ler_variavel(nome: str) -> str | None:
    """Ambiente do shell primeiro; depois o .env (mesmo arquivo lido pelas Settings)."""
    return os.environ.get(nome) or dotenv_values(".env").get(nome) or None


def _usuario(sessao: Session, email: str | None) -> Usuario:
    email = email or get_settings().admin_email
    if not email:
        raise _falhar("informe --usuario ou defina ADMIN_EMAIL")
    usuario = sessao.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        raise _falhar(f"usuário não encontrado: {email}")
    return usuario


def _provider(sessao: Session, usuario: Usuario, nome: str) -> ProviderIA:
    provider = sessao.scalar(
        select(ProviderIA).where(ProviderIA.usuario_id == usuario.id, ProviderIA.nome == nome)
    )
    if provider is None:
        raise _falhar(f"provider não encontrado: {nome}")
    return provider


@provider_app.command("adicionar")
def adicionar(
    nome: str = typer.Argument(..., help="Nome livre, ex.: groq-llama"),
    preset: str | None = typer.Option(None, help="groq | nvidia | gemini | codex"),
    tipo: TipoProvider | None = typer.Option(None),
    base_url: str | None = typer.Option(None),
    modelo: str | None = typer.Option(None),
    comando: str | None = typer.Option(None, help="Só para tipo cli; use {saida} p/ arquivo"),
    api_key_env: str | None = typer.Option(
        None, help="Variável (ambiente ou .env) com a chave; evita a chave no histórico"
    ),
    prioridade: int | None = typer.Option(None, help="Menor = usado primeiro"),
    tamanho_lote: int | None = typer.Option(None),
    rpm: int | None = typer.Option(None),
    rpd: int | None = typer.Option(None),
    timeout_s: int | None = typer.Option(None),
    usuario_email: str | None = OpcaoUsuario,
) -> None:
    """Cadastra um provider. A chave de API é cifrada com FERNET_KEY antes de ir ao banco."""
    from job_radar.auditoria.presets import PRESETS, Preset
    from job_radar.seguranca.cripto import cifrar, mascarar

    base = PRESETS.get(preset) if preset else None
    if preset and base is None:
        raise _falhar(f"preset desconhecido: {preset} (opções: {', '.join(PRESETS)})")
    base = base or Preset(tipo=tipo or TipoProvider.OPENAI_COMPATIBLE, modelo="")

    tipo_final = tipo or base.tipo
    valores = {
        "base_url": base_url or base.base_url,
        "modelo": modelo or base.modelo,
        "comando": comando or base.comando,
        "tamanho_lote": tamanho_lote or base.tamanho_lote,
        "rpm": rpm if rpm is not None else base.rpm,
        "rpd": rpd if rpd is not None else base.rpd,
        "timeout_s": timeout_s or base.timeout_s,
    }
    if not valores["modelo"]:
        raise _falhar("informe --modelo (ou use um --preset)")

    with nova_sessao() as sessao:
        usuario = _usuario(sessao, usuario_email)
        if tipo_final == TipoProvider.CLI and usuario.papel != Papel.ADMIN:
            raise _falhar("provider cli é exclusivo do admin (RN22)")
        existente = sessao.scalar(
            select(ProviderIA).where(ProviderIA.usuario_id == usuario.id, ProviderIA.nome == nome)
        )
        if existente is not None:
            raise _falhar(f"já existe um provider chamado {nome}")

        chave_cifrada = sufixo = None
        if tipo_final == TipoProvider.OPENAI_COMPATIBLE:
            if not valores["base_url"]:
                raise _falhar("informe --base-url (ou use um --preset)")
            chave = _ler_variavel(api_key_env) if api_key_env else None
            if api_key_env and not chave:
                raise _falhar(f"variável vazia no ambiente e no .env: {api_key_env}")
            chave = chave or typer.prompt("Chave de API", hide_input=True)
            chave_cifrada, sufixo = cifrar(chave), mascarar(chave)

        if prioridade is None:
            maior = sessao.scalar(
                select(func.max(ProviderIA.prioridade)).where(ProviderIA.usuario_id == usuario.id)
            )
            prioridade = (maior or 0) + 1

        sessao.add(
            ProviderIA(
                usuario_id=usuario.id,
                nome=nome,
                tipo=tipo_final,
                prioridade=prioridade,
                api_key_cifrada=chave_cifrada,
                api_key_sufixo=sufixo,
                **valores,
            )
        )
        sessao.commit()
    typer.echo(f"provider {nome} cadastrado (prioridade {prioridade}, modelo {valores['modelo']})")


@provider_app.command("listar")
def listar(usuario_email: str | None = OpcaoUsuario) -> None:
    with nova_sessao() as sessao:
        usuario = _usuario(sessao, usuario_email)
        providers = sessao.scalars(
            select(ProviderIA)
            .where(ProviderIA.usuario_id == usuario.id)
            .order_by(ProviderIA.prioridade)
        ).all()
        if not providers:
            typer.echo("nenhum provider cadastrado")
            return
        for p in providers:
            chave = f"…{p.api_key_sufixo}" if p.api_key_sufixo else "-"
            estado = "ativo" if p.ativo else "inativo"
            typer.echo(
                f"{p.prioridade}. {p.nome} [{p.tipo}, {estado}] modelo={p.modelo} chave={chave}"
                f" lote={p.tamanho_lote} rpm={p.rpm or '-'} rpd={p.rpd or '-'}"
            )
            if p.ultimo_erro:
                typer.secho(f"   último erro ({p.ultimo_erro_em}): {p.ultimo_erro}", fg="yellow")


@provider_app.command("testar")
def testar(nome: str, usuario_email: str | None = OpcaoUsuario) -> None:
    """Faz uma chamada mínima e confere se a resposta vem em JSON."""
    from job_radar.auditoria.providers import construir_provider
    from job_radar.auditoria.providers.base import ErroProvider, RespostaInvalida, extrair_json

    with nova_sessao() as sessao:
        config = _provider(sessao, _usuario(sessao, usuario_email), nome)
        inicio = time.monotonic()
        try:
            resposta = construir_provider(config).completar(
                'Responda somente com o objeto JSON {"ok": true}.', "teste de conexão"
            )
            dados = extrair_json(resposta.texto)
        except (ErroProvider, RespostaInvalida) as erro:
            raise _falhar(f"falhou: {erro}") from None
        segundos = time.monotonic() - inicio
    typer.echo(f"ok em {segundos:.1f}s — modelo {resposta.modelo}, resposta {dados}")


@provider_app.command("modelos")
def modelos(
    nome: str,
    filtro: str | None = typer.Option(None, help="Só ids que contenham este texto"),
    usuario_email: str | None = OpcaoUsuario,
) -> None:
    """Lista os modelos disponíveis para a chave cadastrada (endpoint /models)."""
    from job_radar.auditoria.providers import ProviderOpenAICompativel, construir_provider
    from job_radar.auditoria.providers.base import ErroProvider

    with nova_sessao() as sessao:
        config = _provider(sessao, _usuario(sessao, usuario_email), nome)
        provider = construir_provider(config)
        if not isinstance(provider, ProviderOpenAICompativel):
            raise _falhar("só providers openai_compatible listam modelos")
        try:
            ids = provider.listar_modelos()
        except ErroProvider as erro:
            raise _falhar(f"falhou: {erro}") from None
    for id_modelo in ids:
        if not filtro or filtro.lower() in id_modelo.lower():
            typer.echo(id_modelo)


@provider_app.command("editar")
def editar(
    nome: str,
    modelo: str | None = typer.Option(None),
    prioridade: int | None = typer.Option(None),
    tamanho_lote: int | None = typer.Option(None),
    rpm: int | None = typer.Option(None),
    rpd: int | None = typer.Option(None),
    timeout_s: int | None = typer.Option(None),
    ativo: bool | None = typer.Option(None, "--ativo/--inativo"),
    usuario_email: str | None = OpcaoUsuario,
) -> None:
    """Altera campos de um provider sem recadastrar a chave."""
    alteracoes = {
        campo: valor
        for campo, valor in {
            "modelo": modelo,
            "prioridade": prioridade,
            "tamanho_lote": tamanho_lote,
            "rpm": rpm,
            "rpd": rpd,
            "timeout_s": timeout_s,
            "ativo": ativo,
        }.items()
        if valor is not None
    }
    if not alteracoes:
        raise _falhar("nada para alterar")
    with nova_sessao() as sessao:
        config = _provider(sessao, _usuario(sessao, usuario_email), nome)
        for campo, valor in alteracoes.items():
            setattr(config, campo, valor)
        config.ultimo_erro = None
        config.ultimo_erro_em = None
        sessao.commit()
    typer.echo(f"provider {nome} atualizado: {alteracoes}")


@provider_app.command("remover")
def remover(nome: str, usuario_email: str | None = OpcaoUsuario) -> None:
    with nova_sessao() as sessao:
        sessao.delete(_provider(sessao, _usuario(sessao, usuario_email), nome))
        sessao.commit()
    typer.echo(f"provider {nome} removido")


@perfil_app.command("curriculo")
def curriculo(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    usuario_email: str | None = OpcaoUsuario,
) -> None:
    """Define o currículo (Markdown) usado pela IA para comparar requisitos."""
    with nova_sessao() as sessao:
        usuario = _usuario(sessao, usuario_email)
        if usuario.perfil is None:
            raise _falhar("usuário sem perfil")
        usuario.perfil.curriculo_md = arquivo.read_text()
        sessao.commit()
    typer.echo(f"currículo atualizado ({arquivo.stat().st_size} bytes)")


@perfil_app.command("mostrar")
def mostrar(usuario_email: str | None = OpcaoUsuario) -> None:
    with nova_sessao() as sessao:
        perfil = _usuario(sessao, usuario_email).perfil
        if perfil is None:
            raise _falhar("usuário sem perfil")
        typer.echo(f"níveis: {', '.join(perfil.niveis)}")
        typer.echo(f"aceita remoto: {'sim' if perfil.aceita_remoto else 'não'}")
        locais = ", ".join(
            f"{local.get('cidade')}/{local.get('uf')}" for local in perfil.localidades
        )
        typer.echo(f"localidades: {locais or '-'}")
        typer.echo(f"score mínimo: {perfil.score_minimo}")
        typer.echo(f"palavras-chave: {', '.join(perfil.palavras_chave)}")
        typer.echo(f"excluídas: {', '.join(perfil.palavras_excluidas)}")
        typer.echo(f"currículo: {len(perfil.curriculo_md)} caracteres")
