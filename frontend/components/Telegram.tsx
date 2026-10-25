'use client'

import { useEffect, useState } from 'react'
import { ExternalLink, Send } from 'lucide-react'
import { api, ErroApi } from '@/lib/api'

type Status = { configurado: boolean; situacao: 'nao_vinculado' | 'aguardando' | 'vinculado' }

const TEXTO: Record<Status['situacao'], string> = {
  vinculado: 'Vinculado: as recomendações chegam no seu Telegram, com os botões de decisão.',
  aguardando: 'Link gerado: abra no Telegram e toque em Iniciar para concluir.',
  nao_vinculado: 'Não vinculado: as recomendações aparecem só aqui na web.',
}

/** Vínculo do Telegram (mesmo fluxo do `job-radar telegram vincular`). */
export function CartaoTelegram() {
  const [status, setStatus] = useState<Status | null>(null)
  const [link, setLink] = useState('')
  const [erro, setErro] = useState('')

  useEffect(() => { api<Status>('/telegram').then(setStatus).catch(() => {}) }, [])
  if (!status || !status.configurado) return null

  async function vincular() {
    setErro('')
    try {
      const r = await api<{ link: string }>('/telegram/vincular', { metodo: 'POST' })
      setLink(r.link)
      setStatus({ ...status!, situacao: 'aguardando' })
    } catch (e) { setErro(e instanceof ErroApi ? e.message : 'Erro') }
  }

  return (
    <section className="panel bloco">
      <div className="panel-heading"><div><h3>Telegram</h3><p>Receba as recomendações no celular e decida por lá.</p></div></div>
      <p className={`telegram-status telegram-${status.situacao}`}><Send size={15} /> {TEXTO[status.situacao]}</p>
      {link && <p className="dica"><a className="text-button" href={link} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} /> Abrir no Telegram</a><span>Link de uso único; o vínculo conclui em até 1 minuto depois do Iniciar.</span></p>}
      {erro && <p className="alerta alerta-erro">{erro}</p>}
      <button type="button" className="outline-button" onClick={vincular}>{status.situacao === 'vinculado' ? 'Vincular outro chat' : 'Gerar link de vínculo'}</button>
    </section>
  )
}
