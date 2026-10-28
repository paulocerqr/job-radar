'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Copy, MailPlus, Trash2 } from 'lucide-react'
import { AppShell, useUsuario } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'
import { tempoRelativo } from '@/lib/vagas'

type Linha = { id: string; nome: string; email: string; papel: string; ativo: boolean; criado_em: string; eu: boolean }
type ConviteLinha = { id: string; email: string; situacao: 'pendente' | 'usado' | 'expirado' | 'revogado'; criado_em: string; expira_em: string }
type Dados = { usuarios: Linha[]; convites: ConviteLinha[] }

const SITUACAO: Record<string, string> = { pendente: 'Pendente', usado: 'Aceito', expirado: 'Expirado', revogado: 'Revogado' }

function Usuarios() {
  const eu = useUsuario()
  const [dados, setDados] = useState<Dados | null>(null)
  const [email, setEmail] = useState('')
  const [link, setLink] = useState('')
  const [erro, setErro] = useState('')
  const [toast, setToast] = useState('')

  const carregar = useCallback(() => api<Dados>('/usuarios').then(setDados), [])
  useEffect(() => { if (eu?.papel === 'admin') carregar() }, [eu, carregar])

  function avisar(texto: string) {
    setToast(texto)
    window.setTimeout(() => setToast(''), 3500)
  }

  async function convidar(evento: React.FormEvent) {
    evento.preventDefault()
    setErro('')
    setLink('')
    try {
      const r = await api<{ caminho: string }>('/convites', { metodo: 'POST', corpo: { email } })
      setLink(`${window.location.origin}${r.caminho}`) // origem do navegador: mantém o https
      setEmail('')
      carregar()
    } catch (e) { setErro(e instanceof ErroApi ? e.message : 'Erro ao criar o convite') }
  }

  async function copiar() {
    await navigator.clipboard.writeText(link).then(() => avisar('Link copiado.'), () => avisar('Selecione e copie o link manualmente.'))
  }

  async function revogar(c: ConviteLinha) {
    await api(`/convites/${c.id}`, { metodo: 'DELETE' }).catch(() => {})
    avisar(`Convite para ${c.email} revogado.`)
    carregar()
  }

  async function alternar(u: Linha) {
    try {
      await api(`/usuarios/${u.id}`, { metodo: 'PATCH', corpo: { ativo: !u.ativo } })
      avisar(u.ativo ? `${u.nome} desativado: não entra mais nem recebe vagas.` : `${u.nome} reativado.`)
      carregar()
    } catch (e) { avisar(e instanceof ErroApi ? e.message : 'Erro') }
  }

  if (eu?.papel !== 'admin') return <p className="dica">Apenas o admin gerencia usuários.</p>
  if (!dados) return <div className="carregando-bloco">Carregando…</div>

  return (
    <>
      <section className="hero"><div><h1>Usuários & convites</h1><p>Quem usa o Job Radar. Novas pessoas entram por convite, com link de uso único válido por 7 dias.</p></div></section>

      <section className="stats-grid" aria-label="Resumo de acesso">
        <div className="stat-card"><div className="stat-label">Usuários ativos</div><strong>{dados.usuarios.filter((u) => u.ativo).length}</strong><small>{dados.usuarios.length} cadastrado(s)</small></div>
        <div className="stat-card"><div className="stat-label">Convites pendentes</div><strong>{dados.convites.filter((c) => c.situacao === 'pendente').length}</strong><small>nos últimos 50 convites</small></div>
        <div className="stat-card"><div className="stat-label">Convites aceitos</div><strong>{dados.convites.filter((c) => c.situacao === 'usado').length}</strong><small>nos últimos 50 convites</small></div>
        <div className="stat-card"><div className="stat-label">Acesso por convite</div><strong>7 dias</strong><small>validade de cada link de uso único</small></div>
      </section>
      <section className="panel bloco">
        <div className="panel-heading"><div><h3>Convidar</h3><p>Envie o link para a pessoa; ela define o próprio nome e senha. Convidados usam os seus providers de IA.</p></div></div>
        <form className="convite-form" onSubmit={convidar}>
          <label className="campo">E-mail da pessoa
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="nome@exemplo.com" />
          </label>
          <button className="botao-primario" type="submit"><MailPlus size={16} /> Gerar convite</button>
        </form>
        {erro && <p className="alerta alerta-erro">{erro}</p>}
        {link && (
          <div className="link-convite">
            <p>Link gerado. <b>Ele só aparece agora</b>: copie e envie para a pessoa.</p>
            <div className="link-linha"><code>{link}</code><button className="outline-button" type="button" onClick={copiar}><Copy size={14} /> Copiar</button></div>
          </div>
        )}
      </section>

      <section className="section-heading"><div><h2>Usuários</h2></div></section>
      <div className="tabela-simples-rolagem">
        <table className="tabela-simples">
          <thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Desde</th><th>Situação</th></tr></thead>
          <tbody>
            {dados.usuarios.map((u) => (
              <tr key={u.id}>
                <td>{u.nome}{u.eu && <span className="voce"> (você)</span>}</td><td>{u.email}</td><td>{u.papel === 'admin' ? 'Admin' : 'Usuário'}</td>
                <td>{new Date(u.criado_em).toLocaleDateString('pt-BR')}</td>
                <td>{u.eu ? <span className="source-state ok">Ativo</span> : (
                  <label className="interruptor"><input type="checkbox" checked={u.ativo} onChange={() => alternar(u)} /><span>{u.ativo ? 'Ativo' : 'Desativado'}</span></label>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="section-heading"><div><h2>Convites</h2><p>Os 50 mais recentes.</p></div></section>
      {dados.convites.length === 0 ? <div className="jobs-table vazio">Nenhum convite ainda.</div> : (
        <div className="tabela-simples-rolagem">
          <table className="tabela-simples">
            <thead><tr><th>E-mail</th><th>Criado</th><th>Expira</th><th>Situação</th><th /></tr></thead>
            <tbody>
              {dados.convites.map((c) => (
                <tr key={c.id}>
                  <td>{c.email}</td><td>{tempoRelativo(c.criado_em)}</td>
                  <td>{c.situacao === 'pendente' ? new Date(c.expira_em).toLocaleDateString('pt-BR') : '—'}</td>
                  <td><span className={`source-state ${c.situacao === 'usado' ? 'ok' : c.situacao === 'pendente' ? 'pendente' : 'warn'}`}>{SITUACAO[c.situacao]}</span></td>
                  <td>{c.situacao === 'pendente' && <button className="icon-button small danger-action" title="Revogar" onClick={() => revogar(c)}><Trash2 size={15} /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {toast && <div className="toast"><CheckCircle2 size={17} /> {toast}</div>}
    </>
  )
}

export default function Page() {
  return <AppShell titulo="Usuários"><Usuarios /></AppShell>
}
