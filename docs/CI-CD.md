# CI/CD: GitHub Actions e GHCR

Como o código vira uma imagem Docker publicada, e o fluxo usado para cada mudança.

## As ferramentas

| Ferramenta | O que é | Para que serve aqui |
|---|---|---|
| **GitHub Actions** | Serviço de automação do GitHub: roda *workflows* (arquivos YAML) em máquinas do GitHub quando algo acontece no repositório | Testar todo push/PR e construir a imagem |
| **GHCR** (GitHub Container Registry, `ghcr.io`) | Registro de imagens Docker do GitHub, ligado ao repositório | Guardar a imagem `ghcr.io/paulocerqr/job-radar` que o compose, o cluster e a EC2 baixam |
| **`gh`** (GitHub CLI) | Linha de comando oficial do GitHub | Abrir PRs, acompanhar o CI e fazer merge sem sair do terminal |
| **Docker Buildx** | Construtor de imagens do Docker com cache avançado | Build da imagem no CI, com cache entre execuções |

## O workflow: `.github/workflows/ci.yml`

### Quando roda

```yaml
on:
  push:
    branches: [main]   # todo push na main
  pull_request:        # todo PR (qualquer branch)
```

`concurrency` cancela uma execução antiga do mesmo branch quando chega um push novo.

### Job 1: `testes`

Roda em uma VM `ubuntu-24.04` do GitHub, com um Postgres 16 como *service container* (um banco descartável só para o job).

| Passo | O que faz |
|---|---|
| `actions/checkout@v7` | Baixa o código do commit |
| `astral-sh/setup-uv@v10.2.0` | Instala o `uv` (gerenciador de pacotes Python) na versão fixa |
| `uv sync --locked` | Instala as dependências **exatamente** como estão no `uv.lock` (falha se o lock estiver desatualizado) |
| `uv run ruff check` | Lint: erros e más práticas |
| `uv run ruff format --check` | Formatação: falha se algum arquivo não estiver formatado |
| `uv run pytest` | Testes unitários e de integração (usa o Postgres via `TEST_DATABASE_URL`) |

### Job 2: `imagem`

Só começa se `testes` passar (`needs: testes`).

| Passo | O que faz |
|---|---|
| `docker/setup-buildx-action@v4` | Prepara o Buildx |
| `docker/login-action@v4` | Login no `ghcr.io` com o `GITHUB_TOKEN` (só em push na `main`) |
| `docker/metadata-action@v6` | Calcula as tags da imagem: o SHA completo do commit e `latest` (só na `main`) |
| `docker/build-push-action@v7` | Constrói a imagem pelo `Dockerfile`; **publica só em push na `main`** |

Em um PR, a imagem é construída (para garantir que o `Dockerfile` funciona) mas **não é publicada**.

### Permissões

```yaml
permissions:
  contents: read     # ler o código
  packages: write    # publicar no GHCR
```

O `GITHUB_TOKEN` é criado automaticamente pelo GitHub para cada execução e expira no fim dela. Nenhum segredo precisou ser cadastrado no repositório.

### Runner e versões fixas

- `runs-on: ubuntu-24.04` em vez de `ubuntu-latest`: o `latest` mudou para o Ubuntu 26 em 19/10/2026; fixar evita que o CI quebre por uma troca de sistema que não foi escolhida.
- Actions nas *majors* que rodam em Node 24 (as anteriores, em Node 20, geravam avisos de depreciação).

## A imagem no GHCR

| Tag | Quando é criada | Uso |
|---|---|---|
| `<sha do commit>` | A cada push na `main` | Deploy reprodutível: aponta para um commit exato |
| `latest` | A cada push na `main` | Conveniência (desenvolvimento, compose local) |

```bash
docker pull ghcr.io/paulocerqr/job-radar:latest
docker run --rm ghcr.io/paulocerqr/job-radar:latest --help
```

**Visibilidade:** o pacote nasce privado mesmo com o repositório público; a visibilidade é configurada separadamente em *Package settings → Change visibility*. Ele foi tornado **público** para o cluster e a EC2 baixarem sem credencial (o pull anônimo foi testado).

## Fluxo de uma mudança

Toda mudança segue o mesmo caminho:

```bash
git switch -c feat/minha-mudanca          # 1. branch nova
# ... código + testes ...
uv run ruff check && uv run pytest        # 2. checagem local
git commit -m "feat: ..."                 # 3. commit (autor: você, e-mail noreply)
git push -u origin feat/minha-mudanca     # 4. envia a branch

gh pr create --base main --title "..."    # 5. abre o PR → CI roda (testes + build sem publicar)
gh run watch <id> --exit-status           # 6. acompanha o CI
gh pr merge <n> --rebase --delete-branch  # 7. merge na main (histórico linear) e apaga a branch

git switch main && git pull --ff-only     # 8. atualiza a main local
                                          # → push na main dispara o CI de novo e PUBLICA a imagem
```

| PR | Conteúdo |
|---|---|
| #1 | CI: runner fixo e actions em Node 24 |
| #2 | Coleta Gupy/GitHub até o pool |
| #3 | Alimentador e expirador |
| #4 | Auditoria por IA |
| #5, #6 | Correções de providers (chave do `.env`, modelos atualizados) |
| #7 | Telegram e calibração |
| #8 | Plano do lab movido para o repositório `k8s-lab` |

## Configuração do `gh` neste computador

```bash
sudo pacman -S github-cli
gh auth login        # GitHub.com → HTTPS → login pelo navegador
gh auth setup-git    # o git passa a usar o gh como credencial (push/fetch por HTTPS)
```

Para ler pacotes do GHCR pela API (ex.: conferir a visibilidade), o token precisa do escopo extra:

```bash
gh auth refresh -s read:packages
```

## E-mail dos commits

O repositório é público, e o e-mail do autor fica nos metadados de cada commit (visível com `git log` ou adicionando `.patch` à URL de um commit). Neste repositório, os commits usam o endereço *noreply* do GitHub:

```bash
git config user.email "163113808+paulocerqr@users.noreply.github.com"   # só neste repo
```
