'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Search } from 'lucide-react'
import { AppShell } from '@/components/AppShell'
import { PainelVaga, TabelaVagas } from '@/components/Vagas'
import { api } from '@/lib/api'
import { ABAS, type ListaVagas, type Resumo, ROTULO_STATUS, type Status } from '@/lib/vagas'

const VAZIO: Record<string, string> = {
  recomendada: 'Nenhuma vaga esperando decisão.',
  fila: 'A fila da IA está vazia.',
  pool: 'Nenhuma vaga no pool.',
}

function lerUrl(): { status: Status; busca: string } {
  const p = new URLSearchParams(window.location.search)
  const status = p.get('status') as Status
  return { status: ABAS.includes(status) ? status : 'recomendada', busca: p.get('busca') ?? '' }
}

function Vagas() {
  const [status, setStatus] = useState<Status | null>(null)
  const [busca, setBusca] = useState('')
  const [pagina, setPagina] = useState(1)
  const [lista, setLista] = useState<ListaVagas | null>(null)
  const [resumo, setResumo] = useState<Resumo | null>(null)
  const [aberta, setAberta] = useState<string | null>(null)
  const [toast, setToast] = useState('')

  useEffect(() => {
    const inicial = lerUrl()
    setStatus(inicial.status)
    setBusca(inicial.busca)
  }, [])

  const carregar = useCallback(() => {
    if (!status) return
    const params = new URLSearchParams({ status, pagina: String(pagina) })
    if (busca.trim()) params.set('busca', busca.trim())
    window.history.replaceState(null, '', `?${params}`)
    api<ListaVagas>(`/vagas?${params}`).then(setLista)
    api<Resumo>('/resumo').then(setResumo)
  }, [status, busca, pagina])

  useEffect(() => {
    const espera = window.setTimeout(carregar, 250) // digitação na busca
    return () => window.clearTimeout(espera)
  }, [carregar])
  const fechar = useCallback(() => setAberta(null), [])

  function aoDecidir(_id: string, _s: string, mensagem: string) {
    setToast(mensagem)
    window.setTimeout(() => setToast(''), 3500)
    carregar()
  }

  if (!status) return null
  const paginas = lista ? Math.max(1, Math.ceil(lista.total / lista.por_pagina)) : 1

  return (
    <>
      <section className="hero"><div><h1>Vagas & triagem</h1><p>Todas as vagas que passaram pelo pré-filtro, por situação.</p></div></section>
      {resumo && <section className="stats-grid" aria-label="Resumo da triagem">
        <div className="stat-card"><div className="stat-label">Recomendadas</div><strong>{resumo.contagens.recomendada}</strong><small>aguardando sua decisão</small></div>
        <div className="stat-card"><div className="stat-label">Na fila da IA</div><strong>{resumo.contagens.fila}</strong><small>aguardando auditoria</small></div>
        <div className="stat-card"><div className="stat-label">Pool</div><strong>{resumo.contagens.pool}</strong><small>aguardando espaço na fila</small></div>
        <div className="stat-card"><div className="stat-label">Confirmadas</div><strong>{resumo.contagens.confirmada}</strong><small>selecionadas por você</small></div>
      </section>}
      <div className="toolbar">
        <div className="search-box"><Search size={17} /><input aria-label="Buscar por cargo ou empresa" value={busca} onChange={(e) => { setBusca(e.target.value); setPagina(1) }} placeholder="Buscar por cargo ou empresa…" /></div>
      </div>
      <div className="tabs tabs-status" role="tablist">
        {ABAS.map((aba) => (
          <button key={aba} role="tab" aria-selected={aba === status} className={aba === status ? 'tab-active' : ''} onClick={() => { setStatus(aba); setPagina(1) }}>
            {ROTULO_STATUS[aba]}{resumo && <span>{resumo.contagens[aba]}</span>}
          </button>
        ))}
      </div>
      {!lista || !resumo ? <div className="carregando-bloco">Carregando…</div> : (
        <>
          <TabelaVagas itens={lista.itens} motivos={resumo.motivos_ignorar} aoAbrir={setAberta} aoDecidir={aoDecidir}
            vazio={busca ? 'Nenhuma vaga encontrada para essa busca.' : VAZIO[status] ?? 'Nenhuma vaga aqui.'} />
          {paginas > 1 && (
            <div className="paginacao">
              <button className="outline-button" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>Anterior</button>
              <span>Página {pagina} de {paginas} · {lista.total} vagas</span>
              <button className="outline-button" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Próxima</button>
            </div>
          )}
        </>
      )}
      {aberta && resumo && <PainelVaga id={aberta} motivos={resumo.motivos_ignorar} aoFechar={fechar} aoDecidir={aoDecidir} />}
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Vagas"><Vagas /></AppShell>
}
