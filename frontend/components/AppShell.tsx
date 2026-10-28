'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Bot, BriefcaseBusiness, LayoutDashboard, LogOut, Menu, Search, X, Users,
  SlidersHorizontal, UserRound,
} from 'lucide-react'
import { api, definirCsrf, type Usuario } from '@/lib/api'

const ContextoUsuario = createContext<Usuario | null>(null)
export const useUsuario = () => useContext(ContextoUsuario)

type ItemMenu = { href: string; rotulo: string; Icone: LucideIcon; pronto: boolean; soAdmin?: boolean }

const PRINCIPAL: ItemMenu[] = [
  { href: '/', rotulo: 'Visão geral', Icone: LayoutDashboard, pronto: true },
  { href: '/vagas/', rotulo: 'Vagas & triagem', Icone: BriefcaseBusiness, pronto: true },
]
const CONFIGURACAO: ItemMenu[] = [
  { href: '/perfil/', rotulo: 'Meu perfil & regras', Icone: UserRound, pronto: true },
  { href: '/providers/', rotulo: 'Providers de IA', Icone: Bot, pronto: true },
  { href: '/fontes/', rotulo: 'Fontes e coleta', Icone: SlidersHorizontal, pronto: true },
  { href: '/usuarios/', rotulo: 'Usuários & convites', Icone: Users, pronto: true, soAdmin: true },
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
    <Link href={item.href} className={`nav-item ${ativo ? 'active' : ''}`} title={item.rotulo} aria-label={item.rotulo} aria-current={ativo ? 'page' : undefined}>
      <Icone size={18} />
      {aberto && <span>{item.rotulo}</span>}
    </Link>
  )
}

export function AppShell({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  const caminho = usePathname()
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [aberto, setAberto] = useState(true)
  const [menuMobile, setMenuMobile] = useState(false)
  const [mobile, setMobile] = useState(false)
  const menu = useRef<HTMLElement>(null)
  const abrirMenu = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const tela = window.matchMedia('(max-width: 700px)')
    const atualizar = () => { setMobile(tela.matches); setMenuMobile(false) }
    atualizar()
    tela.addEventListener('change', atualizar)
    return () => tela.removeEventListener('change', atualizar)
  }, [])

  useEffect(() => {
    // sem sessão, o cliente da API manda para /login
    api<{ usuario: Usuario; csrf: string }>('/sessao').then(({ usuario, csrf }) => {
      definirCsrf(csrf)
      setUsuario(usuario)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!menuMobile) return
    const anterior = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const botoes = menu.current?.querySelectorAll<HTMLElement>('a[href], button')
    botoes?.[0]?.focus()
    const fechar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuMobile(false)
      if (e.key !== 'Tab' || !botoes?.length) return
      const primeiro = botoes[0]
      const ultimo = botoes[botoes.length - 1]
      if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus() }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus() }
    }
    window.addEventListener('keydown', fechar)
    return () => {
      window.removeEventListener('keydown', fechar)
      document.body.style.overflow = anterior
      abrirMenu.current?.focus()
    }
  }, [menuMobile])

  async function sair() {
    await api('/sair', { metodo: 'POST' }).catch(() => {})
    window.location.assign('/login/')
  }

  if (!usuario) return <div className="carregando-tela" aria-busy="true" />

  const ativo = (href: string) => (href === '/' ? caminho === '/' : caminho.startsWith(href))

  return (
    <ContextoUsuario.Provider value={usuario}>
      <div className="app-shell">
        <button className={`menu-backdrop ${menuMobile ? 'visivel' : ''}`} aria-label="Fechar menu" onClick={() => setMenuMobile(false)} />
        <aside ref={menu} inert={mobile && !menuMobile} id="menu-principal" className={`sidebar ${aberto ? '' : 'sidebar-collapsed'} ${menuMobile ? 'menu-aberto' : ''}`} onClick={(e) => { if ((e.target as HTMLElement).closest('a, button')) setMenuMobile(false) }}>
          <button className="icon-button mobile-menu" aria-label="Fechar navegação" onClick={() => setMenuMobile(false)}><X size={19} /></button>
          <div className="brand"><div className="brand-mark"><RadarMark /></div>{aberto && <span className="brand-copy">Job Radar<small>COLETA & AUDITORIA IA</small></span>}</div>
          <div className="workspace"><div className="workspace-avatar">{iniciais(usuario.nome)}</div>{aberto && <div className="workspace-copy"><strong>{usuario.nome}</strong><small>{usuario.email}</small></div>}</div>
          <nav className="main-nav" aria-label="Operações">{aberto && <div className="section-label">OPERAÇÕES</div>}{PRINCIPAL.map((item) => <Item key={item.href} item={item} ativo={ativo(item.href)} aberto={aberto} />)}</nav>
          <div className="sidebar-section">
            {aberto && <div className="section-label">AUDITORIA & REGRAS</div>}
            {CONFIGURACAO.filter((item) => !item.soAdmin || usuario.papel === 'admin').map((item) => <Item key={item.href} item={item} ativo={ativo(item.href)} aberto={aberto} />)}
          </div>
          <div className="sidebar-bottom">
            <button className="nav-item" onClick={sair} title="Sair" aria-label="Encerrar sessão"><LogOut size={18} />{aberto && <span>Encerrar sessão</span>}</button>
          </div>
        </aside>
        <a className="skip-link" href="#conteudo">Pular para o conteúdo</a>
        <main className="main-content" id="conteudo" inert={mobile && menuMobile}>
          <header className="topbar">
            <button className="icon-button desktop-menu" onClick={() => setAberto(!aberto)} aria-label={aberto ? "Recolher menu" : "Expandir menu"} aria-expanded={aberto} aria-controls="menu-principal"><Menu size={19} /></button>
            <button ref={abrirMenu} className="icon-button mobile-menu" onClick={() => { setAberto(true); setMenuMobile(true) }} aria-label={menuMobile ? "Fechar menu" : "Abrir menu"} aria-expanded={menuMobile} aria-controls="menu-principal">{menuMobile ? <X size={19} /> : <Menu size={19} />}</button>
            <div className="breadcrumbs"><span>Job Radar</span><span>/</span><strong>{titulo}</strong></div>
            <div className="topbar-actions"><form action="/vagas/" className="search-box global-search" role="search"><Search size={16} /><input name="busca" aria-label="Buscar vagas por cargo ou empresa" placeholder="Buscar vagas ou empresas…" /></form><div className="user-copy"><strong>{usuario.nome}</strong><small>{usuario.papel === 'admin' ? 'Administrador' : 'Usuário'}</small></div><div className="avatar" title={usuario.email}>{iniciais(usuario.nome)}</div></div>
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
