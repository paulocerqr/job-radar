'use client'

import { useEffect, useState } from 'react'
import {
  AlertTriangle, Check, CheckCircle2, CircleSlash, ExternalLink, Sparkles, ThumbsDown, X, XCircle,
} from 'lucide-react'
import { api, ErroApi } from '@/lib/api'
import {
  type DetalheVaga, type ItemVaga, local, ROTULO_STATUS, rotuloModalidade, tempoRelativo,
} from '@/lib/vagas'

export function Nota({ valor, titulo }: { valor: number | null; titulo?: string }) {
  if (valor === null) return <span className="score score-none" title={titulo}>—</span>
  const nivel = valor >= 80 ? 'high' : valor >= 60 ? 'medium' : 'low'
  return <span className={`score score-${nivel}`} title={titulo}><Sparkles size={13} /> {valor}</span>
}

/** Botões de decisão (só para recomendadas). Ignorar abre a escolha opcional do motivo. */
export function Decisao({ vaga, motivos, aoDecidir, compacto = false }: {
  vaga: ItemVaga; motivos: Record<string, string>; aoDecidir: (status: string, mensagem: string) => void; compacto?: boolean
}) {
  const [escolhendo, setEscolhendo] = useState(false)
  const [enviando, setEnviando] = useState(false)
  if (vaga.status !== 'recomendada') return null

  async function decidir(acao: 'confirmar' | 'ignorar', motivo?: string) {
    setEnviando(true)
    try {
      const r = await api<{ status: string }>(`/vagas/${vaga.id}/${acao}`, { metodo: 'POST', corpo: motivo ? { motivo } : {} })
      aoDecidir(r.status, acao === 'confirmar' ? 'Vaga confirmada. Boa sorte na candidatura!' : 'Vaga ignorada.')
    } catch (e) {
      aoDecidir(vaga.status, e instanceof ErroApi ? e.message : 'Erro ao registrar a decisão')
    } finally {
      setEnviando(false)
      setEscolhendo(false)
    }
  }

  if (escolhendo) {
    return (
      <div className="motivos" onClick={(e) => e.stopPropagation()}>
        <span>Motivo (opcional):</span>
        {Object.entries(motivos).map(([codigo, rotulo]) => (
          <button key={codigo} className="chip" disabled={enviando} onClick={() => decidir('ignorar', codigo)}>{rotulo}</button>
        ))}
        <button className="chip" disabled={enviando} onClick={() => decidir('ignorar')}>sem motivo</button>
        <button className="icon-button small" onClick={() => setEscolhendo(false)} title="Cancelar"><X size={15} /></button>
      </div>
    )
  }
  return (
    <div className={`decisao ${compacto ? 'decisao-compacta' : ''}`} onClick={(e) => e.stopPropagation()}>
      <button className={compacto ? 'icon-button small success-action' : 'botao-sucesso'} disabled={enviando} onClick={() => decidir('confirmar')} title="Vou aplicar">
        <Check size={16} />{!compacto && ' Vou aplicar'}
      </button>
      <button className={compacto ? 'icon-button small danger-action' : 'botao-neutro'} disabled={enviando} onClick={() => setEscolhendo(true)} title="Ignorar">
        <ThumbsDown size={15} />{!compacto && ' Ignorar'}
      </button>
    </div>
  )
}

export function TabelaVagas({ itens, motivos, aoAbrir, aoDecidir, vazio }: {
  itens: ItemVaga[]; motivos: Record<string, string>; aoAbrir: (id: string) => void
  aoDecidir: (id: string, status: string, mensagem: string) => void; vazio: string
}) {
  if (itens.length === 0) return <div className="jobs-table vazio">{vazio}</div>
  return (
    <div className="jobs-table">
      <div className="table-header"><span>OPORTUNIDADE</span><span>LOCALIZAÇÃO</span><span>FONTE</span><span>PUBLICADA</span><span>NOTA IA</span><span /></div>
      {itens.map((v) => (
        <div className="job-row clicavel" key={v.id} onClick={() => aoAbrir(v.id)} role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter') aoAbrir(v.id) }}>
          <div className="job-main">
            <div className="company-logo violet">{(v.empresa ?? v.titulo).slice(0, 1).toUpperCase()}</div>
            <div><strong title={v.titulo}>{v.titulo}</strong><p>{v.empresa ?? 'Empresa não informada'}{v.resumo && <><span> · </span>{v.resumo}</>}</p></div>
          </div>
          <div className="job-location"><span>{local(v)}</span><small className={v.modalidade === 'remoto' ? 'remote' : ''}>{rotuloModalidade(v.modalidade)}</small></div>
          <div className="job-source"><span>{v.fontes.join(', ') || '—'}</span></div>
          <div className="job-posted">{tempoRelativo(v.publicada_em)}</div>
          <div><Nota valor={v.score_ia} titulo={`Pré-filtro: ${v.score_prefiltro}`} /></div>
          <div className="row-actions">
            <a className="icon-button small" href={v.url} target="_blank" rel="noopener noreferrer" title="Abrir vaga original" onClick={(e) => e.stopPropagation()}><ExternalLink size={15} /></a>
            <Decisao vaga={v} motivos={motivos} compacto aoDecidir={(s, m) => aoDecidir(v.id, s, m)} />
          </div>
        </div>
      ))}
    </div>
  )
}

function Lista({ titulo, itens, Icone, tom }: { titulo: string; itens?: string[]; Icone: typeof CheckCircle2; tom: string }) {
  if (!itens || itens.length === 0) return null
  return (
    <div className={`lista-parecer ${tom}`}>
      <h4><Icone size={15} /> {titulo}</h4>
      <ul>{itens.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </div>
  )
}

const ROTULO_TRANSICAO: Record<string, string> = {
  pool: 'Entrou no pool (pré-filtro)', fila: 'Foi para a fila da IA', recomendada: 'Recomendada pela IA',
  descartada: 'Descartada pela IA', confirmada: 'Confirmada por você', ignorada: 'Ignorada por você',
  expirada: 'Expirou', erro: 'Erro na auditoria',
}

/** Painel lateral com o parecer da IA, a descrição e o histórico da vaga. */
export function PainelVaga({ id, motivos, aoFechar, aoDecidir }: {
  id: string; motivos: Record<string, string>; aoFechar: () => void; aoDecidir: (id: string, status: string, mensagem: string) => void
}) {
  const [vaga, setVaga] = useState<DetalheVaga | null>(null)
  const [descricaoAberta, setDescricaoAberta] = useState(false)

  useEffect(() => {
    setVaga(null)
    api<DetalheVaga>(`/vagas/${id}`).then(setVaga).catch(() => aoFechar())
    const fechar = (e: KeyboardEvent) => { if (e.key === 'Escape') aoFechar() }
    window.addEventListener('keydown', fechar)
    return () => window.removeEventListener('keydown', fechar)
  }, [id, aoFechar])

  const r = vaga?.auditoria?.resultado ?? {}
  return (
    <div className="painel-fundo" onClick={aoFechar}>
      <aside className="painel" onClick={(e) => e.stopPropagation()} aria-label="Detalhe da vaga">
        <button className="icon-button painel-fechar" onClick={aoFechar} title="Fechar (Esc)"><X size={18} /></button>
        {!vaga ? <div className="carregando-bloco">Carregando…</div> : (
          <>
            <div className="painel-topo">
              <span className={`status-tag status-${vaga.status}`}>{ROTULO_STATUS[vaga.status]}</span>
              <h2>{vaga.titulo}</h2>
              <p>{vaga.empresa ?? 'Empresa não informada'} · {local(vaga)} · {rotuloModalidade(vaga.modalidade)}</p>
              <p className="painel-meta">{vaga.fontes.join(', ')} · publicada {tempoRelativo(vaga.publicada_em)}</p>
            </div>
            <div className="painel-notas">
              <div><span>Nota da IA</span><Nota valor={vaga.score_ia} /></div>
              <div><span>Pré-filtro</span><strong>{vaga.score_prefiltro}</strong></div>
              {r.area && <div><span>Área</span><strong>{r.area}</strong></div>}
            </div>
            <div className="painel-acoes">
              <Decisao vaga={vaga} motivos={motivos} aoDecidir={(s, m) => { aoDecidir(vaga.id, s, m); setVaga({ ...vaga, status: s as DetalheVaga['status'] }) }} />
              <a className="outline-button" href={vaga.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} /> Abrir vaga original</a>
            </div>
            {vaga.motivo_usuario && <p className="dica">Motivo registrado: {motivos[vaga.motivo_usuario] ?? vaga.motivo_usuario}</p>}

            {vaga.auditoria ? (
              <section className="painel-secao">
                <h3>Parecer da IA</h3>
                {r.resumo && <p className="parecer">{r.resumo}</p>}
                {r.motivo_descarte && <p className="parecer-descarte"><XCircle size={15} /> {r.motivo_descarte}</p>}
                <div className="compatibilidade">
                  {r.nivel_compativel !== undefined && <span className={r.nivel_compativel ? 'ok' : 'nao'}>{r.nivel_compativel ? <Check size={13} /> : <CircleSlash size={13} />} nível</span>}
                  {r.modalidade_compativel !== undefined && <span className={r.modalidade_compativel ? 'ok' : 'nao'}>{r.modalidade_compativel ? <Check size={13} /> : <CircleSlash size={13} />} modalidade e local</span>}
                </div>
                <Lista titulo="Requisitos atendidos" itens={r.requisitos_atendidos} Icone={CheckCircle2} tom="tom-ok" />
                <Lista titulo="Gaps" itens={r.gaps} Icone={AlertTriangle} tom="tom-alerta" />
                <Lista titulo="Red flags" itens={r.red_flags} Icone={XCircle} tom="tom-erro" />
                <p className="painel-meta">Auditada {tempoRelativo(vaga.auditoria.em)} · {vaga.auditoria.modelo}</p>
              </section>
            ) : <p className="dica">Ainda não auditada pela IA.</p>}

            {vaga.descricao && (
              <section className="painel-secao">
                <h3>Descrição</h3>
                <div className={`descricao ${descricaoAberta ? 'aberta' : ''}`}>{vaga.descricao}</div>
                <button className="text-button" onClick={() => setDescricaoAberta(!descricaoAberta)}>{descricaoAberta ? 'Mostrar menos' : 'Mostrar tudo'}</button>
              </section>
            )}

            <section className="painel-secao">
              <h3>Histórico</h3>
              <ol className="linha-tempo">
                {vaga.historico.map((h, i) => (
                  <li key={i}><strong>{ROTULO_TRANSICAO[h.para] ?? h.para}</strong>{h.detalhe && <span> · {h.detalhe}</span>}<time>{new Date(h.em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</time></li>
                ))}
              </ol>
            </section>
          </>
        )}
      </aside>
    </div>
  )
}
