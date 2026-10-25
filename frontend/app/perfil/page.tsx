'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2, FlaskConical, Info, Save } from 'lucide-react'
import { AppShell } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'

type Perfil = {
  palavras_chave: string[]
  palavras_excluidas: string[]
  niveis: string[]
  aceita_remoto: boolean
  localidades: string[]
  score_minimo: number
  ttl_pool_dias: number
  ttl_recomendada_dias: number
  curriculo_md: string
  instrucoes_ia: string
}
type Limites = { niveis: string[]; curriculo: number; instrucoes: number }
type Simulacao = { avaliadas: number; aprovadas: number; para_fila: number; exemplos: { nota: number; titulo: string }[] }

// listas editadas como texto, um item por linha
type Formulario = Omit<Perfil, 'palavras_chave' | 'palavras_excluidas' | 'localidades'> & {
  palavras_chave: string
  palavras_excluidas: string
  localidades: string
}

const ROTULO_NIVEL: Record<string, string> = { estagio: 'Estágio', trainee: 'Trainee', junior: 'Júnior', pleno: 'Pleno', senior: 'Sênior' }

const paraFormulario = (p: Perfil): Formulario => ({
  ...p,
  palavras_chave: p.palavras_chave.join('\n'),
  palavras_excluidas: p.palavras_excluidas.join('\n'),
  localidades: p.localidades.join('\n'),
})
const linhas = (texto: string) => texto.split(/[\n,;]/).map((t) => t.trim()).filter(Boolean)
const paraApi = (f: Formulario): Perfil => ({
  ...f,
  palavras_chave: linhas(f.palavras_chave),
  palavras_excluidas: linhas(f.palavras_excluidas),
  localidades: f.localidades.split('\n').map((t) => t.trim()).filter(Boolean),
})

function ErroCampo({ erros, campo }: { erros: Record<string, string>; campo: string }) {
  return erros[campo] ? <span className="erro-campo">{erros[campo]}</span> : null
}

function MeuPerfil() {
  const [form, setForm] = useState<Formulario | null>(null)
  const [limites, setLimites] = useState<Limites | null>(null)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [simulacao, setSimulacao] = useState<{ atual: Simulacao; nova: Simulacao } | null>(null)
  const [simulando, setSimulando] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [recalcular, setRecalcular] = useState(true)
  const [toast, setToast] = useState('')

  useEffect(() => {
    api<{ perfil: Perfil; limites: Limites }>('/perfil').then(({ perfil, limites }) => {
      setForm(paraFormulario(perfil))
      setLimites(limites)
    })
  }, [])

  if (!form || !limites) return <div className="carregando-bloco">Carregando perfil…</div>

  const mudar = <K extends keyof Formulario>(campo: K, valor: Formulario[K]) => setForm({ ...form, [campo]: valor })
  const alternarNivel = (nivel: string) =>
    mudar('niveis', form.niveis.includes(nivel) ? form.niveis.filter((n) => n !== nivel) : [...form.niveis, nivel])

  function avisar(texto: string) {
    setToast(texto)
    window.setTimeout(() => setToast(''), 4000)
  }

  function tratarErro(e: unknown) {
    if (e instanceof ErroApi && e.status === 422) setErros(e.corpo.erros as Record<string, string>)
    else avisar(e instanceof Error ? e.message : 'Erro inesperado')
  }

  async function simular() {
    setSimulando(true)
    setErros({})
    try {
      setSimulacao(await api('/perfil/simular', { metodo: 'POST', corpo: paraApi(form!) }))
    } catch (e) {
      tratarErro(e)
    } finally {
      setSimulando(false)
    }
  }

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    try {
      const r = await api<{ perfil: Perfil; recalculadas: number | null }>(
        `/perfil${recalcular ? '?recalcular=true' : ''}`, { metodo: 'PUT', corpo: paraApi(form!) },
      )
      setForm(paraFormulario(r.perfil))
      avisar(r.recalculadas === null ? 'Perfil salvo.' : `Perfil salvo. ${r.recalculadas} vaga(s) do pool mudaram de nota; as aprovadas vão para a fila em até 10 min.`)
    } catch (e) {
      tratarErro(e)
    } finally {
      setSalvando(false)
    }
  }

  const temErros = Object.keys(erros).length > 0

  return (
    <form onSubmit={salvar}>
      <section className="hero">
        <div>
          <h1>Meu perfil</h1>
          <p>O que o pré-filtro usa para escolher as vagas que vão para a IA, e o que a IA usa para dar a nota.</p>
        </div>
      </section>

      {temErros && <p className="alerta alerta-erro" role="alert">Há campos com erro; nada foi salvo.</p>}

      <section className="panel bloco">
        <div className="panel-heading"><div><h3>Pré-filtro</h3><p>Regras aplicadas na coleta, sem IA.</p></div></div>
        <p className="dica"><Info size={15} /><span>Sem palavra-chave no <b>título</b>, a nota máxima é 43 e a vaga não chega à IA (mínimo 50). Prefira palavras de área (“suporte”, “dados”) às de stack, que quase nunca aparecem em títulos de estágio.</span></p>
        <div className="grade-2">
          <label className="campo">Palavras-chave <small>uma por linha</small>
            <textarea rows={12} spellCheck={false} value={form.palavras_chave} onChange={(e) => mudar('palavras_chave', e.target.value)} />
            <ErroCampo erros={erros} campo="palavras_chave" />
          </label>
          <label className="campo">Palavras excluídas <small>no título, reprovam a vaga</small>
            <textarea rows={12} spellCheck={false} value={form.palavras_excluidas} onChange={(e) => mudar('palavras_excluidas', e.target.value)} />
          </label>
        </div>
        <fieldset className="campo">
          <legend>Níveis aceitos</legend>
          <div className="opcoes">
            {limites.niveis.map((nivel) => (
              <label key={nivel} className={`chip ${form.niveis.includes(nivel) ? 'chip-on' : ''}`}>
                <input type="checkbox" checked={form.niveis.includes(nivel)} onChange={() => alternarNivel(nivel)} /> {ROTULO_NIVEL[nivel] ?? nivel}
              </label>
            ))}
          </div>
          <ErroCampo erros={erros} campo="niveis" />
        </fieldset>
        <div className="grade-2">
          <label className="campo">Localidades presenciais/híbridas <small>Cidade/UF, uma por linha</small>
            <textarea rows={3} spellCheck={false} value={form.localidades} onChange={(e) => mudar('localidades', e.target.value)} />
            <ErroCampo erros={erros} campo="localidades" />
          </label>
          <label className="interruptor">
            <input type="checkbox" checked={form.aceita_remoto} onChange={(e) => mudar('aceita_remoto', e.target.checked)} />
            <span>Aceito vagas remotas de qualquer lugar</span>
          </label>
        </div>
        <div className="acoes-linha">
          <button type="button" className="outline-button" onClick={simular} disabled={simulando}><FlaskConical size={15} /> {simulando ? 'Calculando…' : 'Simular com as vagas do banco'}</button>
        </div>
        {simulacao && (
          <div className="simulacao">
            <div className="sim-numeros">
              <div className="sim-numero"><span>Vagas ativas no banco</span><strong>{simulacao.nova.avaliadas}</strong></div>
              <div className="sim-numero"><span>Passam no pré-filtro</span><strong>{simulacao.nova.aprovadas}</strong><small>hoje: {simulacao.atual.aprovadas}</small></div>
              <div className="sim-numero sim-destaque"><span>Iriam para a IA (nota ≥ 50)</span><strong>{simulacao.nova.para_fila}</strong><small>hoje: {simulacao.atual.para_fila}</small></div>
            </div>
            {simulacao.nova.exemplos.length > 0 && (
              <ol className="sim-exemplos">{simulacao.nova.exemplos.map((ex, i) => <li key={i}><span className="score score-high">{ex.nota}</span> {ex.titulo}</li>)}</ol>
            )}
            <p className="dica">Simulação sobre as vagas já coletadas; nada foi salvo. A IA ainda decide quais são recomendadas.</p>
          </div>
        )}
      </section>

      <section className="panel bloco">
        <div className="panel-heading"><div><h3>Auditoria pela IA</h3><p>Critérios usados para recomendar.</p></div></div>
        <div className="grade-3">
          <label className="campo">Nota mínima para recomendar
            <input type="number" min={0} max={100} value={form.score_minimo} onChange={(e) => mudar('score_minimo', Number(e.target.value))} />
            <ErroCampo erros={erros} campo="score_minimo" />
          </label>
          <label className="campo">Dias no pool antes de expirar
            <input type="number" min={1} max={60} value={form.ttl_pool_dias} onChange={(e) => mudar('ttl_pool_dias', Number(e.target.value))} />
            <ErroCampo erros={erros} campo="ttl_pool_dias" />
          </label>
          <label className="campo">Dias como recomendada
            <input type="number" min={1} max={60} value={form.ttl_recomendada_dias} onChange={(e) => mudar('ttl_recomendada_dias', Number(e.target.value))} />
            <ErroCampo erros={erros} campo="ttl_recomendada_dias" />
          </label>
        </div>
        <label className="campo">Instruções para a IA <small>prevalecem sobre os critérios padrão · {form.instrucoes_ia.length}/{limites.instrucoes}</small>
          <textarea rows={4} maxLength={limites.instrucoes} value={form.instrucoes_ia} onChange={(e) => mudar('instrucoes_ia', e.target.value)}
            placeholder="Ex.: aceito vagas remotas que pedem idas esporádicas a outra cidade (eventos, integração); descarte só presença frequente fora do DF." />
          <ErroCampo erros={erros} campo="instrucoes_ia" />
        </label>
        <label className="campo">Currículo <small>Markdown; a IA compara os requisitos da vaga com este texto · {form.curriculo_md.length}/{limites.curriculo}</small>
          <textarea rows={16} className="mono" maxLength={limites.curriculo} value={form.curriculo_md} onChange={(e) => mudar('curriculo_md', e.target.value)} />
          <ErroCampo erros={erros} campo="curriculo_md" />
        </label>
      </section>

      <div className="barra-salvar">
        <label className="interruptor">
          <input type="checkbox" checked={recalcular} onChange={(e) => setRecalcular(e.target.checked)} />
          <span>Recalcular as notas do pool com as regras novas</span>
        </label>
        <button type="submit" className="botao-primario" disabled={salvando}><Save size={16} /> {salvando ? 'Salvando…' : 'Salvar'}</button>
      </div>
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </form>
  )
}

export default function Page() {
  return <AppShell titulo="Meu perfil"><MeuPerfil /></AppShell>
}
