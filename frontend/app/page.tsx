'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, BriefcaseBusiness, CheckCircle2, Clock3, Send, ThumbsDown, TriangleAlert, RefreshCw } from 'lucide-react'
import { AppShell } from '@/components/AppShell'
import { PainelVaga, TabelaVagas } from '@/components/Vagas'
import { api } from '@/lib/api'
import { type ListaVagas, type Resumo, tempoRelativo } from '@/lib/vagas'

const ICONE_ATIVIDADE = { recomendada: Send, confirmada: CheckCircle2, ignorada: ThumbsDown } as const
const TEXTO_ATIVIDADE: Record<string, string> = { recomendada: 'Recomendada pela IA', confirmada: 'Você confirmou', ignorada: 'Você ignorou' }

function VisaoGeral() {
  const [resumo, setResumo] = useState<Resumo | null>(null)
  const [recomendadas, setRecomendadas] = useState<ListaVagas | null>(null)
  const [aberta, setAberta] = useState<string | null>(null)
  const [toast, setToast] = useState('')

  const carregar = useCallback(() => {
    api<Resumo>('/resumo').then(setResumo)
    api<ListaVagas>('/vagas?status=recomendada').then(setRecomendadas)
  }, [])
  useEffect(carregar, [carregar])
  const fechar = useCallback(() => setAberta(null), [])

  function aoDecidir(_id: string, _status: string, mensagem: string) {
    setToast(mensagem)
    window.setTimeout(() => setToast(''), 3500)
    carregar()
  }

  if (!resumo || !recomendadas) return <div className="carregando-bloco">Carregando…</div>
  const c = resumo.contagens
  const ultimaColeta = resumo.fontes.map((f) => f.iniciada_em).filter(Boolean).sort().at(-1) ?? null

  const totalFunil = c.recomendada + c.fila + c.pool + c.confirmada

  return (
    <>
      <section className="hero">
        <div>
          <h1>Visão geral</h1>
          <p>Acompanhe suas oportunidades, a auditoria por IA e as últimas coletas.</p>
        </div>
        <button className="outline-button" onClick={carregar}><RefreshCw size={15} /> Atualizar</button>
      </section>

      <section className="notice">
        <TriangleAlert size={22} />
        <div><strong>{c.recomendada ? `${c.recomendada} vaga(s) recomendada(s) aguardando sua decisão` : 'Sua triagem está em dia'}</strong><p>{c.fila} na fila da IA · {c.pool} no pool · última coleta {tempoRelativo(ultimaColeta)}</p></div>
        <Link className="outline-button" href="/vagas/">Ir para triagem <ArrowUpRight size={15} /></Link>
      </section>

      <section className="stats-grid">
        <div className="stat-card"><div className="stat-icon blue"><Send size={18} /></div><div className="stat-label">Aguardando você</div><strong>{c.recomendada}<small className="de"> / {resumo.limites.recomendadas}</small></strong><small>recomendadas pela IA</small></div>
        <div className="stat-card"><div className="stat-icon green"><CheckCircle2 size={18} /></div><div className="stat-label">Recomendadas hoje</div><strong>{resumo.recomendadas_hoje}</strong><small>{c.confirmada} confirmada(s) no total</small></div>
        <div className="stat-card"><div className="stat-icon orange"><Clock3 size={18} /></div><div className="stat-label">Na fila da IA</div><strong>{c.fila}<small className="de"> / {resumo.limites.fila}</small></strong><small>{c.pool} no pool aguardando vaga na fila</small></div>
        <div className="stat-card"><div className="stat-icon purple"><BriefcaseBusiness size={18} /></div><div className="stat-label">Vagas novas hoje</div><strong>{resumo.vagas_novas_hoje}</strong><small>coletadas de {resumo.fontes.length} fonte(s)</small></div>
      </section>

      <section className="dashboard-grid">
        <div className="panel">
          <div className="panel-heading"><div><h3>Saúde das fontes</h3><p>Última coleta de cada fonte</p></div></div>
          <div className="source-list">
            {resumo.fontes.map((f) => (
              <div className="source-item" key={f.id}>
                <div className="source-badge gupy">{f.nome.slice(0, 1)}</div>
                <div className="source-name"><strong>{f.nome}</strong><small>{tempoRelativo(f.iniciada_em)}</small></div>
                <span className="source-count">{f.coletadas ?? 0} vistas · {f.novas ?? 0} novas</span>
                <span className={`source-state ${f.status === 'ok' ? 'ok' : 'warn'}`} title={f.erro ?? ''}>{f.status === 'ok' ? 'Operacional' : f.status ? 'Atenção' : 'Sem coleta'}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-heading"><div><h3>Distribuição do funil</h3><p>Situação atual das suas oportunidades</p></div></div>
          <div className="funnel-bar" aria-hidden="true">
            <span style={{ width: `${totalFunil ? c.recomendada / totalFunil * 100 : 0}%` }} />
            <span style={{ width: `${totalFunil ? c.fila / totalFunil * 100 : 0}%` }} />
            <span style={{ width: `${totalFunil ? c.confirmada / totalFunil * 100 : 0}%` }} />
            <span style={{ width: `${totalFunil ? c.pool / totalFunil * 100 : 0}%` }} />
          </div>
          <div className="funnel-list">
            <Link href="/vagas/?status=recomendada"><i />Recomendadas<strong>{c.recomendada}</strong></Link>
            <Link href="/vagas/?status=fila"><i />Na fila da IA<strong>{c.fila}</strong></Link>
            <Link href="/vagas/?status=confirmada"><i />Confirmadas<strong>{c.confirmada}</strong></Link>
            <Link href="/vagas/?status=pool"><i />No pool<strong>{c.pool}</strong></Link>
          </div>
        </div>
      </section>

      <section className="section-heading">
        <div><h2>Recomendadas</h2><p>Auditadas pela IA, da maior para a menor nota. Clique para ver o parecer.</p></div>
        <Link className="text-button" href="/vagas/">Ver todas as vagas <ArrowUpRight size={15} /></Link>
      </section>
      <TabelaVagas itens={recomendadas.itens.slice(0, 8)} motivos={resumo.motivos_ignorar} aoAbrir={setAberta} aoDecidir={aoDecidir}
        vazio="Nenhuma vaga recomendada agora. Novas coletas rodam de hora em hora, das 8h às 20h." />

      <section className="activity-panel-wrap">
        <div className="panel activity-panel">
          <div className="panel-heading"><div><h3>Atividade recente</h3><p>Recomendações e decisões</p></div></div>
          <div className="activity-list">
            {resumo.atividade.length === 0 && <p className="dica">Nada por aqui ainda.</p>}
            {resumo.atividade.map((a, i) => {
              const Icone = ICONE_ATIVIDADE[a.para as keyof typeof ICONE_ATIVIDADE] ?? Send
              return (
                <button className="activity-item" key={i} onClick={() => setAberta(a.vaga_id)}>
                  <div className={`activity-symbol ${a.para === 'ignorada' ? 'purple' : 'green'}`}><Icone size={15} /></div>
                  <div><strong>{a.titulo}</strong><p>{TEXTO_ATIVIDADE[a.para] ?? a.para}{a.origem === 'usuario' && a.detalhe ? ` (${a.detalhe})` : ''}</p></div>
                  <time>{tempoRelativo(a.em)}</time>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {aberta && <PainelVaga id={aberta} motivos={resumo.motivos_ignorar} aoFechar={fechar} aoDecidir={aoDecidir} />}
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Visão geral"><VisaoGeral /></AppShell>
}
