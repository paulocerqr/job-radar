# k8s-lab — Esboço

> Rascunho do repositório **`k8s-lab`** (projeto de portfólio separado).
> Objetivo: demonstrar Cloud (GCP) e Kubernetes self-managed (kubeadm) rodando um sistema real — o **Job Radar** — e o **n8n**.
> Este arquivo deve ser movido para o repo `k8s-lab` quando ele for criado.
> Status: **planejamento**. Data: 2026-10-17.

---

## 1. Objetivos

| # | Objetivo | Evidência para o portfólio |
|---|---|---|
| O1 | Provisionar infraestrutura como código | Terraform cria rede, firewall, IP e 3 VMs |
| O2 | Montar cluster Kubernetes do zero | kubeadm + CNI, sem GKE |
| O3 | Rodar aplicação real com estado | Job Radar (API, worker, CronJobs) + Postgres + n8n |
| O4 | Expor com segurança | Ingress + TLS (cert-manager / Let's Encrypt) |
| O5 | Demonstrar resiliência | `kubectl drain` de um worker sem indisponibilidade da API |
| O6 | Entrega contínua | CI publica imagem; GitOps (ArgoCD) aplica no cluster |
| O7 | Observabilidade | Prometheus + Grafana + logs |

Escopo mínimo: **O1–O5**. **O6–O7** são diferenciais se os créditos permitirem.

---

## 2. Topologia

```
                         Internet
                            │  (IP estático, DNS: *.lab.<dominio>)
                            ▼
┌──────────────────────── VPC k8s-lab (GCP, us-east1 / southamerica-east1) ───────────────┐
│  Subnet 10.10.0.0/24                                                                  │
│                                                                                       │
│  ┌───────────────────┐    ┌───────────────────────────┐   ┌───────────────────────────┐│
│  │ cp-1 (e2-medium)  │    │ worker-1 (e2-medium)      │   │ worker-2 (e2-medium)      ││
│  │ control plane     │    │ ingress-nginx (hostPort)  │   │                           ││
│  │ etcd, apiserver,  │    │ api (réplica)             │   │ api (réplica)             ││
│  │ scheduler, ctrl-mgr│   │ postgres (PVC)            │   │ worker job-radar          ││
│  │ taint NoSchedule  │    │ ...                       │   │ n8n (PVC) ...             ││
│  └───────────────────┘    └───────────────────────────┘   └───────────────────────────┘│
│        CNI: Cilium (Pod CIDR 10.244.0.0/16)                                           │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

> A distribuição de pods nos workers acima é **ilustrativa** — quem decide é o scheduler. Afinidade só onde há motivo (ex.: Postgres preso ao nó do volume quando usar `local-path`).

### 2.1 VMs

| VM | Tipo | Disco | Papel |
|---|---|---|---|
| `cp-1` | e2-medium (2 vCPU, 4 GB) | 30 GB pd-balanced | control plane (taint padrão mantido) |
| `worker-1` | e2-medium | 30 GB + disco de dados (se PD CSI não for usado) | workloads |
| `worker-2` | e2-medium | 30 GB | workloads |

- SO: Ubuntu 24.04 LTS ou Debian 12.
- Runtime: **containerd**.
- Versão do Kubernetes: fixar uma minor (ex.: `1.33.x`) e documentar o upgrade como exercício.
- **Custo:** estimar no Pricing Calculator antes; desligar VMs (`terraform` com variável `ligado=false` ou `gcloud compute instances stop`) quando não estiver demonstrando.

### 2.2 Rede e firewall

| Regra | Origem | Destino | Portas |
|---|---|---|---|
| SSH | seu IP / IAP | todas | 22 |
| API server | seu IP | cp-1 | 6443 |
| Interno do cluster | subnet | todas | todas (simplifica; restringir depois como exercício) |
| HTTP/HTTPS | 0.0.0.0/0 | worker com ingress | 80, 443 |

- IP externo estático no nó do ingress (ou só nele; demais nós sem IP público + Cloud NAT).
- DNS: registro `A` para `jobradar.lab.<dominio>` e `n8n.lab.<dominio>`.

---

## 3. Decisões

| # | Decisão | Alternativas | Motivo |
|---|---|---|---|
| K01 | **kubeadm** em VMs na GCP | GKE, k3s | Mostra domínio dos componentes do cluster (etcd, apiserver, certificados, upgrade); é a base da CKA/CKS. GKE esconde o control plane; k3s abstrai demais para o objetivo de estudo. |
| K12 | **k3s single-node** no servidor local como destino permanente (opcional) | Voltar ao docker-compose | Leve (~500 MB–1 GB), já traz ServiceLB, Traefik e local-path; reaproveita os manifests via overlay `local`. docker-compose fica como plano B se faltar RAM. |
| K02 | **Cilium** como CNI | Calico, Flannel | NetworkPolicy + Hubble (visualização de tráfego) rende boa documentação. |
| K03 | **ingress-nginx** com `hostPort` em um worker + IP estático | Service LoadBalancer, cloud-controller-manager | Fora do GKE não há LB automático; hostPort é simples e explicável. CCM fica como evolução. |
| K04 | Armazenamento: começar com **local-path-provisioner**; evoluir para **GCE PD CSI driver** | Só PD CSI | local-path é trivial; PD CSI é o "upgrade" documentado (volume sobrevive à troca de nó). |
| K05 | **cert-manager** + Let's Encrypt (HTTP-01) | Certificados manuais | TLS automático. |
| K06 | Manifests com **Kustomize** (`base` + `overlays/gcp`) | Helm próprio | Nativo do kubectl, legível no portfólio. Helm só para terceiros (ingress, cert-manager, monitoring). |
| K07 | Segredos com **Sealed Secrets** | SOPS, External Secrets + Secret Manager | Commitável no Git, sem dependência extra. External Secrets fica como evolução. |
| K08 | GitOps com **ArgoCD** (fase opcional) | Flux, `kubectl apply` no CI | UI ajuda na demonstração. |
| K09 | Imagens no **GHCR** | Artifact Registry | Já publicadas pelo CI do Job Radar; sem custo. |
| K10 | Coleta do Job Radar via **CronJob** | APScheduler no worker | Recurso nativo do K8s; `COLETA_NO_WORKER=false`. |
| K11 | Apenas providers de IA via API no cluster | CLI Claude/Codex | Ver D18 no plano do Job Radar. |

---

## 4. Workloads

### 4.1 Namespaces

| Namespace | Conteúdo |
|---|---|
| `job-radar` | api, worker, cronjobs, postgres, n8n |
| `ingress-nginx` | controller |
| `cert-manager` | cert-manager |
| `kube-system` | cilium, sealed-secrets, local-path / pd-csi |
| `argocd` | (opcional) |
| `monitoring` | (opcional) kube-prometheus-stack, loki |

### 4.2 Job Radar

| Recurso | Tipo | Detalhes |
|---|---|---|
| `jobradar-migrar` | **Job** (ArgoCD PreSync hook ou aplicado antes) | `job-radar migrar` |
| `jobradar-api` | **Deployment**, 2 réplicas | `job-radar api`; probes `/healthz` e `/readyz`; `topologySpreadConstraints` por nó; PDB `minAvailable: 1` |
| `jobradar-api` | **Service** ClusterIP | porta 8000 |
| `jobradar-worker` | **Deployment**, 1 réplica, `strategy: Recreate` | `job-radar worker`; evita dois schedulers ativos durante rollout |
| `jobradar-coletar-<fonte>` | **CronJob** | `job-radar coletar gupy`; `schedule: "0 8-20 * * *"`, `timeZone: America/Sao_Paulo`, `concurrencyPolicy: Forbid` |
| `jobradar-config` | **ConfigMap** | `TZ`, `COLETA_NO_WORKER=false`, `LOG_FORMAT=json`, URLs internas |
| `jobradar-secrets` | **SealedSecret** | `DATABASE_URL`, `FERNET_KEY`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `N8N_WEBHOOK_TOKEN` |
| `jobradar` | **Ingress** | `jobradar.lab.<dominio>` com TLS |
| NetworkPolicy | — | Postgres só aceita tráfego de pods `app.kubernetes.io/part-of=job-radar` |

Recursos iniciais (ajustar após medir):

| Pod | requests | limits |
|---|---|---|
| api | 100m / 192Mi | 500m / 384Mi |
| worker | 100m / 192Mi | 500m / 384Mi |
| coletar | 50m / 128Mi | 300m / 256Mi |
| postgres | 100m / 256Mi | 500m / 512Mi |
| n8n | 100m / 256Mi | 500m / 512Mi |

### 4.3 Postgres

- **StatefulSet** 1 réplica + `volumeClaimTemplates` (5–10 GB) + Service headless.
- Backup: **CronJob** diário com `pg_dump` enviando para um bucket GCS (exercício de Workload Identity/Service Account na VM).
- Alternativa futura: operador (CloudNativePG) — bom tema de artigo.

### 4.4 n8n

- **Deployment** 1 réplica + PVC (`/home/node/.n8n`), usando o mesmo Postgres (database `n8n`) ou SQLite no PVC.
- Ingress `n8n.lab.<dominio>` com autenticação.
- Webhook do Job Radar aponta para o Service interno: `http://n8n.job-radar.svc:5678/webhook/job-radar`.
- Workflows importados de `job-radar/n8n/workflows/`.

---

## 5. Estrutura do repositório

```
k8s-lab/
├── README.md                     # visão geral, diagrama, como reproduzir, custos
├── docs/
│   ├── 00-arquitetura.md
│   ├── 01-terraform.md
│   ├── 02-kubeadm.md             # passo a passo + problemas encontrados
│   ├── 03-rede-cni.md
│   ├── 04-storage.md             # local-path → PD CSI
│   ├── 05-ingress-tls.md
│   ├── 06-deploy-job-radar.md
│   ├── 07-resiliencia.md         # drain, kill de pod, PDB (com prints/gravações)
│   ├── 08-gitops.md              # opcional
│   ├── 09-observabilidade.md     # opcional
│   ├── decisoes/                 # ADRs K01..K11
│   └── img/
├── terraform/
│   ├── main.tf                   # provider, VPC, subnet, firewall, IP, VMs
│   ├── variables.tf              # projeto, região, tipo de máquina, ligado=true/false
│   ├── outputs.tf                # IPs, comando ssh
│   └── terraform.tfvars.example
├── ansible/
│   ├── inventory.ini             # gerado a partir dos outputs do Terraform
│   ├── playbooks/
│   │   ├── 00-preparar-nos.yml   # swap off, módulos, sysctl, containerd, kubeadm/kubelet/kubectl
│   │   ├── 01-control-plane.yml  # kubeadm init + CNI
│   │   └── 02-workers.yml        # kubeadm join
│   └── roles/
├── cluster/                      # componentes de plataforma (Helm values + Kustomize)
│   ├── cilium/
│   ├── ingress-nginx/
│   ├── cert-manager/             # + ClusterIssuer letsencrypt
│   ├── sealed-secrets/
│   ├── storage/                  # local-path e/ou gce-pd-csi
│   ├── argocd/                   # opcional
│   └── monitoring/               # opcional
├── apps/
│   ├── job-radar/
│   │   ├── base/                 # deployment-api, deployment-worker, cronjobs, job-migrar,
│   │   │                         # service, configmap, pdb, networkpolicy, kustomization.yaml
│   │   └── overlays/
│   │       ├── gcp/              # ingress, sealedsecret, tag da imagem, recursos
│   │       └── local/            # k3s no servidor local (fase G)
│   ├── postgres/
│   │   └── base/                 # statefulset, service, cronjob-backup
│   └── n8n/
│       └── base/
├── argocd/                       # opcional: Applications (app-of-apps)
├── scripts/
│   ├── kubeconfig.sh             # copia admin.conf do cp-1
│   └── demo-drain.sh             # roteiro da demonstração de resiliência
└── Makefile                      # make infra | cluster | plataforma | apps | destruir
```

---

## 6. Fases

### Fase A — Infraestrutura (Terraform)
- [ ] Projeto GCP, budget alert, conta de serviço do Terraform.
- [ ] VPC, subnet, firewall, IP estático, 3 VMs.
- [ ] Variável para ligar/desligar VMs.

### Fase B — Cluster (kubeadm)
- [ ] Preparar nós (containerd, sysctl, kubeadm/kubelet/kubectl) via Ansible.
- [ ] `kubeadm init` no `cp-1`; instalar Cilium; `kubeadm join` nos workers.
- [ ] Validar: `kubectl get nodes`, pod de teste, DNS do cluster.

### Fase C — Plataforma
- [ ] local-path-provisioner (StorageClass padrão).
- [ ] ingress-nginx (hostPort no worker com IP estático).
- [ ] cert-manager + ClusterIssuer; DNS apontando para o IP.
- [ ] Sealed Secrets.

### Fase D — Aplicações
- [ ] Postgres (StatefulSet) + backup para GCS.
- [ ] Job Radar: Job de migração, api, worker, CronJobs, Ingress com TLS.
- [ ] n8n + import dos workflows; integração com o Telegram.
- [ ] NetworkPolicies.

**Critério de pronto do lab:** `https://jobradar.lab.<dominio>` acessível com TLS, recomendadas chegando no Telegram via n8n do cluster, e `kubectl drain worker-X` sem indisponibilidade da API.

### Fase E — Diferenciais (opcional)
- [ ] ArgoCD (app-of-apps) — CI do Job Radar atualiza a tag no overlay.
- [ ] kube-prometheus-stack + dashboards; Loki para logs.
- [ ] GCE PD CSI driver substituindo local-path.
- [ ] Upgrade de versão do cluster documentado.

### Fase F — Encerramento dos créditos
- [ ] Backup final do Postgres; exportar para o servidor local.
- [ ] Gravar demonstração / prints para o README.
- [ ] `terraform destroy`.
- [ ] Job Radar continua no servidor local: k3s (Fase G) ou docker-compose (plano B), mesma imagem.

### Fase G — k3s no servidor local (opcional)

Pré-requisito: ~600 MB–1 GB de RAM livre no servidor local.

- [ ] Instalar k3s single-node (`--disable traefik` se preferir manter ingress-nginx por consistência com a GCP).
- [ ] Criar `apps/job-radar/overlays/local`, `apps/postgres/overlays/local` e `apps/n8n/overlays/local`:
  - `jobradar-api` com 1 réplica, sem `topologySpreadConstraints` e sem PDB;
  - recursos (requests/limits) reduzidos;
  - StorageClass `local-path` (embutida no k3s);
  - Ingress com host da rede local; TLS opcional;
  - provider CLI (Claude/Codex) indisponível no cluster: manter auditoria por API **ou** manter o `worker` fora do cluster (ver nota).
- [ ] Decidir sobre o n8n: migrar para o cluster ou apontar o webhook para a instância já existente no servidor (`ExternalName` Service ou URL direta).
- [ ] Restaurar o backup do Postgres vindo da GCP.
- [ ] Documentar em `docs/10-k3s-local.md`: diferenças kubeadm × k3s na prática e "mesmo app, dois clusters".

> **Nota (CLI no k3s local):** se a auditoria pelo Claude/Codex CLI for essencial no ambiente local, a opção mais simples é rodar o `job-radar worker` fora do k3s (systemd ou container no host com o CLI autenticado), conectado ao Postgres do cluster. O resto (api, CronJobs, Postgres) fica no k3s.

### Comparativo kubeadm × k3s (referência)

| | kubeadm | k3s |
|---|---|---|
| Instalação | Manual (containerd, sysctl, CNI, join) | Um comando por nó |
| RAM do control plane | ~1,5–2 GB | ~0,5–1 GB |
| Já incluído | Nada (escolhe-se CNI, ingress, storage) | Flannel, Traefik, ServiceLB, local-path, CoreDNS |
| LoadBalancer fora de nuvem gerenciada | Requer solução extra | ServiceLB embutido |
| Control plane | Static pods visíveis (etcd, apiserver...) | Binário único (SQLite ou etcd embutido) |
| Certificações (CKA/CKS) | Usam kubeadm | — |
| Uso neste projeto | Lab na GCP (estudo/portfólio) | Ambiente permanente local |

---

## 7. Dependências do Job Radar

O que o repo `job-radar` precisa entregar para o lab funcionar (já incluído em `docs/PLANO.md`):

| Item | Referência no PLANO.md |
|---|---|
| Imagem publicada no GHCR com tag `sha` | Stack (CI), D14 |
| Config 100% por env, logs JSON em stdout | RNF09 |
| `/healthz` e `/readyz` | RNF10 |
| `job-radar migrar` separado do startup | RNF11, D17 |
| Shutdown gracioso | RNF12 |
| `job-radar coletar <fonte>` + `COLETA_NO_WORKER` | D17, seção 3.3 |
| Worker com 1 réplica | D16 |
| Providers só via API no cluster | D18 |

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Créditos acabam antes do fim | Budget alert; desligar VMs fora de uso; priorizar Fases A–D. |
| Nó do Postgres cai com local-path | Backup diário no GCS; migrar para PD CSI na Fase E. |
| IP do ingress preso a um worker (ponto único) | Documentar como limitação conhecida; evolução: CCM + LB da GCP. |
| Rate limit do Let's Encrypt em testes | Usar o issuer `staging` até validar. |
| Duas instâncias do Job Radar (local + cluster) coletando e notificando ao mesmo tempo | Usar bots/chats do Telegram diferentes ou desligar um ambiente durante a demonstração. |
