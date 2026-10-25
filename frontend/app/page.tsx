'use client'

import { useMemo, useState } from 'react'
import { AppShell, useUsuario } from '@/components/AppShell'
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bell,
  Bot,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  Cloud,
  ExternalLink,
  Filter,
  GitBranch,
  LayoutDashboard,
  Network,
  Menu,
  MoreHorizontal,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TerminalSquare,
  UserRound,
  X,
  Zap,
} from 'lucide-react'

type Status = 'Nova' | 'Em análise' | 'Recomendada'

type Job = {
  id: number
  title: string
  company: string
  location: string
  mode: string
  source: string
  sourceIcon: 'github' | 'linkedin' | 'cloud'
  posted: string
  score: number
  tags: string[]
  status: Status
  tone: string
}

const jobs: Job[] = [
  { id: 1, title: 'Estágio em DevOps / Cloud', company: 'NuvemTech', location: 'Brasília, DF', mode: 'Híbrido', source: 'Gupy', sourceIcon: 'cloud', posted: 'há 2h', score: 94, tags: ['AWS', 'Docker', 'Python'], status: 'Recomendada', tone: 'violet' },
  { id: 2, title: 'Pessoa Estagiária em Backend', company: 'ContaSimples', location: 'Remoto · Brasil', mode: 'Remoto', source: 'LinkedIn', sourceIcon: 'linkedin', posted: 'há 3h', score: 91, tags: ['Python', 'APIs', 'PostgreSQL'], status: 'Nova', tone: 'blue' },
  { id: 3, title: 'Estágio em Infraestrutura', company: 'Banco Aurora', location: 'Brasília, DF', mode: 'Presencial', source: 'GitHub Jobs', sourceIcon: 'github', posted: 'há 5h', score: 87, tags: ['Linux', 'Kubernetes', 'CI/CD'], status: 'Em análise', tone: 'orange' },
  { id: 4, title: 'Estágio Desenvolvimento Fullstack', company: 'Orbe Sistemas', location: 'Remoto · Brasil', mode: 'Remoto', source: 'Gupy', sourceIcon: 'cloud', posted: 'há 6h', score: 82, tags: ['React', 'Node.js', 'TypeScript'], status: 'Nova', tone: 'cyan' },
  { id: 5, title: 'Estágio em Cloud Engineering', company: 'Vértice Digital', location: 'Brasília, DF', mode: 'Híbrido', source: 'LinkedIn', sourceIcon: 'linkedin', posted: 'ontem', score: 78, tags: ['GCP', 'Terraform', 'Linux'], status: 'Nova', tone: 'pink' },
]

const sourceIcon = { github: GitBranch, linkedin: Network, cloud: Cloud }

function Score({ value }: { value: number }) {
  return <span className={`score score-${value >= 90 ? 'high' : value >= 80 ? 'medium' : 'low'}`}><Sparkles size={13} /> {value}</span>
}

function saudacao() {
  const hora = new Date().getHours()
  return hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite'
}

// Visão geral ainda com dados de exemplo do protótipo; os reais entram com a API de vagas
function VisaoGeral() {
  const usuario = useUsuario()
  const primeiroNome = usuario?.nome.split(' ')[0] ?? ''
  const [activeTab, setActiveTab] = useState('Todas')
  const [query, setQuery] = useState('')
  const [jobsState, setJobsState] = useState(jobs)
  const [toast, setToast] = useState('')

  const filteredJobs = useMemo(() => jobsState.filter((job) => {
    const matchesTab = activeTab === 'Todas' || (activeTab === 'Novas' && job.status === 'Nova') || (activeTab === 'Recomendadas' && job.status === 'Recomendada')
    const haystack = `${job.title} ${job.company} ${job.tags.join(' ')}`.toLowerCase()
    return matchesTab && haystack.includes(query.toLowerCase())
  }), [activeTab, jobsState, query])

  function act(id: number, action: 'confirm' | 'ignore') {
    setJobsState((current) => current.map((job) => job.id === id ? { ...job, status: action === 'confirm' ? 'Recomendada' : 'Em análise' } : job))
    setToast(action === 'confirm' ? 'Vaga confirmada para acompanhamento.' : 'Vaga movida para análise.')
    window.setTimeout(() => setToast(''), 2800)
  }

  return (
    <>
      <p className="aviso-exemplo">Dados de exemplo: esta tela passa a mostrar as vagas reais na próxima etapa.</p>
      <section className="hero"><div><div className="eyebrow"><span className="live-dot" /> Radar ativo <span className="eyebrow-separator">·</span> Atualizado agora</div><h1>{saudacao()}, {primeiroNome} <span className="wave">✦</span></h1><p>Aqui está o que encontramos para você hoje.</p></div><button className="outline-button" onClick={() => { setToast('Coleta iniciada. Novas vagas aparecerão em instantes.'); window.setTimeout(() => setToast(''), 2800) }}><RefreshCw size={15} /> Rodar coleta agora</button></section>
          <section className="stats-grid"><div className="stat-card"><div className="stat-icon purple"><BriefcaseBusiness size={18} /></div><div className="stat-label">Vagas encontradas <span className="trend positive">+18,4%</span></div><strong>128</strong><small>nas últimas 24 horas</small></div><div className="stat-card"><div className="stat-icon green"><Sparkles size={18} /></div><div className="stat-label">Score médio <span className="trend positive">+6,2%</span></div><strong>84,6</strong><small>entre as vagas analisadas</small></div><div className="stat-card"><div className="stat-icon orange"><Clock3 size={18} /></div><div className="stat-label">Na fila de auditoria <span className="trend neutral">de 30</span></div><strong>12</strong><small>processadas automaticamente</small></div><div className="stat-card"><div className="stat-icon blue"><Send size={18} /></div><div className="stat-label">Recomendadas <span className="trend positive">+3 hoje</span></div><strong>24</strong><small>aguardando sua decisão</small></div></section>
          <section className="section-heading"><div><h2>Vagas no radar</h2><p>Priorizadas pelo seu perfil e auditadas por IA.</p></div><button className="text-button">Ver todas <ArrowUpRight size={15} /></button></section>
          <div className="toolbar"><div className="search-box"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar por cargo, empresa ou tecnologia..." /></div><div className="tabs">{['Todas', 'Novas', 'Recomendadas'].map(tab => <button key={tab} className={activeTab === tab ? 'tab-active' : ''} onClick={() => setActiveTab(tab)}>{tab}{tab === 'Novas' && <span>8</span>}</button>)}</div><button className="filter-button"><Filter size={16} /> Filtros <span>2</span></button></div>
          <div className="jobs-table"><div className="table-header"><span>OPORTUNIDADE</span><span>LOCALIZAÇÃO</span><span>FONTE</span><span>PUBLICADA</span><span>SCORE IA</span><span /></div>{filteredJobs.map((job) => { const SourceIcon = sourceIcon[job.sourceIcon]; return <div className="job-row" key={job.id}><div className="job-main"><div className={`company-logo ${job.tone}`}><SourceIcon size={18} /></div><div><strong>{job.title}</strong><p>{job.company} <span>·</span> {job.tags.slice(0, 2).join(' · ')}</p></div></div><div className="job-location"><span>{job.location}</span><small className={job.mode === 'Remoto' ? 'remote' : ''}>{job.mode}</small></div><div className="job-source"><SourceIcon size={14} /><span>{job.source}</span></div><div className="job-posted">{job.posted}</div><div><Score value={job.score} /></div><div className="row-actions"><button className="icon-button small" title="Abrir vaga"><ExternalLink size={15} /></button>{job.status !== 'Recomendada' && <button className="icon-button small success-action" onClick={() => act(job.id, 'confirm')} title="Confirmar vaga"><Check size={16} /></button>}</div></div> })}</div>
          <section className="bottom-grid"><div className="panel"><div className="panel-heading"><div><h3>Saúde das fontes</h3><p>Status das últimas coletas</p></div><button className="icon-button small"><MoreHorizontal size={17} /></button></div><div className="source-list">{[['Gupy', 'há 4 min', '128 vagas', 'ok'], ['GitHub Jobs', 'há 18 min', '42 vagas', 'ok'], ['LinkedIn', 'há 1h', '—', 'warn']].map(([name, time, count, state]) => <div className="source-item" key={name}><div className={`source-badge ${name === 'Gupy' ? 'gupy' : name === 'LinkedIn' ? 'linkedin' : 'github'}`}>{name === 'Gupy' ? <Cloud size={15} /> : name === 'LinkedIn' ? <Network size={15} /> : <GitBranch size={15} />}</div><div className="source-name"><strong>{name}</strong><small>{time}</small></div><span className="source-count">{count}</span><span className={`source-state ${state}`}>{state === 'ok' ? 'Operacional' : 'Atenção'}</span></div>)}</div></div><div className="panel activity-panel"><div className="panel-heading"><div><h3>Atividade recente</h3><p>O que aconteceu no seu radar</p></div><button className="text-button">Ver histórico <ArrowUpRight size={14} /></button></div><div className="activity-list"><div className="activity-item"><div className="activity-symbol green"><CheckCircle2 size={15} /></div><div><strong>3 vagas recomendadas</strong><p>Foram adicionadas à sua fila de decisão</p></div><time>há 12 min</time></div><div className="activity-item"><div className="activity-symbol purple"><Bot size={15} /></div><div><strong>Auditoria concluída</strong><p>12 vagas analisadas pelo Groq Llama</p></div><time>há 18 min</time></div></div></div></section>
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Visão geral"><VisaoGeral /></AppShell>
}
