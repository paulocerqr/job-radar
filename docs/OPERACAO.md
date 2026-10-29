# Operação e configuração

[Voltar ao README](../README.md)

Este guia reúne os comandos de administração, coleta, auditoria e notificações. Para instalar localmente, comece pelo [README](../README.md#execução-local).

## Executando os comandos

Os exemplos `job-radar ...` pressupõem a CLI instalada e as variáveis de ambiente configuradas. No host, use `uv run job-radar ...` após `uv sync`; ajuste `DATABASE_URL` para apontar para `localhost`.

Com Docker Compose, use `docker compose exec api <comando e argumentos>`, pois a API já está em execução. Por exemplo:

```bash
docker compose exec api job-radar provider listar
docker compose exec api job-radar provider adicionar groq --preset groq
docker compose exec api job-radar telegram vincular
```

Para cadastrar o currículo pelo terminal, copie o arquivo e informe seu caminho dentro do container:

```bash
docker compose cp curriculo.md api:/tmp/curriculo.md
docker compose exec api job-radar perfil curriculo /tmp/curriculo.md
```

Os comandos de perfil e providers usam `ADMIN_EMAIL` por padrão; use `--usuario <email>` para selecionar outro usuário nos comandos que oferecem essa opção. Também é possível editar o currículo pela Web UI, em **Meu perfil**.

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
# 1. se ainda não configurou: gere a chave e coloque no .env como FERNET_KEY
docker compose run --rm --no-deps api chave-fernet

# 2. providers, em ordem de prioridade. --api-key-env lê a variável do ambiente ou do .env
#    (a chave não fica no histórico do shell); sem ele, a chave é pedida no terminal
job-radar provider adicionar groq --preset groq --api-key-env GROQ_API_KEY
job-radar provider adicionar nvidia --preset nvidia --api-key-env NVIDIA_API_KEY
job-radar provider adicionar gemini --preset gemini --api-key-env GEMINI_API_KEY
job-radar provider adicionar codex-luna --preset codex # Codex CLI com gpt-6-luna, só para o admin

job-radar provider listar
job-radar provider testar groq

# 3. currículo usado para comparar requisitos
job-radar perfil curriculo curriculo.md
```

Depois de alterar o `.env`, recrie API e worker com `docker compose up -d api worker` para carregar os novos valores. Preserve a `FERNET_KEY`: trocá-la exige recadastrar as chaves de API cifradas no banco.

Os presets trazem modelo e limites iniciais. Modelos são aposentados com frequência: se o `testar` falhar com 404/410, liste os disponíveis com `job-radar provider modelos <nome>` e troque com `job-radar provider editar <nome> --modelo ...`. O worker audita um lote por usuário a cada minuto; `job-radar auditar` roda uma rodada na hora.

O preset `codex` usa `gpt-6-luna` pelo Codex CLI 0.165.0, incluído na imagem Docker. Cada auditoria roda em uma pasta temporária, em modo somente leitura e sem shell, web, plugins ou agentes auxiliares. A configuração pessoal e as instruções de arquivos AGENTS.md não são carregadas; os logs locais daquela chamada ficam na pasta temporária e são removidos ao final. O login do ChatGPT continua sendo reutilizado pelo CLI. O modelo vai pelo marcador `{modelo}` do comando, portanto `provider editar codex-luna --modelo ...` também muda o modelo realmente executado quando o comando contém esse marcador. Providers antigos não têm seu comando atualizado automaticamente.

No host, autentique com `codex login` e use `job-radar provider testar codex-luna`. No lab, o worker possui `CODEX_HOME` em um PVC exclusivo, que permite ao CLI renovar o login sem colocar tokens na imagem, no Git ou nos manifests:

```bash
kubectl -n job-radar exec -it deploy/worker -- sh -c 'umask 077; mkdir -p "$CODEX_HOME"; exec codex login --device-auth'
kubectl -n job-radar exec deploy/worker -- job-radar provider testar codex-luna
```

O login exige concluir a autenticação no navegador e a opção de device code habilitada na conta. O cadastro desse provider é feito pelo terminal do worker autenticado; as réplicas da API não recebem essa sessão. O botão **Testar conexão** solicita o teste ao worker e acompanha o resultado: ele executa antes da próxima rodada de auditoria, sem disputar memória com outra chamada do CLI. Normalmente começa em até um minuto, mas aguarda uma auditoria em andamento; após 15 minutos sem conclusão, a interface permite tentar novamente. Providers CLI continuam exclusivos do admin e não são usados como fallback dos convidados. O worker precisa de memória para o processo do CLI além da sua própria; o lab reserva limite de 512 MiB após medir aproximadamente 300 MiB no CLI isolado. O volume usa `pd-balanced` com retenção: removê-lo exige cuidar também do disco, e perder o cache exige novo login.

O CLI envia os dados da auditoria à OpenAI: usar login do ChatGPT não transforma a análise em processamento offline. As cotas do login se aplicam; os demais providers continuam disponíveis na cascata se o Codex falhar.

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
