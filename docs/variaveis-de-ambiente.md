# Variáveis de ambiente

Tabela baseada exclusivamente no [`.env.example`](../.env.example) e no [README](../README.md). Para variáveis futuras comentadas no `.env.example`, a marcação **Futura** aparece no grupo. “Obrigatória para subir com Docker Compose” considera a orientação disponível nessas fontes; quando não há informação explícita, consta “não informado”. Valores de exemplo não reproduzem senhas.

| Variável | Grupo | Obrigatória para subir com Docker Compose | Valor de exemplo | Como preencher |
|---|---|---|---|---|
| `POSTGRES_USER` | Postgres | não informado | `jobradar` | Copie `.env.example` para `.env` e ajuste conforme necessário; regra específica não informada. |
| `POSTGRES_PASSWORD` | Postgres | não informado | não informado (senha) | Defina uma senha; o README orienta ajustar as senhas. |
| `POSTGRES_DB` | Postgres | não informado | `jobradar` | Copie `.env.example` para `.env` e ajuste conforme necessário; regra específica não informada. |
| `POSTGRES_PORTA` | Postgres | não informado | `5432` | Porta publicada em `127.0.0.1` (dev/testes), conforme comentário no `.env.example`. |
| `DATABASE_URL` | Postgres | não informado | `postgresql+psycopg://jobradar:<senha>@postgres:5432/jobradar` | No Compose, o host é `postgres`; no host, use `localhost`. Ajuste usuário, senha e banco conforme a configuração. |
| `LOG_FORMAT` | Aplicação | não informado | `json` | Use `json` ou `text`, conforme comentário no `.env.example`. |
| `LOG_LEVEL` | Aplicação | não informado | `INFO` | não informado |
| `TZ` | Aplicação | não informado | `America/Sao_Paulo` | não informado |
| `COLETA_NO_WORKER` | Aplicação | não informado | `true` | Use `false` no Kubernetes, onde a coleta é via CronJob, conforme comentário no `.env.example`. |
| `ADMIN_EMAIL` | Seed | sim: o README orienta ajustar ao copiar `.env.example` | `voce@exemplo.com` | Informe o e-mail do usuário admin criado por `job-radar seed`. |
| `ADMIN_NOME` | Seed | não informado | `Admin` | não informado |
| `ADMIN_SENHA` | Seed | não informado | não informado (senha) | Defina uma senha; regra específica não informada. |
| `FERNET_KEY` | IA | não informado | não informado | Gere com `docker compose run --rm api chave-fernet` e coloque o resultado no `.env`. Se perder ou trocar, as chaves cadastradas precisam ser cadastradas de novo. |
| `TELEGRAM_BOT_TOKEN` | Telegram | não informado | não informado (vazio desliga notificações) | Crie um bot próprio do Job Radar com `@BotFather` e coloque o token no `.env`; vazio desliga as notificações. |
| `SECRET_KEY` | Próximas fases — futura | não informado | não informado | não informado |
| `N8N_WEBHOOK_URL` | Próximas fases — futura | não informado | não informado | não informado |
| `N8N_WEBHOOK_TOKEN` | Próximas fases — futura | não informado | não informado | não informado |
| `GITHUB_TOKEN` | Próximas fases — futura | não informado | não informado | não informado |
