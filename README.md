# Job Radar

Busca vagas de estágio/emprego em várias fontes, audita cada uma com IA de acordo com o seu perfil e envia as recomendadas pelo Telegram. O sistema **não se candidata automaticamente**: quem confirma é você.

- Plano completo (requisitos, regras de negócio, schema, decisões): [`docs/PLANO.md`](docs/PLANO.md)
- Deploy em Kubernetes (lab na GCP): [`docs/K8S-LAB.md`](docs/K8S-LAB.md)
- CI/CD (GitHub Actions, GHCR, fluxo de PR): [`docs/CI-CD.md`](docs/CI-CD.md)

**Status:** MVP (Fase 1) funcional: coleta (Gupy, Solides, GitHub), pré-filtro, fila, auditoria por IA (Codex, Groq, NVIDIA, Gemini) e notificações no Telegram. Web UI (Fase 2) em Next.js: Visão geral, Vagas (com o parecer da IA e as decisões), Meu perfil (com vínculo do Telegram), Providers de IA, Fontes e coleta, Usuários (cadastro por convite).

## Rodando com Docker Compose

```bash
cp .env.example .env        # ajuste senhas e ADMIN_EMAIL
docker compose up -d --build
docker compose run --rm api seed   # fontes + usuário admin (idempotente)

curl localhost:8000/healthz   # {"status":"ok"}
curl localhost:8000/readyz    # {"status":"ok","banco":"ok"}
```

Serviços: `postgres`, `migrar` (aplica as migrations e sai), `api` e `worker` (sempre 1 réplica).

## Comandos

Uma única imagem, com comandos diferentes:

| Comando | O que faz |
|---|---|
| `job-radar api` | Sobe a API (FastAPI) |
| `job-radar worker` | Sobe o scheduler (APScheduler) |
| `job-radar worker-saude` | Sai com 0 se o heartbeat do worker for recente (healthcheck/probe) |
| `job-radar migrar [revisao]` | Aplica as migrations e sai |
| `job-radar seed` | Cria fontes e o usuário admin |
| `job-radar coletar <fonte>` | Executa uma coleta e sai (CronJob no Kubernetes) |
| `job-radar alimentar` | Move as melhores vagas do pool para a fila |
| `job-radar expirar` | Expira vagas além do TTL |
| `job-radar auditar` | Uma rodada de auditoria por IA |
| `job-radar provider ...` | Cadastra, lista, testa e remove providers de IA |
| `job-radar perfil ...` | Mostra o perfil e define o currículo |
| `job-radar chave-fernet` | Gera uma `FERNET_KEY` |
| `job-radar telegram vincular` | Gera o link que vincula o seu chat do Telegram |
| `job-radar notificar` / `resumo` | Envia as recomendações pendentes / o resumo do dia agora |

Toda a configuração vem de variáveis de ambiente (ver `.env.example`).

## LinkedIn via JobSpy (experimental)

O coletor `jobspy` usa somente a busca pública do LinkedIn, sem conta pessoal. O `seed` cadastra a fonte **desativada**, com intervalo de 240 minutos, limite total de 20 vagas e esta configuração:

```json
{
  "buscas": [{"termo": "estágio tecnologia", "local": "Brasília, Distrito Federal, Brazil"}],
  "horas": 72,
  "pausa_s": 5
}
```

O administrador pode alterar esses parâmetros em **Fontes e coleta → LinkedIn → Editar buscas**: até cinco buscas, termos e locais obrigatórios, janela de 1 a 720 horas e pausa entre buscas de 0 a 60 segundos. O limite total deve ficar entre 1 e 50 e vale para a execução inteira, com deduplicação entre buscas. As buscas seguem a ordem informada; ao atingir o limite, as demais não são consultadas naquela execução. Os campos são validados no servidor; não é possível salvar durante uma coleta em andamento. Salvar preserva a ativação e os horários da fonte, e a configuração passa a valer nas próximas execuções.

Após executar `job-radar seed`, a fonte aparece em **Fontes e coleta**. Ative-a para permitir **Coletar agora** ou `job-radar coletar jobspy`. No ambiente local, reinicie o worker após habilitar a fonte para registrar seu agendamento. No lab Kubernetes, o CronJob `coletar-linkedin`, mantido no `k8s-lab`, agenda as execuções às 08h, 12h, 16h e 20h de Brasília. A edição das buscas não altera esse CronJob.

Os filtros remoto e tipo de contrato não são enviados, pois a busca pública do LinkedIn não os suporta; o pré-filtro por usuário continua selecionando as vagas. Ausência de indicação de remoto não é tratada como confirmação de trabalho presencial. Erros reportados pelo JobSpy, inclusive bloqueios/429, deixam a execução com erro, sem repetição imediata pelo adaptador. Resultados parciais com erro são descartados para não registrar sucesso incompleto. Descrições são solicitadas, mas podem faltar quando a página de uma vaga falha.

Para direcionar a coleta, use buscas separadas com termos como `estágio suporte remoto`, `Python remote` ou `internship`, e localização `Brazil` para ampliar a cobertura de vagas remotas. Esses termos são pistas de busca, não filtros garantidos. Regras do perfil e instruções da IA podem refinar as recomendações; dados ausentes exigem confirmação. O tipo `fulltime` do JobSpy descreve jornada, não comprova contratação CLT; CLT/PJ precisam de evidência no anúncio.

## Configurando a auditoria por IA

```bash
# 1. chave que cifra as API keys no banco (coloque no .env como FERNET_KEY)
docker compose run --rm api chave-fernet

# 2. providers, em ordem de prioridade. --api-key-env lê a variável do ambiente ou do .env
#    (a chave não fica no histórico do shell); sem ele, a chave é pedida no terminal
job-radar provider adicionar groq --preset groq --api-key-env GROQ_API_KEY
job-radar provider adicionar nvidia --preset nvidia --api-key-env NVIDIA_API_KEY
job-radar provider adicionar gemini --preset gemini --api-key-env GEMINI_API_KEY
job-radar provider adicionar codex --preset codex     # CLI local, só para o admin

job-radar provider listar
job-radar provider testar groq

# 3. currículo usado para comparar requisitos
job-radar perfil curriculo curriculo.md
```

Os presets trazem modelo e limites iniciais. Modelos são aposentados com frequência: se o `testar` falhar com 404/410, liste os disponíveis com `job-radar provider modelos <nome>` e troque com `job-radar provider editar <nome> --modelo ...`. O worker audita um lote por usuário a cada minuto; `job-radar auditar` roda uma rodada na hora.

> O preset `codex` usa o Codex CLI autenticado na máquina, em modo somente leitura, sem salvar sessão e numa pasta temporária vazia. Não funciona dentro do container: use-o rodando `job-radar worker` no host.

## Notificações pelo Telegram

```bash
# 1. crie um bot no @BotFather e coloque o token no .env como TELEGRAM_BOT_TOKEN
# 2. gere o link de vínculo (uso único) e abra no Telegram
job-radar telegram vincular
# 3. com o worker rodando, toque em "Iniciar" no chat do bot
job-radar worker
job-radar telegram status
```

Cada vaga recomendada chega com os botões **✅ Vou aplicar**, **❌ Ignorar** (com motivo opcional) e **🔗 Abrir vaga**. O worker também avisa quando as recomendadas passam de 80% do limite e envia um resumo às 20:30. O bot responde a `/status`.

O bot usa long polling: não precisa de URL pública nem de porta aberta. Só um processo pode fazer polling por bot, o que casa com o worker de réplica única. Use um bot só para o Job Radar, não o de outro projeto.

## Desenvolvimento

Requer [uv](https://docs.astral.sh/uv/) e Docker.

```bash
uv sync
uv run ruff check && uv run ruff format --check

# testes de integração precisam de um Postgres:
docker compose up -d postgres
TEST_DATABASE_URL=postgresql+psycopg://jobradar:<senha>@localhost:5432/jobradar uv run pytest
```

> Os testes de integração fazem `downgrade base` no banco apontado por `TEST_DATABASE_URL`, ou seja, apagam tudo. Use um banco descartável.

Nova migration (depois de alterar os models):

```bash
DATABASE_URL=postgresql+psycopg://... uv run alembic revision --autogenerate -m "descricao"
```

### Frontend

Next.js em `frontend/`, exportado como arquivos estáticos que a própria API serve (Node só no build; na imagem, o estágio `frontend` do Dockerfile). Requer Node 24 e pnpm.

```bash
cd frontend && pnpm install
pnpm dev                      # http://localhost:3000, com recarga automática
pnpm typecheck && pnpm build  # gera frontend/out
FRONTEND_DIR=$PWD/out uv run job-radar api   # a API serve o build em http://localhost:8000
```

Com `pnpm dev`, as chamadas a `/api` são repassadas para a API em `127.0.0.1:8000`. Servindo o build pela API, reinicie a API depois de cada `pnpm build`: a CSP lista o hash dos scripts inline, calculado na inicialização.

O frontend segue o visual Quayside do protótipo do Google Stitch, adaptado aos dados reais:

- Visão geral e triagem: contagens atuais, funil, recomendações, decisões e saúde das últimas coletas.
- Perfil: quantidade de palavras, níveis e critérios editados; simulação e vínculo do Telegram existentes.
- Providers: prioridade, requisições, tokens e erros; fontes: coletas e histórico; usuários: acesso e convites.

Os totais de fontes se referem às últimas 30 execuções; os de convites, aos últimos 50 registros. O protótipo também sugere séries históricas, custos em dinheiro, latência média, previsões de próxima coleta, ações em lote e configurações globais: esses recursos não foram incluídos porque não têm suporte nos endpoints atuais. Os gráficos e números ilustrativos do Stitch não são usados como dados da aplicação.

## CI

`.github/workflows/ci.yml`: lint e testes (com Postgres) em todo push e PR. Em push na `main`, publica `ghcr.io/paulocerqr/job-radar` com as tags `<sha>` e `latest`.
