import itertools
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from job_radar.auditoria.auditor import MAX_TENTATIVAS, auditar
from job_radar.auditoria.providers.base import ErroProvider, LimiteExcedido, RespostaProvider
from job_radar.db import nova_sessao
from job_radar.models import Auditoria, ProviderIA, UsoProvider, Usuario, Vaga, VagaUsuario
from job_radar.models.enums import Papel, StatusVaga, TipoProvider

AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)
_sequencia = itertools.count()


class ProviderRoteirizado:
    """Devolve as respostas na ordem; cada item é um texto ou uma exceção."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = 0
        self.modelo = "fake"

    def completar(self, sistema, usuario):
        self.chamadas += 1
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return RespostaProvider(texto=item, modelo="fake", tokens_entrada=300, tokens_saida=90)


def resposta(*resultados) -> str:
    return json.dumps({"resultados": list(resultados)})


def item(id_, score, nivel=True, modalidade=True, motivo=None):
    return {
        "id": id_,
        "score": score,
        "area": "devops",
        "nivel_compativel": nivel,
        "modalidade_compativel": modalidade,
        "resumo": f"vaga {id_}",
        "motivo_descarte": motivo,
    }


@pytest.fixture
def sessao(banco_com_seed):
    with nova_sessao() as sessao:
        yield sessao


@pytest.fixture
def admin(sessao) -> Usuario:
    return sessao.scalar(select(Usuario).where(Usuario.papel == Papel.ADMIN))


def criar_provider(sessao, usuario, nome, prioridade, tipo=TipoProvider.OPENAI_COMPATIBLE, **kw):
    provider = ProviderIA(
        usuario_id=usuario.id,
        nome=nome,
        tipo=tipo,
        base_url="https://fake/v1" if tipo == TipoProvider.OPENAI_COMPATIBLE else None,
        comando="fake" if tipo == TipoProvider.CLI else None,
        modelo="fake",
        prioridade=prioridade,
        **kw,
    )
    sessao.add(provider)
    sessao.commit()
    return provider


def na_fila(sessao, usuario, quantidade, score_base=50) -> list[VagaUsuario]:
    criadas = []
    for i in range(quantidade):
        n = next(_sequencia)
        vaga = Vaga(hash_dedupe=f"a-{n}", titulo=f"Vaga {n}", url_canonica=f"https://x/{n}")
        sessao.add(vaga)
        sessao.flush()
        vu = VagaUsuario(
            vaga_id=vaga.id,
            usuario_id=usuario.id,
            status=StatusVaga.FILA,
            score_prefiltro=score_base - i,  # ordem previsível: ids 1, 2, 3...
        )
        sessao.add(vu)
        criadas.append(vu)
    sessao.commit()
    return criadas


def recarregar(sessao, objetos):
    for objeto in objetos:
        sessao.refresh(objeto)


def test_aplica_resultado_recomenda_descarta_e_marca_ausente(sessao, admin):
    criar_provider(sessao, admin, "a", 1)
    v1, v2, v3 = na_fila(sessao, admin, 3)
    fake = ProviderRoteirizado(
        [resposta(item("1", 85), item("2", 40, motivo="stack diferente"))]  # "3" ausente
    )

    resumo = auditar(sessao, AGORA, fabrica=lambda _: fake)

    recarregar(sessao, [v1, v2, v3])
    assert v1.status == StatusVaga.RECOMENDADA
    assert v1.score_ia == 85
    assert v1.expira_em == AGORA + timedelta(days=14)
    assert v2.status == StatusVaga.DESCARTADA
    assert v3.status == StatusVaga.ERRO
    assert resumo.recomendadas == [v1.id]
    assert (resumo.descartadas, resumo.erros) == (1, 1)
    assert sessao.scalar(select(func.count()).select_from(Auditoria)) == 3
    (uso,) = sessao.scalars(select(UsoProvider)).all()
    assert (uso.requisicoes, uso.tokens_entrada, uso.erros) == (1, 300, 0)


def test_incompatibilidade_descarta_mesmo_com_score_alto(sessao, admin):
    criar_provider(sessao, admin, "a", 1)
    (vu,) = na_fila(sessao, admin, 1)
    fake = ProviderRoteirizado([resposta(item("1", 95, nivel=False, motivo="vaga sênior"))])

    auditar(sessao, AGORA, fabrica=lambda _: fake)

    sessao.refresh(vu)
    assert vu.status == StatusVaga.DESCARTADA


def test_saida_invalida_tenta_de_novo_e_depois_usa_proximo_provider(sessao, admin):
    a = criar_provider(sessao, admin, "a", 1)
    criar_provider(sessao, admin, "b", 2)
    (vu,) = na_fila(sessao, admin, 1)
    fakes = {
        "a": ProviderRoteirizado(["não é json", '{"resultados": "errado"}']),
        "b": ProviderRoteirizado([resposta(item("1", 90))]),
    }

    auditar(sessao, AGORA, fabrica=lambda cfg: fakes[cfg.nome])

    assert fakes["a"].chamadas == 2  # RN18: uma nova tentativa no mesmo provider
    sessao.refresh(vu)
    sessao.refresh(a)
    assert vu.status == StatusVaga.RECOMENDADA
    assert "saída inválida" in a.ultimo_erro


def test_saida_invalida_em_todos_os_providers_vira_erro(sessao, admin):
    criar_provider(sessao, admin, "a", 1)
    (vu,) = na_fila(sessao, admin, 1)
    fake = ProviderRoteirizado(["lixo", "lixo"])

    resumo = auditar(sessao, AGORA, fabrica=lambda _: fake)

    sessao.refresh(vu)
    assert vu.status == StatusVaga.ERRO
    assert resumo.erros == 1


def test_providers_indisponiveis_aplicam_backoff_e_devolvem_ao_pool(sessao, admin):
    criar_provider(sessao, admin, "a", 1)
    criar_provider(sessao, admin, "b", 2)
    (vu,) = na_fila(sessao, admin, 1)

    def fabrica(cfg):
        if cfg.nome == "a":
            return ProviderRoteirizado([LimiteExcedido("429")])
        return ProviderRoteirizado([ErroProvider("503")])

    auditar(sessao, AGORA, fabrica=fabrica)
    sessao.refresh(vu)
    assert vu.status == StatusVaga.FILA
    assert vu.tentativas == 1
    assert vu.proxima_tentativa_em == AGORA + timedelta(minutes=5)

    # antes do backoff vencer, a vaga não é selecionada
    assert auditar(sessao, AGORA + timedelta(minutes=1), fabrica=fabrica).adiadas == 0

    instante = AGORA
    for _ in range(MAX_TENTATIVAS - 1):
        sessao.refresh(vu)
        instante = vu.proxima_tentativa_em
        auditar(sessao, instante, fabrica=fabrica)
    sessao.refresh(vu)
    assert vu.status == StatusVaga.POOL
    assert vu.tentativas == 0
    assert vu.expira_em == instante + timedelta(days=7)


def test_nao_audita_com_recomendadas_cheias(sessao, admin):
    admin.limite_recomendadas = 0
    sessao.commit()
    criar_provider(sessao, admin, "a", 1)
    (vu,) = na_fila(sessao, admin, 1)
    fake = ProviderRoteirizado([])

    auditar(sessao, AGORA, fabrica=lambda _: fake)

    assert fake.chamadas == 0
    sessao.refresh(vu)
    assert vu.status == StatusVaga.FILA


def test_lote_respeita_tamanho_e_espaco_nas_recomendadas(sessao, admin):
    admin.limite_recomendadas = 2
    sessao.commit()
    criar_provider(sessao, admin, "a", 1, tamanho_lote=5)
    vagas = na_fila(sessao, admin, 4)
    fake = ProviderRoteirizado([resposta(item("1", 90), item("2", 90))])

    auditar(sessao, AGORA, fabrica=lambda _: fake)

    recarregar(sessao, vagas)
    assert [v.status for v in vagas] == [
        StatusVaga.RECOMENDADA,
        StatusVaga.RECOMENDADA,
        StatusVaga.FILA,
        StatusVaga.FILA,
    ]


def test_provider_cli_ignorado_para_quem_nao_e_admin(sessao, admin):
    admin.papel = Papel.USUARIO
    sessao.commit()
    criar_provider(sessao, admin, "codex", 1, tipo=TipoProvider.CLI)
    (vu,) = na_fila(sessao, admin, 1)
    fake = ProviderRoteirizado([])

    auditar(sessao, AGORA, fabrica=lambda _: fake)

    assert fake.chamadas == 0
    sessao.refresh(vu)
    assert vu.status == StatusVaga.FILA


def test_limite_diario_pula_o_provider(sessao, admin):
    a = criar_provider(sessao, admin, "a", 1, rpd=1)
    criar_provider(sessao, admin, "b", 2)
    sessao.add(UsoProvider(provider_id=a.id, dia=AGORA.date(), requisicoes=1))
    sessao.commit()
    (vu,) = na_fila(sessao, admin, 1)
    fakes = {"a": ProviderRoteirizado([]), "b": ProviderRoteirizado([resposta(item("1", 90))])}

    auditar(sessao, AGORA, fabrica=lambda cfg: fakes[cfg.nome])

    assert fakes["a"].chamadas == 0
    sessao.refresh(vu)
    assert vu.status == StatusVaga.RECOMENDADA
