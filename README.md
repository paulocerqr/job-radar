# Job Radar

Busca vagas de estágio/emprego em várias fontes, audita cada uma com IA de acordo com o seu perfil e envia as recomendadas pelo Telegram. O sistema **não se candidata automaticamente**: quem confirma é você.

- Plano completo (requisitos, regras de negócio, schema, decisões): [`docs/PLANO.md`](docs/PLANO.md)
- Deploy em Kubernetes (lab na GCP): [`docs/K8S-LAB.md`](docs/K8S-LAB.md)

**Status:** Fase 1 em andamento. Coleta (Gupy, GitHub), pré-filtro e fila funcionando; auditoria por IA e notificações a seguir.

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

Toda a configuração vem de variáveis de ambiente (ver `.env.example`).

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

## CI

`.github/workflows/ci.yml`: lint e testes (com Postgres) em todo push e PR. Em push na `main`, publica `ghcr.io/paulocerqr/job-radar` com as tags `<sha>` e `latest`.
