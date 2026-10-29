# Desenvolvimento

[Voltar ao README](../README.md)

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
cd ..
FRONTEND_DIR="$PWD/frontend/out" uv run job-radar api   # http://localhost:8000
```

Com `pnpm dev`, as chamadas a `/api` são repassadas para a API em `127.0.0.1:8000`. Servindo o build pela API, reinicie a API depois de cada `pnpm build`: a CSP lista o hash dos scripts inline, calculado na inicialização.

O frontend segue o visual Quayside do protótipo do Google Stitch, adaptado aos dados reais:

- Visão geral e triagem: contagens atuais, funil, recomendações, decisões e saúde das últimas coletas.
- Perfil: quantidade de palavras, níveis e critérios editados; simulação e vínculo do Telegram existentes.
- Providers: prioridade, requisições, tokens e erros; fontes: coletas e histórico; usuários: acesso e convites.

Os totais de fontes se referem às últimas 30 execuções; os de convites, aos últimos 50 registros. O protótipo também sugere séries históricas, custos em dinheiro, latência média, previsões de próxima coleta, ações em lote e configurações globais: esses recursos não foram incluídos porque não têm suporte nos endpoints atuais. Os gráficos e números ilustrativos do Stitch não são usados como dados da aplicação.

## Integração contínua

`.github/workflows/ci.yml`: lint e testes (com Postgres) em todo push e PR. Em push na `main`, publica `ghcr.io/paulocerqr/job-radar` com as tags `<sha>` e `latest`.

Detalhes de publicação e fluxo de PR em [CI/CD](CI-CD.md).
