'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createContext, useContext, useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Bot, BriefcaseBusiness, LayoutDashboard, LogOut, Menu,
  SlidersHorizontal, UserRound,
} from 'lucide-react'
import { api, definirCsrf, type Usuario } from '@/lib/api'

const ContextoUsuario = createContext<Usuario | null>(null)
export const useUsuario = () => useContext(ContextoUsuario)

type ItemMenu = { href: string; rotulo: string; Icone: LucideIcon; pronto: boolean }

const PRINCIPAL: ItemMenu[] = [
  { href: '/', rotulo: 'Visão geral', Icone: LayoutDashboard, pronto: true },
  { href: '/vagas/', rotulo: 'Vagas', Icone: BriefcaseBusiness, pronto: true },
]
const CONFIGURACAO: ItemMenu[] = [
  { href: '/perfil/', rotulo: 'Meu perfil', Icone: UserRound, pronto: true },
  { href: '/providers/', rotulo: 'Providers de IA', Icone: Bot, pronto: false },
  { href: '/fontes/', rotulo: 'Fontes e coleta', Icone: SlidersHorizontal, pronto: false },
]

function iniciais(nome: string) {
  return nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('')
}

function Item({ item, ativo, aberto }: { item: ItemMenu; ativo: boolean; aberto: boolean }) {
  const { Icone } = item
  if (!item.pronto) {
    return (
      <span className="nav-item nav-item-off" title={`${item.rotulo} (em breve)`}>
        <Icone size={18} />
        {aberto && <span>{item.rotulo}</span>}
      </span>
    )
  }
  return (
    <Link href={item.href} className={`nav-item ${ativo ? 'active' : ''}`} title={item.rotulo}>
      <Icone size={18} />
      {aberto && <span>{item.rotulo}</span>}
    </Link>
  )
}

export function AppShell({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  const caminho = usePathname()
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [aberto, setAberto] = useState(true)

  useEffect(() => {
    // sem sessão, o cliente da API manda para /login
    api<{ usuario: Usuario; csrf: string }>('/sessao').then(({ usuario, csrf }) => {
      definirCsrf(csrf)
      setUsuario(usuario)
    }).catch(() => {})
  }, [])

  async function sair() {
    await api('/sair', { metodo: 'POST' }).catch(() => {})
    window.location.assign('/login/')
  }

  if (!usuario) return <div className="carregando-tela" aria-busy="true" />

  const ativo = (href: string) => (href === '/' ? caminho === '/' : caminho.startsWith(href))

  return (
    <ContextoUsuario.Provider value={usuario}>
      <div className="app-shell">
        <aside className={`sidebar ${aberto ? '' : 'sidebar-collapsed'}`}>
          <div className="brand"><div className="brand-mark"><RadarMark /></div>{aberto && <span>job<span>radar</span></span>}</div>
          <div className="workspace"><div className="workspace-avatar">{iniciais(usuario.nome)}</div>{aberto && <div className="workspace-copy"><strong>{usuario.nome}</strong><small>{usuario.email}</small></div>}</div>
          <nav className="main-nav">{PRINCIPAL.map((item) => <Item key={item.href} item={item} ativo={ativo(item.href)} aberto={aberto} />)}</nav>
          <div className="sidebar-section">
            {aberto && <div className="section-label">CONFIGURAÇÃO</div>}
            {CONFIGURACAO.map((item) => <Item key={item.href} item={item} ativo={ativo(item.href)} aberto={aberto} />)}
          </div>
          <div className="sidebar-bottom">
            <button className="nav-item" onClick={sair} title="Sair"><LogOut size={18} />{aberto && <span>Sair</span>}</button>
          </div>
        </aside>
        <main className="main-content">
          <header className="topbar">
            <button className="icon-button" onClick={() => setAberto(!aberto)} aria-label="Recolher menu"><Menu size={19} /></button>
            <div className="breadcrumbs"><span>Job Radar</span><span>/</span><strong>{titulo}</strong></div>
            <div className="topbar-actions"><div className="avatar" title={usuario.email}>{iniciais(usuario.nome)}</div></div>
          </header>
          <div className="content-wrap">{children}</div>
        </main>
      </div>
    </ContextoUsuario.Provider>
  )
}

export function RadarMark() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12a8 8 0 1 0 16 0M7.5 12a4.5 4.5 0 1 0 9 0M12 12h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/><path d="M12 12 20 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
}
