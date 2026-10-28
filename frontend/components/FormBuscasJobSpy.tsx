'use client'

import { useState } from 'react'
import { Plus, Save, Trash2, X } from 'lucide-react'
import { api } from '@/lib/api'

export type ConfigBuscasJobSpy = {
  buscas: { termo: string; local: string }[]
  horas?: number
  pausa_s?: number
}

export function FormBuscasJobSpy({ inicial, limite, aoSalvar, aoCancelar }: {
  inicial: ConfigBuscasJobSpy; limite: number
  aoSalvar: () => void; aoCancelar: () => void
}) {
  const [buscas, setBuscas] = useState(inicial.buscas)
  const [horas, setHoras] = useState(inicial.horas ?? 72)
  const [pausa, setPausa] = useState(inicial.pausa_s ?? 5)
  const [maxItens, setMaxItens] = useState(limite)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState('')

  function mudar(indice: number, campo: 'termo' | 'local', valor: string) {
    setBuscas(buscas.map((busca, i) => i === indice ? { ...busca, [campo]: valor } : busca))
  }

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault()
    setErro('')
    if (buscas.some((b) => !b.termo.trim() || !b.local.trim())) {
      setErro('Informe um cargo e uma localização para cada busca.')
      return
    }
    setSalvando(true)
    try {
      await api('/fontes/jobspy/buscas', {
        metodo: 'PUT',
        corpo: { config: { buscas, horas, pausa_s: pausa }, max_itens: maxItens },
      })
      aoSalvar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao salvar as buscas.')
    } finally { setSalvando(false) }
  }

  return (
    <form className="form-buscas" aria-label="Editar buscas do LinkedIn" onSubmit={salvar}>
      <h3>Buscas do LinkedIn</h3>
      <p className="dica">As alterações valem para as próximas coletas. As buscas seguem a ordem abaixo até atingir o limite total. Para direcionar a busca, experimente termos como “estágio suporte remoto” e localização “Brazil”. A modalidade ainda precisa ser confirmada na vaga.</p>
      <fieldset className="buscas-campos" disabled={salvando}>
        {buscas.map((busca, i) => (
          <fieldset className="campo busca-item" key={i}>
            <legend>Busca {i + 1}</legend>
            <div className="grade-2">
              <label className="campo">Cargo ou palavras-chave
                <input value={busca.termo} onChange={(e) => mudar(i, 'termo', e.target.value)} maxLength={200} required />
              </label>
              <label className="campo">Localização
                <input value={busca.local} onChange={(e) => mudar(i, 'local', e.target.value)} maxLength={200} required placeholder="Ex.: Brasília, Distrito Federal, Brazil" />
              </label>
            </div>
            <button type="button" className="outline-button" disabled={buscas.length === 1} onClick={() => setBuscas(buscas.filter((_, indice) => indice !== i))}><Trash2 size={14} /> Remover busca {i + 1}</button>
          </fieldset>
        ))}
        <button type="button" className="outline-button" disabled={buscas.length >= 5} onClick={() => setBuscas([...buscas, { termo: '', local: 'Brazil' }])}><Plus size={14} /> Adicionar busca ({buscas.length}/5)</button>
        <div className="grade-3">
          <label className="campo">Publicadas nas últimas (horas)
            <input type="number" min={1} max={720} step={1} required value={horas} onChange={(e) => setHoras(Number(e.target.value))} />
          </label>
          <label className="campo">Limite total por coleta
            <input type="number" min={1} max={50} step={1} required value={maxItens} onChange={(e) => setMaxItens(Number(e.target.value))} />
          </label>
          <label className="campo">Pausa entre buscas (segundos)
            <input type="number" min={0} max={60} step="any" required value={pausa} onChange={(e) => setPausa(Number(e.target.value))} />
          </label>
        </div>
        {erro && <p className="alerta alerta-erro" role="alert">{erro}</p>}
        <div className="acoes-linha">
          <button className="botao-primario" type="submit"><Save size={15} /> {salvando ? 'Salvando…' : 'Salvar buscas'}</button>
          <button className="outline-button" type="button" onClick={aoCancelar}><X size={15} /> Cancelar</button>
        </div>
      </fieldset>
    </form>
  )
}
