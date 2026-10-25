from fastapi.testclient import TestClient
from pydantic import SecretStr

from job_radar.auditoria.prompt import VERSAO_PROMPT, montar_prompt
from job_radar.config import Settings
from job_radar.models import Perfil
from job_radar.web.app import create_app
from job_radar.web.perfil_json import lista_de_termos, para_json, validar
from job_radar.web.sessao import BLOQUEIO_S, MAX_FALHAS, LimiteLogin, chave_sessao


def corpo(**valores) -> dict:
    padrao = {
        "palavras_chave": ["devops", "suporte"],
        "palavras_excluidas": ["senior"],
        "niveis": ["estagio"],
        "localidades": ["Brasília/DF"],
        "aceita_remoto": True,
        "score_minimo": 60,
        "ttl_pool_dias": 7,
        "ttl_recomendada_dias": 14,
        "curriculo_md": "# CV",
        "instrucoes_ia": "",
    }
    return {**padrao, **valores}


def test_lista_de_termos_sem_vazios_nem_repeticao():
    assert lista_de_termos(["devops", " Cloud ", "", "machine   learning", "cloud"]) == [
        "devops", "Cloud", "machine learning",
    ]  # fmt: skip
    assert lista_de_termos("não é lista") == []


def test_perfil_valido_e_ida_e_volta_das_localidades():
    dados = validar(corpo(localidades=["Brasília/DF", "GO"]))
    assert not dados.erros
    assert dados.localidades == [{"cidade": "Brasília", "uf": "DF"}, {"uf": "GO"}]
    assert para_json(dados)["localidades"] == ["Brasília/DF", "GO"]


def test_perfil_com_erros():
    dados = validar(
        corpo(
            palavras_chave=[" "],
            localidades=["Brasília/XX"],
            score_minimo=150,
            niveis=["desconhecido"],
            aceita_remoto="sim",  # só true de verdade conta
        )
    )
    assert set(dados.erros) == {"palavras_chave", "localidades", "score_minimo", "niveis"}
    assert dados.aceita_remoto is False


def test_limite_login_bloqueia_e_libera_depois():
    agora = [0.0]
    limite = LimiteLogin(relogio=lambda: agora[0])
    for _ in range(MAX_FALHAS):
        assert not limite.bloqueado("ip:1")
        limite.falhou("ip:1")
    assert limite.bloqueado("ip:1")
    assert not limite.bloqueado("ip:2")
    agora[0] += BLOQUEIO_S + 1
    assert not limite.bloqueado("ip:1")


def test_chave_de_sessao_derivada_da_fernet_e_diferente_dela():
    s = Settings(database_url="x", fernet_key=SecretStr("abc"))
    chave = chave_sessao(s)
    assert chave == chave_sessao(s)
    assert "abc" not in chave
    assert chave_sessao(Settings(database_url="x", sessao_secret=SecretStr("s"))) == "s"


def test_api_sem_sessao_responde_401():
    resposta = TestClient(create_app()).get("/api/perfil")
    assert resposta.status_code == 401
    assert resposta.headers["content-security-policy"].startswith("default-src 'none'")


def test_escrita_exige_json_e_token():
    cliente = TestClient(create_app())
    # formulário (o que outro site conseguiria mandar) é recusado antes de qualquer coisa
    assert cliente.post("/api/login", data={"email": "a@b.c", "senha": "x"}).status_code == 403
    assert cliente.post("/api/sair", json={}).status_code == 403  # JSON sem X-CSRF-Token


def test_prompt_leva_as_instrucoes_do_candidato():
    perfil = Perfil(
        curriculo_md="cv", niveis=["estagio"], palavras_chave=["devops"], aceita_remoto=True,
        localidades=[], instrucoes_ia="aceito idas esporádicas",
    )  # fmt: skip
    sistema, usuario = montar_prompt(perfil, [])
    assert VERSAO_PROMPT == "v2"
    assert "regras_do_candidato" in sistema
    assert "aceito idas esporádicas" in usuario
