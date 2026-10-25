// Tipos e utilitários das vagas (espelham /api/resumo e /api/vagas)

export type Status = 'pool' | 'fila' | 'recomendada' | 'confirmada' | 'descartada' | 'ignorada' | 'expirada' | 'erro'

export type ItemVaga = {
  id: string
  titulo: string
  empresa: string | null
  cidade: string | null
  uf: string | null
  modalidade: string
  nivel: string
  url: string
  fontes: string[]
  publicada_em: string | null
  status: Status
  status_em: string
  score_prefiltro: number
  score_ia: number | null
  area: string | null
  resumo: string | null
  motivo_usuario: string | null
}

export type ResultadoAuditoria = {
  resumo?: string
  area?: string
  requisitos_atendidos?: string[]
  gaps?: string[]
  red_flags?: string[]
  motivo_descarte?: string | null
  nivel_compativel?: boolean
  modalidade_compativel?: boolean
}

export type DetalheVaga = ItemVaga & {
  descricao: string
  auditoria: { resultado: ResultadoAuditoria; modelo: string; em: string } | null
  historico: { de: Status | null; para: Status; origem: string; detalhe: string | null; em: string }[]
}

export type ListaVagas = { total: number; pagina: number; por_pagina: number; itens: ItemVaga[] }

export type Resumo = {
  contagens: Record<Status, number>
  limites: { fila: number; recomendadas: number }
  recomendadas_hoje: number
  vagas_novas_hoje: number
  fontes: { id: string; nome: string; iniciada_em: string | null; status: string | null; coletadas: number | null; novas: number | null; erro: string | null }[]
  atividade: { vaga_id: string; titulo: string; para: Status; origem: string; detalhe: string | null; em: string }[]
  motivos_ignorar: Record<string, string>
}

export const ROTULO_STATUS: Record<Status, string> = {
  recomendada: 'Recomendadas',
  fila: 'Na fila da IA',
  pool: 'Pool',
  confirmada: 'Confirmadas',
  ignorada: 'Ignoradas',
  descartada: 'Descartadas pela IA',
  expirada: 'Expiradas',
  erro: 'Com erro',
}

export const ABAS: Status[] = ['recomendada', 'fila', 'pool', 'confirmada', 'ignorada', 'descartada', 'expirada']

const MODALIDADE: Record<string, string> = { remoto: 'Remoto', hibrido: 'Híbrido', presencial: 'Presencial', desconhecida: 'Modalidade não informada' }
export const rotuloModalidade = (m: string) => MODALIDADE[m] ?? m

export function local(v: Pick<ItemVaga, 'cidade' | 'uf' | 'modalidade'>) {
  const lugar = [v.cidade, v.uf].filter(Boolean).join(', ')
  return lugar || (v.modalidade === 'remoto' ? 'Brasil' : 'Local não informado')
}

export function tempoRelativo(iso: string | null) {
  if (!iso) return '—'
  const minutos = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutos < 1) return 'agora'
  if (minutos < 60) return `há ${minutos} min`
  const horas = Math.round(minutos / 60)
  if (horas < 24) return `há ${horas} h`
  const dias = Math.round(horas / 24)
  return dias === 1 ? 'ontem' : `há ${dias} dias`
}
