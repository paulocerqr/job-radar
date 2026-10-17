# Job Radar — Plano de Execução

> Sistema de busca, auditoria por IA e recomendação de vagas de emprego/estágio.
> Status: **planejamento** (nada implementado). Data: 2026-10-17.

---

## 1. Visão geral

O Job Radar coleta vagas de múltiplas fontes, deduplica, aplica um pré-filtro por regras do perfil do usuário e envia as candidatas para **auditoria por IA**. Vagas aprovadas viram **recomendadas** e são notificadas (Telegram/e-mail via n8n). O usuário decide o que **confirmar**. O sistema **nunca se candidata automaticamente**.

Perfil inicial (usuário administrador):
- Estágio em **DevOps / Infraestrutura / Cloud** ou **Desenvolvimento Fullstack / Backend**.
- Modalidades: **remoto** (Brasil inteiro), **presencial** e **híbrido** (somente **Brasília-DF**).

---

## 2. Requisitos

### 2.1 Funcionais

| ID | Requisito |
|---|---|
| RF01 | Coletar vagas de múltiplas fontes via plugins (um coletor por fonte). |
| RF02 | Normalizar vagas para um modelo único. |
| RF03 | Deduplicar vagas globalmente (mesma vaga em fontes diferentes = uma vaga). |
| RF04 | Aplicar pré-filtro por regras do perfil de cada usuário (palavras-chave, exclusões, nível, localização). |
| RF05 | Manter, por usuário, um pool de candidatas, uma fila de auditoria (limite 30) e uma lista de recomendadas (limite 50). |
| RF06 | Auditar vagas com IA (CLI Claude/Codex ou API OpenAI-compatível), retornando JSON estruturado com score, gaps e justificativa. |
| RF07 | Notificar novas recomendadas via webhook do n8n (Telegram/e-mail). |
| RF08 | Permitir ao usuário confirmar ou ignorar recomendadas (Telegram inline buttons e Web UI), registrando motivo. |
| RF09 | Expirar automaticamente vagas por TTL e vagas que saíram do ar. |
| RF10 | Cada usuário cadastra seus próprios providers de IA (BYOK) com ordem de fallback. |
| RF11 | Vincular conta Telegram do usuário via `/start <token>`. |
| RF12 | Enviar resumo diário e alerta de capacidade (recomendadas ≥ 80%). |
| RF13 | Web UI: login, perfil, providers, listagem/triagem de vagas, histórico, saúde dos coletores. |

### 2.2 Não funcionais

| ID | Requisito |
|---|---|
| RNF01 | Rodar em servidor local com pouca RAM livre (sem LLM local). Alvo: < 512 MB para o core. |
| RNF02 | Deploy via docker-compose. |
| RNF03 | Respeitar rate limit por fonte (scraping educado) e por chave de IA. |
| RNF04 | Chaves de API criptografadas em repouso; nunca logadas; mascaradas na UI. |
| RNF05 | Falha de um coletor ou provider não derruba o sistema (isolamento por job). |
| RNF06 | Observabilidade: log estruturado, registro de cada execução de coleta e auditoria. |
| RNF07 | Idempotência: re-coletar a mesma vaga não gera duplicata nem re-auditoria. |
| RNF08 | Modelo de dados multiusuário desde o início, mesmo com MVP de usuário único. |
| RNF09 | Deploy agnóstico (12-factor): toda configuração por variáveis de ambiente, logs em stdout (JSON), sem estado em disco local nos processos `api`/`worker`. A mesma imagem roda em docker-compose e Kubernetes. |
| RNF10 | Endpoints de saúde: `/healthz` (liveness, processo vivo) e `/readyz` (readiness, banco acessível). O `worker` expõe um health equivalente (arquivo de heartbeat ou porta HTTP mínima). |
| RNF11 | Migrations executadas por comando dedicado (`job-radar migrar`), nunca no startup da API (permite rodar como Job/initContainer). |
| RNF12 | Shutdown gracioso em `SIGTERM` (terminar lote de auditoria em andamento ou devolvê-lo à fila). |

---

## 3. Arquitetura

```
                          ┌───────────────────── CORE (Python) ─────────────────────┐
                          │                                                         │
 ┌──────────────┐         │  ┌───────────┐   ┌──────────┐   ┌─────────┐             │
 │ Fontes       │ ──────► │  │ Coletores │─► │Normaliza │─► │ Dedupe  │──► VAGA      │
 │ Gupy, GitHub │         │  │ (plugins) │   └──────────┘   └─────────┘   (global)   │
 │ Greenhouse...│         │  └───────────┘                                   │       │
 └──────────────┘         │                                                  ▼       │
                          │                              Pré-filtro por usuário      │
                          │                                         │                │
                          │                                         ▼                │
                          │   VAGA_USUARIO:  pool ─► fila(30) ─► recomendada(50)     │
                          │                   │       ▲   │            │    │        │
                          │       alimentador ┘───────┘   │            │    ▼        │
                          │                    Auditor IA ┘            │ confirmada  │
                          │                    (round-robin)           │             │
                          │                         │                  ▼             │
                          │                         ▼             descartada/        │
                          │                 Providers (BYOK)      ignorada/expirada  │
                          │                 CLI | OpenAI-compat                      │
                          │                                                          │
                          │   FastAPI (Web UI + API + webhook Telegram)              │
                          └─────────────┬───────────────────────────▲────────────────┘
                                        │ webhook (nova recomendada) │ callback (botões)
                                        ▼                            │
                                   ┌────────┐   Telegram / e-mail    │
                                   │  n8n   │ ───────────────────────┘
                                   └────────┘
```

### 3.1 Componentes

| Componente | Responsabilidade |
|---|---|
| **Coletores** | Um plugin por fonte. Interface comum `buscar(termos, desde) -> list[VagaBruta]`. Rate limit próprio. |
| **Normalizador** | Converte `VagaBruta` em `Vaga` (título, empresa, local, modalidade, nível, descrição limpa, URL canônica). |
| **Dedupe** | Calcula `hash_dedupe` e faz upsert em `vaga`. |
| **Pré-filtro** | Para cada usuário ativo, avalia a vaga contra o perfil e cria `vaga_usuario` em `pool` com `score_prefiltro`. |
| **Alimentador** | Move as melhores do `pool` para `fila` até o limite do usuário. |
| **Auditor** | Consome a `fila` (round-robin entre usuários), chama o provider, valida JSON, transiciona estado. |
| **Expirador** | Aplica TTLs e verifica se vagas recomendadas ainda estão no ar. |
| **Notificador** | Envia eventos ao webhook do n8n. |
| **API/Web** | FastAPI + templates (HTMX) para UI; endpoints de callback do Telegram. |

### 3.2 Stack

| Camada | Escolha | Motivo |
|---|---|---|
| Linguagem | **Python 3.12+** | Ecossistema de scraping e IA; padrão do autor. |
| Web/API | **FastAPI** + **Jinja2 + HTMX** | UI simples sem build de frontend; pouca RAM. |
| Banco | **PostgreSQL 16** | `SKIP LOCKED` para fila, JSONB, `pg_trgm` para similaridade. |
| ORM/Migrations | **SQLAlchemy 2.0** + **Alembic** | Padrão maduro. |
| Validação | **Pydantic v2** | Schemas de vaga e da saída da IA. |
| Agendamento | **APScheduler** (processo `worker`) | Sem Redis/Celery; volume baixo. |
| HTTP/Scraping | **httpx**, **selectolax**, **python-jobspy**; **Playwright** só se inevitável | Leve; Playwright é pesado em RAM. |
| IA | Adaptadores `cli` (Claude Code, Codex) e `openai_compatible` (Groq, NVIDIA NIM, Gemini, OpenRouter) | Dois adaptadores cobrem todos os providers. |
| Cripto | **cryptography (Fernet)** | Chaves de API em repouso. |
| Notificação | **n8n** via webhook | Canais configuráveis sem tocar no código. |
| Bot | Telegram Bot API (webhook no FastAPI ou via n8n) | Botões inline para triagem. |
| CLI | **Typer** | Comandos operacionais (`migrar`, `coletar`, `auditar`...). |
| Imagem | **Dockerfile** multi-stage, usuário não-root | Uma imagem para `api`, `worker` e comandos. |
| CI | **GitHub Actions** → **GHCR** | Lint, testes, build e push com tag `sha` + `semver`. |
| Deploy local | **docker-compose** (`api`, `worker`, `postgres`) | n8n já existente no servidor. |
| Deploy cloud | **Kubernetes (kubeadm na GCP)** — manifests no repo `k8s-lab` | Ver `docs/K8S-LAB.md`. |
| Qualidade | **ruff**, **pytest**, **mypy** (opcional) | |

Processos (mesma imagem, comandos diferentes):
- `job-radar api`: FastAPI (UI, API REST, callbacks).
- `job-radar worker`: APScheduler com jobs de alimentação, auditoria, expiração, resumo e (opcionalmente) coleta.
- `job-radar migrar`: aplica migrations Alembic e sai.
- `job-radar coletar <fonte>`: executa uma coleta e sai (usado por CronJob no Kubernetes).
- `job-radar seed`: cria admin, perfil e fontes iniciais.

### 3.3 Modos de execução

| Ambiente | Coleta | Provider de IA | Banco | n8n |
|---|---|---|---|---|
| **Servidor local** | Job do APScheduler no `worker` | CLI (Claude/Codex) + APIs | Postgres no compose | Instância existente |
| **Kubernetes (GCP)** | `CronJob` por fonte (`COLETA_NO_WORKER=false`) | Somente APIs (Groq/NVIDIA/Gemini) | StatefulSet + PVC | Deployment no cluster |

A variável `COLETA_NO_WORKER` (padrão `true`) define se o `worker` agenda as coletas ou se elas vêm de fora (CronJob/cron).

---

## 4. Ciclo de vida da vaga

### 4.1 Estados (`vaga_usuario.status`)

| Estado | Significado | Entra por | Sai para |
|---|---|---|---|
| `pool` | Passou no pré-filtro, aguardando vaga na fila | Pré-filtro | `fila`, `expirada` |
| `fila` | Aguardando auditoria (limite 30/usuário) | Alimentador | `recomendada`, `descartada`, `erro`, `pool` (retry esgotado de provider) |
| `recomendada` | Aprovada pela IA (limite 50/usuário) | Auditor | `confirmada`, `ignorada`, `expirada` |
| `confirmada` | Usuário aprovou (sem limite) | Usuário | — (futuro: `aplicada`, `entrevista`...) |
| `descartada` | Reprovada pela IA (motivo salvo) | Auditor | — (terminal) |
| `ignorada` | Usuário rejeitou (motivo salvo) | Usuário | — (terminal) |
| `expirada` | TTL vencido ou vaga fora do ar | Expirador | — (terminal) |
| `erro` | Saída inválida após retries | Auditor | `fila` (reprocessamento manual) |

```
pool ──► fila ──► recomendada ──► confirmada
 │        │            │
 │        ├──► descartada
 │        └──► erro ──(manual)──► fila
 │                     ├──► ignorada
 └──► expirada ◄───────┘
```

Toda transição gera registro em `historico_status`.

### 4.2 Regras de negócio

**Coleta**
- RN01: Coleta roda das **08:00 às 20:00** (America/Sao_Paulo), com intervalo **por fonte** (ex.: Gupy 1h, GitHub 2h, LinkedIn 4h).
- RN02: Cada execução coleta no máximo `fonte.max_itens_execucao` itens (ex.: 10–50).
- RN03: Termos de busca = união das palavras-chave de todos os usuários ativos.
- RN04: Coleta é **independente** da capacidade da fila; o gargalo é a auditoria.

**Deduplicação**
- RN05: `hash_dedupe = sha256(normalizar(empresa) + "|" + normalizar(titulo) + "|" + normalizar(cidade|"remoto"))`. Normalizar = minúsculas, sem acento, sem pontuação, sem sufixos ("ltda", "s.a.").
- RN06: Mesma vaga vista em outra fonte → adiciona registro em `vaga_fonte`, não cria nova `vaga`.
- RN07: Se já existe `vaga_usuario` para (vaga, usuário) em **qualquer** estado, não recria (evita re-auditoria de descartadas/ignoradas).

**Pré-filtro** (por usuário, sem IA)
- RN08: Deve conter ao menos um termo de `perfil.palavras_chave` no título ou descrição.
- RN09: Não pode conter termos de `perfil.palavras_excluidas` no título (ex.: "sênior", "pleno", "especialista", "lead").
- RN10: Nível deve estar em `perfil.niveis` (ex.: `estagio`) — inferido por termos ("estágio", "estagiário", "intern", "trainee" opcional).
- RN11: Localização:
  - `remoto` → aceita se `perfil.aceita_remoto`.
  - `presencial`/`hibrido` → aceita só se cidade/UF ∈ `perfil.localidades` (para o admin: Brasília-DF, incluindo RAs como Taguatinga, Águas Claras, Asa Norte etc., normalizadas para `Brasília/DF`).
  - Localização desconhecida → aceita com penalidade no score (a IA decide).
- RN12: `score_prefiltro` (0–100) = peso de termos encontrados + recência + confiabilidade da fonte.
- RN13: Vagas no `pool` expiram após **7 dias** sem entrar na fila.

**Alimentador**
- RN14: Executa a cada **10 min**. Para cada usuário: `vagas_livres = limite_fila - count(fila)`; move as `vagas_livres` melhores do `pool` ordenadas por `score_prefiltro DESC, publicada_em DESC`.
- RN15: Não alimenta se `count(recomendada) >= limite_recomendadas` (backpressure).

**Auditoria**
- RN16: Worker com **concorrência 1** por provider; round-robin entre usuários.
- RN17: Lote de **até 5 vagas por chamada** (configurável por provider).
- RN18: Saída validada por schema Pydantic (`ResultadoAuditoria`). Inválida → 1 retry; persistindo → estado `erro`.
- RN19: `score >= perfil.score_minimo` (padrão 70) e `nivel_compativel = true` → `recomendada`; senão → `descartada` com motivo.
- RN20: Provider com rate limit/erro → tenta o próximo da lista do usuário (por `prioridade`). Todos falharam → vaga permanece em `fila` com `proxima_tentativa_em` (backoff exponencial: 5, 15, 60 min). Após 5 tentativas → volta ao `pool`.
- RN21: Auditoria só ocorre se `count(recomendada) < limite_recomendadas`.
- RN22: Provider `cli` só pode ser cadastrado por usuário `admin`.

**Recomendadas**
- RN23: TTL de **14 dias**; após isso → `expirada`.
- RN24: Expirador verifica diariamente se a URL da vaga ainda responde/está aberta (quando a fonte permitir) → senão `expirada`.
- RN25: Ao atingir **80%** do limite → alerta ao usuário.

**Usuário**
- RN26: Confirmar/ignorar disponível via Telegram (botões inline) e Web. Ignorar pede motivo opcional (botões rápidos: "nível", "stack", "local", "empresa", "outro").
- RN27: O sistema **nunca** se candidata automaticamente.

**Notificação**
- RN28: Cada nova `recomendada` → POST no webhook n8n (evento `vaga.recomendada`).
- RN29: Resumo diário às **20:30** (evento `resumo.diario`): novas recomendadas, pendentes, capacidade.

---

## 5. Auditoria por IA

### 5.1 Entrada
- Perfil do usuário (`perfil.curriculo_md` + preferências).
- Lote de vagas (título, empresa, local, modalidade, descrição truncada em ~6k caracteres).

### 5.2 Saída (por vaga)

```json
{
  "vaga_id": "uuid",
  "score": 0,
  "area": "devops | cloud | infra | backend | fullstack | outro",
  "nivel_compativel": true,
  "modalidade_compativel": true,
  "requisitos_atendidos": ["..."],
  "gaps": ["..."],
  "red_flags": ["..."],
  "resumo": "1-3 frases",
  "motivo_descarte": null
}
```

### 5.3 Providers

| Tipo | Exemplos | Config |
|---|---|---|
| `cli` | `claude -p`, `codex exec` | comando, modelo, timeout (admin apenas) |
| `openai_compatible` | Groq, NVIDIA NIM (Nemotron), Gemini, OpenRouter, OpenAI | `base_url`, `api_key`, `modelo` |

- Limites por provider: `rpm`, `rpd`, `tpm` (opcionais) → limitador token-bucket em memória + contadores persistidos em `uso_provider`.
- Aviso na UI: free tiers podem usar dados enviados para treino.

---

## 6. Schema do banco (PostgreSQL)

Convenções: PK `uuid` (`gen_random_uuid()`), `criado_em/atualizado_em timestamptz`, enums como `text` + `CHECK` (facilita migração).

### 6.1 Usuários e configuração

```sql
CREATE TABLE usuario (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text NOT NULL UNIQUE,
  senha_hash       text NOT NULL,
  nome             text NOT NULL,
  papel            text NOT NULL DEFAULT 'usuario' CHECK (papel IN ('admin','usuario')),
  ativo            boolean NOT NULL DEFAULT true,
  limite_fila          int NOT NULL DEFAULT 30,
  limite_recomendadas  int NOT NULL DEFAULT 50,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE perfil (
  usuario_id           uuid PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
  curriculo_md         text NOT NULL DEFAULT '',
  palavras_chave       text[] NOT NULL DEFAULT '{}',   -- {devops,cloud,aws,backend,python,...}
  palavras_excluidas   text[] NOT NULL DEFAULT '{}',   -- {senior,pleno,lead,...}
  niveis               text[] NOT NULL DEFAULT '{estagio}',
  aceita_remoto        boolean NOT NULL DEFAULT true,
  localidades          jsonb NOT NULL DEFAULT '[]',     -- [{"cidade":"Brasília","uf":"DF"}]
  score_minimo         int NOT NULL DEFAULT 70 CHECK (score_minimo BETWEEN 0 AND 100),
  ttl_pool_dias        int NOT NULL DEFAULT 7,
  ttl_recomendada_dias int NOT NULL DEFAULT 14,
  atualizado_em        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE provider_ia (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id       uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  nome             text NOT NULL,                       -- "Groq Llama 70B"
  tipo             text NOT NULL CHECK (tipo IN ('cli','openai_compatible')),
  base_url         text,                                -- null p/ cli
  modelo           text NOT NULL,
  comando          text,                                -- só p/ cli
  api_key_cifrada  bytea,                               -- Fernet
  api_key_sufixo   text,                                -- últimos 4 chars p/ exibição
  prioridade       int NOT NULL DEFAULT 1,              -- menor = primeiro
  tamanho_lote     int NOT NULL DEFAULT 5,
  rpm              int, rpd int, tpm int,
  timeout_s        int NOT NULL DEFAULT 120,
  ativo            boolean NOT NULL DEFAULT true,
  ultimo_erro      text,
  ultimo_erro_em   timestamptz,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (usuario_id, prioridade)
);

CREATE TABLE uso_provider (
  provider_id      uuid NOT NULL REFERENCES provider_ia(id) ON DELETE CASCADE,
  dia              date NOT NULL,
  requisicoes      int NOT NULL DEFAULT 0,
  tokens_entrada   int NOT NULL DEFAULT 0,
  tokens_saida     int NOT NULL DEFAULT 0,
  erros            int NOT NULL DEFAULT 0,
  PRIMARY KEY (provider_id, dia)
);

CREATE TABLE canal_notificacao (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id       uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  tipo             text NOT NULL CHECK (tipo IN ('telegram','email')),
  destino          text,                                -- chat_id ou e-mail
  token_vinculo    text UNIQUE,                         -- p/ /start <token>
  verificado       boolean NOT NULL DEFAULT false,
  ativo            boolean NOT NULL DEFAULT true,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (usuario_id, tipo)
);
```

### 6.2 Fontes e coleta

```sql
CREATE TABLE fonte (
  id                   text PRIMARY KEY,                -- 'gupy','github_backendbr','greenhouse',...
  nome                 text NOT NULL,
  ativa                boolean NOT NULL DEFAULT true,
  intervalo_min        int NOT NULL DEFAULT 60,
  max_itens_execucao   int NOT NULL DEFAULT 20,
  confiabilidade       int NOT NULL DEFAULT 50,         -- 0-100, entra no score_prefiltro
  config               jsonb NOT NULL DEFAULT '{}',     -- ex.: lista de empresas greenhouse
  ultima_execucao_em   timestamptz
);

CREATE TABLE execucao_coleta (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fonte_id         text NOT NULL REFERENCES fonte(id),
  iniciada_em      timestamptz NOT NULL DEFAULT now(),
  finalizada_em    timestamptz,
  status           text NOT NULL CHECK (status IN ('rodando','ok','erro','parcial')),
  itens_coletados  int NOT NULL DEFAULT 0,
  itens_novos      int NOT NULL DEFAULT 0,
  itens_duplicados int NOT NULL DEFAULT 0,
  erro             text
);
CREATE INDEX ON execucao_coleta (fonte_id, iniciada_em DESC);
```

### 6.3 Vagas

```sql
CREATE TABLE vaga (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  hash_dedupe      text NOT NULL UNIQUE,
  titulo           text NOT NULL,
  empresa          text,
  descricao        text,
  cidade           text,
  uf               char(2),
  modalidade       text CHECK (modalidade IN ('remoto','presencial','hibrido','desconhecida')),
  nivel            text CHECK (nivel IN ('estagio','trainee','junior','pleno','senior','desconhecido')),
  url_canonica     text NOT NULL,
  publicada_em     timestamptz,
  ativa            boolean NOT NULL DEFAULT true,
  verificada_em    timestamptz,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON vaga (publicada_em DESC);
CREATE INDEX vaga_titulo_trgm ON vaga USING gin (titulo gin_trgm_ops);

CREATE TABLE vaga_fonte (
  vaga_id          uuid NOT NULL REFERENCES vaga(id) ON DELETE CASCADE,
  fonte_id         text NOT NULL REFERENCES fonte(id),
  id_externo       text NOT NULL,
  url              text NOT NULL,
  dados_brutos     jsonb,
  visto_em         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (fonte_id, id_externo)
);
CREATE INDEX ON vaga_fonte (vaga_id);
```

### 6.4 Vaga por usuário (fila) e auditoria

```sql
CREATE TABLE vaga_usuario (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vaga_id              uuid NOT NULL REFERENCES vaga(id) ON DELETE CASCADE,
  usuario_id           uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  status               text NOT NULL CHECK (status IN
                         ('pool','fila','recomendada','confirmada',
                          'descartada','ignorada','expirada','erro')),
  score_prefiltro      int NOT NULL DEFAULT 0,
  score_ia             int,
  tentativas           int NOT NULL DEFAULT 0,
  proxima_tentativa_em timestamptz,
  motivo_usuario       text,                            -- ao ignorar
  expira_em            timestamptz,
  status_em            timestamptz NOT NULL DEFAULT now(),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (vaga_id, usuario_id)
);
-- consultas quentes
CREATE INDEX vu_status ON vaga_usuario (usuario_id, status);
CREATE INDEX vu_pool   ON vaga_usuario (usuario_id, score_prefiltro DESC) WHERE status = 'pool';
CREATE INDEX vu_fila   ON vaga_usuario (usuario_id, proxima_tentativa_em NULLS FIRST) WHERE status = 'fila';
CREATE INDEX vu_expira ON vaga_usuario (expira_em) WHERE status IN ('pool','recomendada');

CREATE TABLE auditoria (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vaga_usuario_id  uuid NOT NULL REFERENCES vaga_usuario(id) ON DELETE CASCADE,
  provider_id      uuid REFERENCES provider_ia(id) ON DELETE SET NULL,
  modelo           text NOT NULL,
  versao_prompt    text NOT NULL,
  sucesso          boolean NOT NULL,
  resultado        jsonb,                               -- ResultadoAuditoria
  erro             text,
  duracao_ms       int,
  tokens_entrada   int,
  tokens_saida     int,
  criado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON auditoria (vaga_usuario_id, criado_em DESC);

CREATE TABLE historico_status (
  id               bigserial PRIMARY KEY,
  vaga_usuario_id  uuid NOT NULL REFERENCES vaga_usuario(id) ON DELETE CASCADE,
  de               text,
  para             text NOT NULL,
  origem           text NOT NULL CHECK (origem IN ('sistema','ia','usuario')),
  detalhe          text,
  criado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON historico_status (vaga_usuario_id);
```

### 6.5 Consulta de consumo da fila (referência)

```sql
-- Auditor: pega lote do próximo usuário (round-robin) sem conflito entre workers
SELECT vu.id
FROM vaga_usuario vu
WHERE vu.usuario_id = :usuario_id
  AND vu.status = 'fila'
  AND (vu.proxima_tentativa_em IS NULL OR vu.proxima_tentativa_em <= now())
ORDER BY vu.score_prefiltro DESC
LIMIT :tamanho_lote
FOR UPDATE SKIP LOCKED;
```

---

## 7. Estrutura de pastas

```
job-radar/
├── docs/
│   ├── PLANO.md                    # este documento
│   └── decisoes/                   # ADRs (uma decisão por arquivo)
├── .github/workflows/
│   └── ci.yml                      # lint, testes, build e push da imagem (GHCR)
├── docker-compose.yml              # deploy local
├── Dockerfile                      # multi-stage, não-root
├── pyproject.toml
├── alembic.ini
├── .env.example
├── migrations/                     # Alembic
│   └── versions/
├── src/job_radar/
│   ├── __init__.py
│   ├── cli.py                      # Typer: api, worker, migrar, coletar, seed
│   ├── config.py                   # Settings (pydantic-settings)
│   ├── logs.py                     # logging JSON em stdout
│   ├── db.py                       # engine, sessão
│   ├── models/                     # SQLAlchemy
│   │   ├── usuario.py              # usuario, perfil, canal_notificacao
│   │   ├── provider.py             # provider_ia, uso_provider
│   │   ├── fonte.py                # fonte, execucao_coleta
│   │   ├── vaga.py                 # vaga, vaga_fonte
│   │   └── vaga_usuario.py         # vaga_usuario, auditoria, historico_status
│   ├── schemas/                    # Pydantic (VagaBruta, Vaga, ResultadoAuditoria, DTOs da API)
│   ├── coleta/
│   │   ├── base.py                 # interface Coletor + registry
│   │   ├── normalizador.py
│   │   ├── dedupe.py
│   │   └── fontes/
│   │       ├── gupy.py
│   │       ├── github_issues.py
│   │       ├── greenhouse.py
│   │       ├── lever.py
│   │       └── jobspy.py           # LinkedIn/Indeed/Glassdoor (fase 4)
│   ├── filtro/
│   │   ├── prefiltro.py            # RN08–RN12
│   │   └── localidade.py           # normalização DF/RAs, cidades
│   ├── fila/
│   │   ├── estados.py              # máquina de estados + transições válidas
│   │   ├── alimentador.py          # RN14–RN15
│   │   └── expirador.py            # RN13, RN23–RN24
│   ├── auditoria/
│   │   ├── auditor.py              # round-robin, lote, fallback, backoff
│   │   ├── prompt.py               # templates versionados
│   │   ├── limitador.py            # rate limit por provider
│   │   └── providers/
│   │       ├── base.py
│   │       ├── cli.py
│   │       └── openai_compatible.py
│   ├── notificacao/
│   │   ├── n8n.py                  # cliente do webhook
│   │   └── eventos.py              # vaga.recomendada, resumo.diario, capacidade.alerta
│   ├── seguranca/
│   │   ├── cripto.py               # Fernet
│   │   └── auth.py                 # hash de senha, sessão
│   ├── web/
│   │   ├── app.py                  # FastAPI factory
│   │   ├── rotas/                  # vagas, perfil, providers, fontes, telegram, saude (/healthz, /readyz)
│   │   ├── templates/              # Jinja2 + HTMX
│   │   └── static/
│   └── worker/
│       └── main.py                 # APScheduler: registra jobs
├── n8n/
│   └── workflows/                  # export JSON dos fluxos do n8n (versionados)
└── tests/
    ├── unit/                       # prefiltro, dedupe, estados, parsers
    ├── integration/                # banco, fila, auditor com provider fake
    └── fixtures/                   # respostas salvas das fontes (HTML/JSON)
```

---

## 8. Jobs do worker

| Job | Frequência | Janela | Ação |
|---|---|---|---|
| `coletar:<fonte>` | `fonte.intervalo_min` | 08:00–20:00 | Coleta, normaliza, dedupe, pré-filtro por usuário (só se `COLETA_NO_WORKER=true`; no K8s vira `CronJob`) |
| `alimentar_fila` | 10 min | 24h | RN14–RN15 |
| `auditar` | 1 min (loop curto) | 24h | Consome fila respeitando limites |
| `expirar` | 1h | 24h | TTLs de pool e recomendadas |
| `verificar_vagas` | 1x/dia (06:00) | — | Checa se recomendadas ainda estão no ar |
| `resumo_diario` | 20:30 | — | Evento `resumo.diario` |

---

## 9. Contrato com o n8n

`POST {N8N_WEBHOOK_URL}` com header `X-Job-Radar-Token: <segredo>`.

```json
{
  "evento": "vaga.recomendada",
  "usuario": {"id": "uuid", "telegram_chat_id": "123", "email": "..."},
  "vaga": {
    "vaga_usuario_id": "uuid",
    "titulo": "Estágio DevOps",
    "empresa": "ACME",
    "local": "Remoto",
    "url": "https://...",
    "score": 86,
    "resumo": "...",
    "gaps": ["Kubernetes"]
  },
  "acoes": {
    "confirmar": "https://<host>/api/acoes/<token-assinado>/confirmar",
    "ignorar":   "https://<host>/api/acoes/<token-assinado>/ignorar"
  }
}
```

Outros eventos: `resumo.diario`, `capacidade.alerta`, `coletor.falhando` (admin).
Tokens de ação são assinados (HMAC) e expiram com a vaga.

---

## 10. Decisões (ADRs resumidos)

| # | Decisão | Alternativas | Motivo |
|---|---|---|---|
| D01 | Lógica no core Python; n8n só para notificação | Tudo no n8n | Testabilidade, versionamento, dedupe/estado complexos. |
| D02 | Fila em tabela Postgres com `SKIP LOCKED` | Redis, RabbitMQ | Volume baixo; menos um serviço; menos RAM. |
| D03 | APScheduler em processo `worker` | Celery, cron | Simples, sem broker. |
| D04 | Coleta compartilhada (`vaga`) + estado por usuário (`vaga_usuario`) | Coleta por usuário | Coleta uma vez, audita N vezes; menos carga nas fontes. |
| D05 | Limite de ritmo na auditoria, não na coleta | Coleta em lotes de 10/h | Vagas novas não ficam de fora quando a fila enche. |
| D06 | Estados terminais (`descartada`, `ignorada`, `expirada`) persistidos | Apagar rejeitadas | Necessário para dedupe e feedback. |
| D07 | Dois adaptadores de IA (`cli`, `openai_compatible`) | SDK por provider | Cobre Groq/NVIDIA/Gemini/OpenRouter com um código. |
| D08 | CLI (Claude/Codex) restrito ao admin | Compartilhar com todos | Usa a assinatura do admin; termos de uso. |
| D09 | BYOK para usuários, chaves com Fernet | Chave central | Custo distribuído; isolamento de limites. |
| D10 | UI com Jinja2 + HTMX | React/Vue SPA | Sem build de frontend; leve. |
| D11 | Fontes iniciais: Gupy, GitHub, Greenhouse/Lever | LinkedIn primeiro | Baixo risco de bloqueio/ToS. |
| D12 | Sem candidatura automática | Auto-apply | Controle do usuário; qualidade. |
| D13 | Modelo multiusuário desde o MVP, UI para um usuário | Single-user puro | Retrofit de schema é caro. |
| D14 | Uma branch (`main`) e uma imagem; deploy por ambiente fica fora do código | Branch por ambiente | Evita divergência; o que muda é configuração, não código. |
| D15 | Manifests Kubernetes no repo separado `k8s-lab` | `k8s/` dentro deste repo | Projeto de portfólio independente; app não conhece o orquestrador. |
| D16 | `worker` sempre com 1 réplica | Múltiplas réplicas | APScheduler duplicaria jobs; escala horizontal fica na `api`. |
| D17 | Coleta exposta como comando CLI (`job-radar coletar <fonte>`) | Só via APScheduler | Permite CronJob no Kubernetes e execução manual/debug. |
| D18 | No cluster, apenas providers de API | CLI dentro do container | Autenticar Claude/Codex em container expõe a assinatura e é frágil. |

---

## 11. Fontes (prioridade)

| Fase | Fonte | Método | Observação |
|---|---|---|---|
| 1 | Gupy | Endpoint JSON público | Maior volume de estágios no BR |
| 1 | GitHub (backend-br/vagas, frontendbr/vagas e similares) | API GitHub (issues) | Oficial |
| 2 | Greenhouse / Lever / Ashby | APIs públicas por empresa | Lista de empresas em `fonte.config` |
| 4 | LinkedIn / Indeed / Glassdoor | `python-jobspy` | Frágil, rate limit baixo, sem login |
| 4 | Programathor, Vagas.com, InfoJobs | Scraping HTML | Manutenção por site |
| 4 | CIEE, Nube, Super Estágios | Scraping | Específicos de estágio |
| 5 | Google (`site:` queries) | SerpAPI/Serper | Pago com tier free |

---

## 12. Fases de execução

### Fase 0 — Fundação
- [ ] `pyproject.toml`, ruff, pytest, docker-compose (`api`, `worker`, `postgres`).
- [ ] Config (`pydantic-settings`), `.env.example`, logging JSON.
- [ ] CLI Typer (`api`, `worker`, `migrar`, `seed`, `coletar`).
- [ ] Dockerfile multi-stage não-root; `/healthz` e `/readyz`.
- [ ] GitHub Actions: lint + testes + push da imagem no GHCR.
- [ ] Models + migration inicial (schema da seção 6).
- [ ] Seed: usuário admin, perfil (Brasília-DF, estágio, palavras-chave), fontes.

### Fase 1 — MVP (usuário único)
- [ ] Interface `Coletor` + coletores Gupy e GitHub (com fixtures e testes).
- [ ] Normalizador, dedupe, pré-filtro (incluindo localidades do DF).
- [ ] Máquina de estados + `historico_status`.
- [ ] Alimentador e expirador.
- [ ] Providers `cli` e `openai_compatible`; auditor com lote, validação, fallback e backoff.
- [ ] Prompt v1 de auditoria + avaliação manual com ~20 vagas reais.
- [ ] Webhook n8n + fluxo Telegram com botões confirmar/ignorar.
- [ ] Worker com todos os jobs.

**Critério de pronto:** às 08:00 o sistema coleta, e ao longo do dia recomendadas chegam no Telegram; confirmar/ignorar pelo Telegram altera o estado.

### Fase 2 — Web UI
- [ ] Login (admin).
- [ ] Listagem por estado, detalhe da auditoria, ações.
- [ ] Edição de perfil e currículo.
- [ ] Cadastro de providers (teste de conexão, chave mascarada).
- [ ] Painel de saúde: execuções de coleta, uso de providers, erros.

### Fase 3 — Multiusuário
- [ ] Cadastro de usuários (convite).
- [ ] Vínculo Telegram via `/start <token>`.
- [ ] Round-robin no auditor; limites por usuário.
- [ ] Restrição de provider `cli` a admin.

### Fase 4 — Mais fontes
- [ ] Greenhouse/Lever (lista de empresas), jobspy, scrapers de estágio.

### Fase 5 — Refinos
- [ ] Busca Google via SerpAPI.
- [ ] Uso do feedback (`ignorada` + motivo) como exemplos no prompt.
- [ ] Estados de acompanhamento (`aplicada`, `entrevista`, `encerrada`).

---

## 13. Riscos

| Risco | Mitigação |
|---|---|
| Fonte muda HTML/endpoint | Testes com fixtures; alerta `coletor.falhando`; isolamento por plugin. |
| Bloqueio por scraping | Rate limit por fonte; user-agent honesto; priorizar APIs. |
| Cota de CLI/free tier esgotada | Fallback de providers; backpressure; lotes. |
| IA com baixa qualidade (modelos pequenos) | Avaliação com conjunto fixo de vagas; `versao_prompt` registrada; score mínimo ajustável. |
| Recomendadas travadas por falta de triagem | TTL 14 dias + alerta de 80%. |
| Vazamento de chave de API | Fernet, sem logs, máscara na UI, chave mestra fora do banco. |
| Dedupe falha (títulos diferentes p/ mesma vaga) | Hash + similaridade `pg_trgm` como checagem secundária (fase 5). |

---

## 14. Configuração (`.env`)

```
DATABASE_URL=postgresql+psycopg://jobradar:***@postgres:5432/jobradar
FERNET_KEY=...
SECRET_KEY=...                 # sessão web e tokens de ação
N8N_WEBHOOK_URL=http://n8n:5678/webhook/job-radar
N8N_WEBHOOK_TOKEN=...
TELEGRAM_BOT_TOKEN=...
TZ=America/Sao_Paulo
COLETA_NO_WORKER=true          # false no Kubernetes (coleta via CronJob)
LOG_FORMAT=json
COLETA_INICIO=08:00
COLETA_FIM=20:00
GITHUB_TOKEN=...               # opcional, aumenta rate limit
```
