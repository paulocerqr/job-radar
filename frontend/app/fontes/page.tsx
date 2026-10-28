'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Play, RefreshCw } from 'lucide-react'
import { AppShell } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'
import { tempoRelativo } from '@/lib/vagas'

type Execucao = {
  id: string; fonte_id: string; iniciada_em: string; finalizada_em: string | null; status: string
  coletadas: number; novas: number; duplicadas: number; erro: string | null
}
type Fonte = {
  id: string; nome: string; ativa: boolean; implementada: boolean; intervalo_min: number; max_itens: number
  confiabilidade: number; config: Record<string, unknown>; ultima: Execucao | null
}
type Dados = { fontes: Fonte[]; execucoes: Execucao[]; pode_alterar: boolean }

const ROTULO_STATUS: Record<string, string> = { ok: 'OK', parcial: 'Parcial', erro: 'Erro', rodando: 'Rodando' }

function duracao(e: Execucao) {
  if (!e.finalizada_em) return '—'
  const s = Math.round((new Date(e.finalizada_em).getTime() - new Date(e.iniciada_em).getTime()) / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

/** O que a fonte busca, em linguagem de gente (cada coletor tem a sua config). */
function parametros(config: Record<string, unknown>): string[] {
  const itens: string[] = []
  const termos = config.termos as string[] | undefined
  if (termos?.length) itens.push(`termos: ${termos.join(', ')}`)
  for (const filtro of (config.filtros ?? config.buscas ?? []) as Record<string, string>[]) {
    itens.push(Object.entries(filtro).map(([k, v]) => `${k}=${v}`).join(' · '))
  }
  if (typeof config.repositorio === 'string') itens.push(`repositório: ${config.repositorio}`)
  return itens
}

function Fontes() {
  const [dados, setDados] = useState<Dados | null>(null)
  const [toast, setToast] = useState('')

  const carregar = useCallback(() => api<Dados>('/fontes').then(setDados), [])
  useEffect(() => { carregar() }, [carregar])

  // enquanto houver coleta rodando, atualiza a cada 5 s
  const rodando = dados?.fontes.some((f) => f.ultima?.status === 'rodando') ?? false
  useEffect(() => {
    if (!rodando) return
    const t = window.setInterval(carregar, 5000)
    return () => window.clearInterval(t)
  }, [rodando, carregar])

  function avisar(texto: string) {
    setToast(texto)
    window.setTimeout(() => setToast(''), 3500)
  }

  async function alternar(f: Fonte) {
    try {
      await api(`/fontes/${f.id}`, { metodo: 'PATCH', corpo: { ativa: !f.ativa } })
      avisar(f.ativa ? `${f.nome} desativada: as próximas coletas agendadas não rodam.` : `${f.nome} ativada.`)
      carregar()
    } catch (e) { avisar(e instanceof ErroApi ? e.message : 'Erro') }
  }

  async function coletar(f: Fonte) {
    try {
      await api(`/fontes/${f.id}/coletar`, { metodo: 'POST' })
      avisar(`Coleta de ${f.nome} iniciada.`)
      window.setTimeout(carregar, 1500)
    } catch (e) { avisar(e instanceof ErroApi ? e.message : 'Erro') }
  }

  if (!dados) return <div className="carregando-bloco">Carregando…</div>
  const nomes = Object.fromEntries(dados.fontes.map((f) => [f.id, f.nome]))

  return (
    <>
      <section className="hero">
        <div><h1>Fontes & coletas</h1><p>De onde vêm as vagas. As coletas agendadas rodam das 8h às 20h.</p></div>
        <button className="outline-button" onClick={carregar}><RefreshCw size={15} /> Atualizar</button>
      </section>

      <section className="stats-grid" aria-label="Resumo das fontes">
        <div className="stat-card"><div className="stat-label">Fontes ativas</div><strong>{dados.fontes.filter((f) => f.ativa && f.implementada).length}</strong><small>{dados.fontes.length} cadastradas</small></div>
        <div className="stat-card"><div className="stat-label">Em execução</div><strong>{dados.fontes.filter((f) => f.ultima?.status === 'rodando').length}</strong><small>coletas em andamento</small></div>
        <div className="stat-card"><div className="stat-label">Vagas vistas</div><strong>{dados.execucoes.reduce((n, e) => n + e.coletadas, 0).toLocaleString('pt-BR')}</strong><small>nas últimas {dados.execucoes.length} execuções</small></div>
        <div className="stat-card"><div className="stat-label">Vagas novas</div><strong>{dados.execucoes.reduce((n, e) => n + e.novas, 0).toLocaleString('pt-BR')}</strong><small>nas últimas {dados.execucoes.length} execuções</small></div>
      </section>
      <div className="cartoes-fonte">
        {dados.fontes.map((f) => (
          <section className={`panel fonte ${f.ativa ? '' : 'fonte-off'}`} key={f.id}>
            <div className="fonte-topo">
              <div className="source-badge gupy">{f.nome.slice(0, 1)}</div>
              <div className="fonte-nome"><strong>{f.nome}</strong><small>{f.implementada ? `a cada ${f.intervalo_min} min · até ${f.max_itens} vagas` : 'coletor ainda não implementado'}</small></div>
              {f.implementada && (
                <label className="interruptor" title={dados.pode_alterar ? '' : 'Só o admin altera'}>
                  <input type="checkbox" checked={f.ativa} disabled={!dados.pode_alterar} onChange={() => alternar(f)} />
                  <span>{f.ativa ? 'Ativa' : 'Desativada'}</span>
                </label>
              )}
            </div>
            {parametros(f.config).length > 0 && (
              <div className="parametros">{parametros(f.config).map((p, i) => <code key={i}>{p}</code>)}</div>
            )}
            {f.ultima ? (
              <div className="fonte-ultima">
                <span className={`source-state ${f.ultima.status === 'ok' ? 'ok' : 'warn'}`}>{ROTULO_STATUS[f.ultima.status] ?? f.ultima.status}</span>
                <span>Última coleta {tempoRelativo(f.ultima.iniciada_em)}</span>
                <span>{f.ultima.coletadas} vistas · <b>{f.ultima.novas} novas</b> · {f.ultima.duplicadas} repetidas</span>
              </div>
            ) : f.implementada && <p className="dica">Nenhuma coleta ainda.</p>}
            {f.ultima?.erro && <p className="fonte-erro">{f.ultima.erro.slice(0, 240)}</p>}
            {f.implementada && dados.pode_alterar && (
              <button className="outline-button" disabled={!f.ativa || f.ultima?.status === 'rodando'} onClick={() => coletar(f)}>
                <Play size={14} /> {f.ultima?.status === 'rodando' ? 'Coletando…' : 'Coletar agora'}
              </button>
            )}
          </section>
        ))}
      </div>

      <section className="section-heading"><div><h2>Últimas execuções</h2><p>As 30 coletas mais recentes, de todas as fontes.</p></div></section>
      <div className="tabela-simples-rolagem">
        <table className="tabela-simples">
          <thead><tr><th>Fonte</th><th>Início</th><th>Duração</th><th>Vistas</th><th>Novas</th><th>Repetidas</th><th>Status</th></tr></thead>
          <tbody>
            {dados.execucoes.map((e) => (
              <tr key={e.id}>
                <td>{nomes[e.fonte_id] ?? e.fonte_id}</td>
                <td>{new Date(e.iniciada_em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</td>
                <td>{duracao(e)}</td><td>{e.coletadas}</td><td className={e.novas ? 'novas' : ''}>{e.novas ? `+${e.novas}` : 0}</td><td>{e.duplicadas}</td>
                <td><span className={`source-state ${e.status === 'ok' ? 'ok' : 'warn'}`} title={e.erro ?? ''}>{ROTULO_STATUS[e.status] ?? e.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Fontes e coleta"><Fontes /></AppShell>
}
