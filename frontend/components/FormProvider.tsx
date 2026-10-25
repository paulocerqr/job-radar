'use client'

import { useEffect, useState } from 'react'
import { ListChecks, Save, Trash2, X } from 'lucide-react'
import { api, ErroApi } from '@/lib/api'

export type Preset = { base_url: string; modelo: string; rpm: number | null; rpd: number | null; tamanho_lote: number; timeout_s: number }
export type DadosProvider = { id?: string; nome: string; base_url: string; modelo: string; rpm: number | null; rpd: number | null; tamanho_lote: number; timeout_s: number }

const ROTULO_PRESET: Record<string, string> = { groq: 'Groq', nvidia: 'NVIDIA', gemini: 'Google Gemini' }
const vazio: DadosProvider = { nome: '', base_url: '', modelo: '', rpm: null, rpd: null, tamanho_lote: 5, timeout_s: 120 }

/** Cadastro (sem `inicial`) ou edição de um provider openai_compatible. */
export function FormProvider({ inicial, aoSalvar, aoCancelar }: {
  inicial?: DadosProvider; aoSalvar: (mensagem: string) => void; aoCancelar: () => void
}) {
  const editando = Boolean(inicial?.id)
  const [presets, setPresets] = useState<Record<string, Preset>>({})
  const [preset, setPreset] = useState('')
  const [form, setForm] = useState<DadosProvider>(inicial ?? vazio)
  const [chave, setChave] = useState('')
  const [modelos, setModelos] = useState<string[]>([])
  const [erros, setErros] = useState<Record<string, string>>({})
  const [aviso, setAviso] = useState('')
  const [salvando, setSalvando] = useState(false)

  useEffect(() => { if (!editando) api<{ presets: Record<string, Preset> }>('/providers/presets').then((r) => setPresets(r.presets)) }, [editando])

  const mudar = <K extends keyof DadosProvider>(campo: K, valor: DadosProvider[K]) => setForm({ ...form, [campo]: valor })
  const numero = (texto: string) => (texto === '' ? null : Number(texto))

  function escolherPreset(nome: string) {
    setPreset(nome)
    setErros({})
    const p = presets[nome]
    if (p) setForm({ ...form, ...p, nome: form.nome || nome })
  }

  async function carregarModelos() {
    setAviso('')
    try {
      const r = await api<{ modelos: string[] }>(`/providers/${inicial!.id}/modelos`)
      setModelos(r.modelos)
      setAviso(`${r.modelos.length} modelos disponíveis para esta chave.`)
    } catch (e) { setAviso(e instanceof ErroApi ? e.message : 'Erro ao listar modelos') }
  }

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault()
    setErros({})
    setSalvando(true)
    const corpo: Record<string, unknown> = { base_url: form.base_url, modelo: form.modelo, rpm: form.rpm, rpd: form.rpd, tamanho_lote: form.tamanho_lote, timeout_s: form.timeout_s }
    if (!editando) corpo.nome = form.nome
    if (chave) corpo.api_key = chave
    try {
      if (editando) await api(`/providers/${inicial!.id}`, { metodo: 'PATCH', corpo })
      else await api('/providers', { metodo: 'POST', corpo })
      setChave('')
      aoSalvar(editando ? 'Provider atualizado.' : `${form.nome} cadastrado no fim da fila. Use "Testar conexão" para conferir.`)
    } catch (e) {
      if (e instanceof ErroApi && e.status === 422) setErros(e.corpo.erros as Record<string, string>)
      else setAviso(e instanceof ErroApi ? e.message : 'Erro ao salvar')
    } finally { setSalvando(false) }
  }

  async function remover() {
    if (!window.confirm(`Remover o provider ${inicial!.nome}? A chave salva é apagada.`)) return
    try {
      await api(`/providers/${inicial!.id}`, { metodo: 'DELETE' })
      aoSalvar(`${inicial!.nome} removido.`)
    } catch (e) { setAviso(e instanceof ErroApi ? e.message : 'Erro ao remover') }
  }

  const erro = (campo: string) => (erros[campo] ? <span className="erro-campo">{erros[campo]}</span> : null)

  return (
    <form className="form-provider" onSubmit={salvar} autoComplete="off">
      {!editando && Object.keys(presets).length > 0 && (
        <fieldset className="campo">
          <legend>Começar de</legend>
          <div className="opcoes">
            {Object.keys(presets).map((nome) => (
              <button type="button" key={nome} className={`chip ${preset === nome ? 'chip-on' : ''}`} onClick={() => escolherPreset(nome)}>{ROTULO_PRESET[nome] ?? nome}</button>
            ))}
            <button type="button" className={`chip ${preset === '' ? 'chip-on' : ''}`} onClick={() => { setPreset(''); setErros({}); setForm({ ...vazio, nome: form.nome }) }}>Outro (compatível com OpenAI)</button>
          </div>
        </fieldset>
      )}
      <div className="grade-2">
        {!editando && <label className="campo">Nome<input value={form.nome} onChange={(e) => mudar('nome', e.target.value)} maxLength={40} required placeholder="ex.: groq-pessoal" />{erro('nome')}</label>}
        <label className="campo">URL da API <small>termina em /v1, por exemplo</small><input value={form.base_url} onChange={(e) => mudar('base_url', e.target.value)} required placeholder="https://api.exemplo.com/v1" />{erro('base_url')}</label>
        <label className="campo">Modelo
          <input value={form.modelo} onChange={(e) => mudar('modelo', e.target.value)} required list="modelos-disponiveis" />
          <datalist id="modelos-disponiveis">{modelos.map((m) => <option key={m} value={m} />)}</datalist>
          {erro('modelo')}
        </label>
        <label className="campo">{editando ? 'Nova chave de API' : 'Chave de API'} <small>{editando ? 'deixe vazio para manter a atual' : 'cifrada no servidor; não volta para o navegador'}</small>
          <input type="password" value={chave} onChange={(e) => setChave(e.target.value)} required={!editando} autoComplete="new-password" spellCheck={false} />
          {erro('api_key')}
        </label>
      </div>
      <div className="grade-4">
        <label className="campo">Req./minuto<input type="number" min={1} value={form.rpm ?? ''} onChange={(e) => mudar('rpm', numero(e.target.value))} placeholder="sem limite" />{erro('rpm')}</label>
        <label className="campo">Req./dia<input type="number" min={1} value={form.rpd ?? ''} onChange={(e) => mudar('rpd', numero(e.target.value))} placeholder="sem limite" />{erro('rpd')}</label>
        <label className="campo">Vagas por chamada<input type="number" min={1} max={20} value={form.tamanho_lote} onChange={(e) => mudar('tamanho_lote', Number(e.target.value))} />{erro('tamanho_lote')}</label>
        <label className="campo">Timeout (s)<input type="number" min={10} max={600} value={form.timeout_s} onChange={(e) => mudar('timeout_s', Number(e.target.value))} />{erro('timeout_s')}</label>
      </div>
      {aviso && <p className="dica">{aviso}</p>}
      <div className="acoes-linha">
        <button type="submit" className="botao-primario" disabled={salvando}><Save size={15} /> {salvando ? 'Salvando…' : editando ? 'Salvar' : 'Cadastrar'}</button>
        {editando && <button type="button" className="outline-button" onClick={carregarModelos}><ListChecks size={14} /> Carregar modelos</button>}
        <button type="button" className="botao-neutro" onClick={aoCancelar}><X size={15} /> Cancelar</button>
        {editando && <button type="button" className="botao-neutro perigo" onClick={remover}><Trash2 size={15} /> Remover</button>}
      </div>
    </form>
  )
}
