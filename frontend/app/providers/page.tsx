'use client'

import { useCallback, useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, CheckCircle2, Pencil, PlugZap, Plus, TriangleAlert } from 'lucide-react'
import { FormProvider } from '@/components/FormProvider'
import { AppShell, useUsuario } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'
import { tempoRelativo } from '@/lib/vagas'

type Uso = { requisicoes: number; tokens_entrada: number; tokens_saida: number; erros: number }
type Provider = {
  id: string; nome: string; tipo: string; modelo: string; base_url: string | null; chave: string | null
  prioridade: number; ativo: boolean; tamanho_lote: number; rpm: number | null; rpd: number | null; timeout_s: number
  ultimo_erro: string | null; ultimo_erro_em: string | null; hoje: Uso; ultimos_7_dias: { requisicoes: number; tokens: number; erros: number }
}
type Teste = { ok: boolean; segundos?: number; modelo?: string; erro?: string }

const milhar = (n: number) => n.toLocaleString('pt-BR')

function Providers() {
  const eu = useUsuario()
  const [lista, setLista] = useState<Provider[] | null>(null)
  const [testes, setTestes] = useState<Record<string, Teste | 'testando'>>({})
  const [toast, setToast] = useState('')
  const [adicionando, setAdicionando] = useState(false)
  const [editando, setEditando] = useState<string | null>(null)

  const carregar = useCallback(() => api<{ providers: Provider[] }>('/providers').then((r) => setLista(r.providers)), [])
  useEffect(() => { carregar() }, [carregar])

  function avisar(texto: string) {
    setToast(texto)
    window.setTimeout(() => setToast(''), 3500)
  }

  async function mover(indice: number, direcao: -1 | 1) {
    if (!lista) return
    const nova = [...lista]
    ;[nova[indice], nova[indice + direcao]] = [nova[indice + direcao], nova[indice]]
    setLista(nova)
    try {
      await api('/providers/ordem', { metodo: 'PUT', corpo: { ids: nova.map((p) => p.id) } })
      avisar('Ordem salva: a auditoria tenta nesta sequência.')
    } catch (e) { avisar(e instanceof ErroApi ? e.message : 'Erro') }
    carregar()
  }

  async function alternar(p: Provider) {
    try {
      await api(`/providers/${p.id}`, { metodo: 'PATCH', corpo: { ativo: !p.ativo } })
      avisar(p.ativo ? `${p.nome} desativado.` : `${p.nome} ativado.`)
      carregar()
    } catch (e) { avisar(e instanceof ErroApi ? e.message : 'Erro') }
  }

  async function testar(p: Provider) {
    setTestes((t) => ({ ...t, [p.id]: 'testando' }))
    try {
      const r = await api<Teste>(`/providers/${p.id}/testar`, { metodo: 'POST' })
      setTestes((t) => ({ ...t, [p.id]: r }))
    } catch (e) {
      setTestes((t) => ({ ...t, [p.id]: { ok: false, erro: e instanceof Error ? e.message : 'Erro' } }))
    }
  }

  if (!lista) return <div className="carregando-bloco">Carregando…</div>

  return (
    <>
      <section className="hero">
        <div><h1>Providers de IA</h1><p>Quem audita as vagas. Em caso de erro ou limite, a auditoria passa para o próximo da lista.</p></div>
        {!adicionando && <button className="outline-button" onClick={() => setAdicionando(true)}><Plus size={15} /> Adicionar provider</button>}
      </section>
      {adicionando && (
        <section className="panel bloco">
          <div className="panel-heading"><div><h3>Novo provider</h3><p>Qualquer API compatível com a da OpenAI (Groq, NVIDIA, Gemini, OpenRouter…). Entra no fim da fila.</p></div></div>
          <FormProvider aoCancelar={() => setAdicionando(false)} aoSalvar={(m) => { setAdicionando(false); avisar(m); carregar() }} />
        </section>
      )}
      {lista.length === 0 && <div className="jobs-table vazio">{eu?.papel === 'admin' ? 'Nenhum provider cadastrado.' : 'Você não tem providers próprios: suas vagas são auditadas pela cascata do admin. Cadastre um para usar a sua própria chave.'}</div>}
      <div className="lista-providers">
        {lista.map((p, i) => {
          const teste = testes[p.id]
          return (
            <section className={`panel provider ${p.ativo ? '' : 'fonte-off'}`} key={p.id}>
              <div className="provider-ordem">
                <span className="provider-posicao">{i + 1}</span>
                <button className="icon-button small" disabled={i === 0} onClick={() => mover(i, -1)} title="Subir"><ArrowUp size={15} /></button>
                <button className="icon-button small" disabled={i === lista.length - 1} onClick={() => mover(i, 1)} title="Descer"><ArrowDown size={15} /></button>
              </div>
              <div className="provider-corpo">
                <div className="fonte-topo">
                  <div className="fonte-nome"><strong>{p.nome}</strong><small><code>{p.modelo}</code> · {p.tipo === 'cli' ? 'CLI local' : p.base_url}</small></div>
                  <label className="interruptor"><input type="checkbox" checked={p.ativo} onChange={() => alternar(p)} /><span>{p.ativo ? 'Ativo' : 'Desativado'}</span></label>
                </div>
                <div className="provider-numeros">
                  <div><span>Chave</span><strong>{p.chave ?? '—'}</strong></div>
                  <div><span>Hoje</span><strong>{milhar(p.hoje.requisicoes)} req</strong><small>{milhar(p.hoje.tokens_entrada + p.hoje.tokens_saida)} tokens{p.hoje.erros ? ` · ${p.hoje.erros} erros` : ''}</small></div>
                  <div><span>7 dias</span><strong>{milhar(p.ultimos_7_dias.requisicoes)} req</strong><small>{milhar(p.ultimos_7_dias.tokens)} tokens</small></div>
                  <div><span>Limites</span><strong>{p.rpm ?? '—'} rpm · {p.rpd ?? '—'} rpd</strong><small>lote de {p.tamanho_lote} · timeout {p.timeout_s} s</small></div>
                </div>
                {p.ultimo_erro && <p className="fonte-erro"><TriangleAlert size={14} /> {tempoRelativo(p.ultimo_erro_em)}: {p.ultimo_erro.slice(0, 240)}</p>}
                <div className="acoes-linha">
                  <button className="outline-button" disabled={teste === 'testando'} onClick={() => testar(p)}><PlugZap size={14} /> {teste === 'testando' ? 'Testando…' : 'Testar conexão'}</button>
                  {p.tipo !== 'cli' && editando !== p.id && <button className="outline-button" onClick={() => setEditando(p.id)}><Pencil size={14} /> Editar</button>}
                  {teste && teste !== 'testando' && (
                    <span className={teste.ok ? 'teste-ok' : 'teste-erro'}>{teste.ok ? `OK em ${teste.segundos} s (${teste.modelo})` : teste.erro}</span>
                  )}
                </div>
                {editando === p.id && (
                  <FormProvider inicial={{ ...p, base_url: p.base_url ?? "" }} aoCancelar={() => setEditando(null)} aoSalvar={(m) => { setEditando(null); avisar(m); carregar() }} />
                )}
              </div>
            </section>
          )
        })}
      </div>
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Providers de IA"><Providers /></AppShell>
}
