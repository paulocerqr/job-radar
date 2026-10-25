from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from job_radar.filtro.prefiltro import avaliar
from job_radar.models.enums import Modalidade, Nivel

AGORA = datetime(2026, 10, 17, 12, tzinfo=UTC)


@dataclass
class Vaga:
    titulo: str = "Estágio em DevOps"
    descricao: str | None = "Linux, Docker e Python"
    cidade: str | None = "Brasília"
    uf: str | None = "DF"
    modalidade: str = Modalidade.PRESENCIAL
    nivel: str = Nivel.ESTAGIO
    publicada_em: datetime | None = AGORA - timedelta(days=1)
    criado_em: datetime | None = AGORA - timedelta(days=1)


@dataclass
class Perfil:
    palavras_chave: list[str] = field(
        default_factory=lambda: ["devops", "python", "docker", "linux", "backend"]
    )
    palavras_excluidas: list[str] = field(default_factory=lambda: ["senior", "pleno"])
    niveis: list[str] = field(default_factory=lambda: [Nivel.ESTAGIO.value])
    aceita_remoto: bool = True
    localidades: list[dict] = field(default_factory=lambda: [{"cidade": "Brasília", "uf": "DF"}])


def test_aprova_vaga_ideal_com_score_alto():
    resultado = avaliar(Vaga(), Perfil(), confiabilidade_fonte=80, agora=AGORA)
    assert resultado.aprovada
    # título 40 + descrição 3x5 + recência 15 + fonte 8
    assert resultado.score == 78


def test_reprova_termo_excluido_no_titulo():
    resultado = avaliar(Vaga(titulo="DevOps Sênior"), Perfil(), 80, AGORA)
    assert not resultado.aprovada
    assert "senior" in resultado.motivo


def test_termo_excluido_so_na_descricao_nao_reprova():
    vaga = Vaga(descricao="Você vai trabalhar com pessoas sênior. Python e Docker.")
    assert avaliar(vaga, Perfil(), 80, AGORA).aprovada


def test_reprova_nivel_fora_do_perfil():
    resultado = avaliar(Vaga(titulo="DevOps", nivel=Nivel.JUNIOR), Perfil(), 80, AGORA)
    assert not resultado.aprovada


def test_nivel_desconhecido_penaliza_mais_quem_busca_so_estagio():
    base = avaliar(Vaga(), Perfil(), 80, AGORA).score
    resultado = avaliar(Vaga(nivel=Nivel.DESCONHECIDO), Perfil(), 80, AGORA)
    assert resultado.aprovada
    assert resultado.score == base - 25


def test_nivel_desconhecido_penalidade_normal_para_outros_niveis():
    perfil = replace(Perfil(), niveis=[Nivel.ESTAGIO.value, Nivel.JUNIOR.value])
    base = avaliar(Vaga(), perfil, 80, AGORA).score
    assert avaliar(Vaga(nivel=Nivel.DESCONHECIDO), perfil, 80, AGORA).score == base - 10


def test_reprova_sem_palavra_chave():
    vaga = Vaga(titulo="Estágio em Marketing", descricao="Redes sociais e campanhas")
    assert not avaliar(vaga, Perfil(), 80, AGORA).aprovada


def test_reprova_presencial_fora_das_localidades():
    vaga = Vaga(cidade="São Paulo", uf="SP")
    resultado = avaliar(vaga, Perfil(), 80, AGORA)
    assert not resultado.aprovada
    assert "localidades" in resultado.motivo


def test_remoto_de_qualquer_lugar_passa():
    vaga = Vaga(cidade="São Paulo", uf="SP", modalidade=Modalidade.REMOTO)
    assert avaliar(vaga, Perfil(), 80, AGORA).aprovada


def test_remoto_reprovado_se_perfil_nao_aceita():
    vaga = Vaga(modalidade=Modalidade.REMOTO)
    assert not avaliar(vaga, replace(Perfil(), aceita_remoto=False), 80, AGORA).aprovada


def test_local_desconhecido_passa_com_penalidade():
    base = avaliar(Vaga(), Perfil(), 80, AGORA).score
    resultado = avaliar(Vaga(cidade=None, uf=None), Perfil(), 80, AGORA)
    assert resultado.aprovada
    assert resultado.score == base - 10


def test_vaga_antiga_perde_pontos_de_recencia():
    nova = avaliar(Vaga(), Perfil(), 80, AGORA).score
    antiga = avaliar(Vaga(criado_em=AGORA - timedelta(days=30)), Perfil(), 80, AGORA).score
    assert antiga == nova - 15


def test_perfil_padrao_leva_titulos_de_area_para_a_fila():
    from job_radar.fila.alimentador import SCORE_MINIMO_FILA
    from job_radar.seed import PERFIL_ADMIN_PADRAO

    perfil = Perfil(**{k: PERFIL_ADMIN_PADRAO[k] for k in ("palavras_chave", "palavras_excluidas")})
    # títulos reais de 25/10 que, sem palavra-chave no título, ficavam com nota < 50
    for titulo in ("Estágio em Machine Learning", "Estagiário(a) de Suporte"):
        vaga = Vaga(titulo=titulo, descricao=None, modalidade=Modalidade.HIBRIDO)
        resultado = avaliar(vaga, perfil, confiabilidade_fonte=80, agora=AGORA)
        assert resultado.score >= SCORE_MINIMO_FILA, titulo


def test_desenvolvimento_de_negocios_nao_vira_palavra_chave():
    from job_radar.seed import PERFIL_ADMIN_PADRAO

    perfil = Perfil(palavras_chave=PERFIL_ADMIN_PADRAO["palavras_chave"])
    vaga = Vaga(titulo="Estágio em Desenvolvimento de Negócios", descricao=None)
    assert not avaliar(vaga, perfil, confiabilidade_fonte=80, agora=AGORA).aprovada


def test_recencia_conta_quando_foi_vista_nao_a_publicacao():
    reaproveitada = Vaga(publicada_em=AGORA - timedelta(days=400), criado_em=AGORA)
    assert avaliar(reaproveitada, Perfil(), 80, AGORA).score == 78  # recência cheia (15)
    sem_data = Vaga(criado_em=None)  # ainda não gravada: acabou de ser vista
    assert avaliar(sem_data, Perfil(), 80, AGORA).score == 78
