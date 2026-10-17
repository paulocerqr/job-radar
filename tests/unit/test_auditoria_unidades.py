import json

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from job_radar.auditoria.prompt import LIMITE_DESCRICAO, montar_prompt
from job_radar.config import get_settings
from job_radar.models import Perfil, Vaga
from job_radar.schemas.auditoria import Area, ResultadoAuditoria
from job_radar.seguranca.cripto import ChaveFernetAusente, cifrar, decifrar, mascarar

# ---------- cripto


def test_cifrar_e_decifrar(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    cifrada = cifrar("gsk_segredo")
    assert b"gsk_segredo" not in cifrada
    assert decifrar(cifrada) == "gsk_segredo"


def test_cifrar_sem_chave(monkeypatch):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.setenv("FERNET_KEY", "")
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "fernet_key", None)
    with pytest.raises(ChaveFernetAusente):
        cifrar("x")


def test_mascarar():
    assert mascarar("gsk_1234567890abcd") == "abcd"
    assert mascarar("curta") == "****"


# ---------- schema


def resultado(**campos):
    base = {"id": "1", "score": 80, "nivel_compativel": True, "resumo": "ok"}
    return ResultadoAuditoria.model_validate(base | campos)


def test_resultado_converte_id_numerico():
    assert resultado(id=3).id == "3"


def test_area_desconhecida_vira_outro():
    assert resultado(area="Data Science").area == Area.OUTRO
    assert resultado(area="DevOps").area == Area.DEVOPS


@pytest.mark.parametrize("score", [-1, 101])
def test_score_fora_da_faixa(score):
    with pytest.raises(ValidationError):
        resultado(score=score)


def test_campos_obrigatorios():
    with pytest.raises(ValidationError):
        ResultadoAuditoria.model_validate({"id": "1", "score": 50})


# ---------- prompt


def test_prompt_inclui_perfil_e_vagas_com_ids_curtos():
    perfil = Perfil(
        curriculo_md="Estudante de ADS",
        niveis=["estagio"],
        palavras_chave=["devops"],
        aceita_remoto=True,
        localidades=[{"cidade": "Brasília", "uf": "DF"}],
    )
    vaga = Vaga(
        titulo="Estágio DevOps",
        empresa="ACME",
        cidade="Brasília",
        uf="DF",
        modalidade="presencial",
        nivel="estagio",
        descricao="x" * (LIMITE_DESCRICAO + 100),
    )
    sistema, usuario = montar_prompt(perfil, [("1", vaga)])

    assert "JSON" in sistema
    dados = json.loads(usuario)
    assert dados["candidato"]["curriculo"] == "Estudante de ADS"
    (item,) = dados["vagas"]
    assert item["id"] == "1"
    assert item["local"] == "Brasília, DF"
    assert item["descricao"].endswith("[...]")
    assert len(item["descricao"]) < LIMITE_DESCRICAO + 10
