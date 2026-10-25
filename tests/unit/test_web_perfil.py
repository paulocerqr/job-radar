from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.datastructures import FormData

from job_radar.auditoria.prompt import VERSAO_PROMPT, montar_prompt
from job_radar.config import Settings
from job_radar.models import Perfil
from job_radar.web.app import create_app
from job_radar.web.formulario_perfil import ler_formulario, lista_de_termos
from job_radar.web.sessao import BLOQUEIO_S, MAX_FALHAS, LimiteLogin, chave_sessao


def formulario(**valores) -> FormData:
    padrao = {
        "palavras_chave": "devops\nsuporte",
        "palavras_excluidas": "senior",
        "niveis": ["estagio"],
        "localidades": "Brasília/DF",
        "aceita_remoto": "on",
        "score_minimo": "60",
        "ttl_pool_dias": "7",
        "ttl_recomendada_dias": "14",
        "curriculo_md": "# CV",
        "instrucoes_ia": "",
    }
    padrao.update(valores)
    itens = []
    for chave, valor in padrao.items():
        for v in valor if isinstance(valor, list) else [valor]:
            itens.append((chave, v))
    return FormData(itens)


def test_lista_de_termos_aceita_linhas_e_virgulas_sem_repetir():
    assert lista_de_termos("devops, Cloud\n\n  machine   learning \ncloud;sre") == [
        "devops", "Cloud", "machine learning", "sre",
    ]  # fmt: skip


def test_formulario_valido():
    dados = ler_formulario(formulario(localidades="Brasília/DF\nGO"))
    assert not dados.erros
    assert dados.palavras_chave == ["devops", "suporte"]
    assert dados.localidades == [{"cidade": "Brasília", "uf": "DF"}, {"uf": "GO"}]
    assert dados.aceita_remoto is True
    assert dados.niveis == ["estagio"]


def test_formulario_com_erros():
    dados = ler_formulario(
        formulario(
            palavras_chave=" \n ",
            localidades="Brasília/XX",
            score_minimo="150",
            niveis=["desconhecido"],
            aceita_remoto="",
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


def test_sem_sessao_redireciona_para_login():
    resposta = TestClient(create_app()).get("/perfil", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_htmx_sem_sessao_recebe_hx_redirect():
    cliente = TestClient(create_app())
    cliente.get("/login")  # cria o token CSRF na sessão
    resposta = cliente.get("/perfil", headers={"HX-Request": "true"}, follow_redirects=False)
    assert resposta.status_code == 401
    assert resposta.headers["hx-redirect"] == "/login"


def test_login_sem_csrf_recusado_e_pagina_com_csp():
    cliente = TestClient(create_app())
    pagina = cliente.get("/login")
    assert "script-src 'self'" in pagina.headers["content-security-policy"]
    assert 'name="csrf"' in pagina.text
    resposta = cliente.post("/login", data={"email": "a@b.c", "senha": "x"})
    assert resposta.status_code == 403


def test_prompt_leva_as_instrucoes_do_candidato():
    perfil = Perfil(
        curriculo_md="cv", niveis=["estagio"], palavras_chave=["devops"], aceita_remoto=True,
        localidades=[], instrucoes_ia="aceito idas esporádicas",
    )  # fmt: skip
    sistema, usuario = montar_prompt(perfil, [])
    assert VERSAO_PROMPT == "v2"
    assert "regras_do_candidato" in sistema
    assert "aceito idas esporádicas" in usuario
