'use client'

import { useEffect, useState } from 'react'
import { UserPlus } from 'lucide-react'
import { RadarMark } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'

export default function AceitarConvite() {
  const [token, setToken] = useState('')
  const [email, setEmail] = useState<string | null>(null)
  const [invalido, setInvalido] = useState('')
  const [nome, setNome] = useState('')
  const [senha, setSenha] = useState('')
  const [confirmacao, setConfirmacao] = useState('')
  const [erros, setErros] = useState<Record<string, string>>({})
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get('token') ?? ''
    setToken(t)
    // tira o token da barra de endereço (e do histórico) assim que ele é lido
    window.history.replaceState(null, '', '/convite/')
    if (!t) { setInvalido('Link de convite incompleto.'); return }
    api<{ email: string }>(`/convites/validar?token=${encodeURIComponent(t)}`)
      .then((r) => setEmail(r.email))
      .catch((e) => setInvalido(e instanceof ErroApi ? e.message : 'Não foi possível validar o convite.'))
  }, [])

  async function criar(evento: React.FormEvent) {
    evento.preventDefault()
    if (senha !== confirmacao) { setErros({ confirmacao: 'As senhas não conferem' }); return }
    setErros({})
    setEnviando(true)
    try {
      await api('/convites/aceitar', { metodo: 'POST', corpo: { token, nome, senha } })
      window.location.assign('/perfil/')
    } catch (e) {
      if (e instanceof ErroApi && e.status === 422) setErros(e.corpo.erros as Record<string, string>)
      else setInvalido(e instanceof ErroApi ? e.message : 'Erro ao criar a conta.')
      setEnviando(false)
    }
  }

  return (
    <div className="login-tela">
      <div className="login-cartao">
        <div className="brand login-marca"><div className="brand-mark"><RadarMark /></div><span>job<span>radar</span></span></div>
        {invalido ? (
          <>
            <h1>Convite indisponível</h1>
            <p className="login-sub">{invalido} Peça um novo link a quem convidou você.</p>
            <a className="text-button" href="/login/">Ir para o login</a>
          </>
        ) : !email ? <p className="login-sub">Validando o convite…</p> : (
          <form onSubmit={criar}>
            <h1>Criar conta</h1>
            <p className="login-sub">Você foi convidado(a) para o Job Radar com o e-mail <b>{email}</b>.</p>
            <label className="campo">Seu nome
              <input value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" required autoFocus maxLength={80} />
              {erros.nome && <span className="erro-campo">{erros.nome}</span>}
            </label>
            <label className="campo">Senha <small>pelo menos 10 caracteres</small>
              <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="new-password" required minLength={10} />
              {erros.senha && <span className="erro-campo">{erros.senha}</span>}
            </label>
            <label className="campo">Confirme a senha
              <input type="password" value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} autoComplete="new-password" required />
              {erros.confirmacao && <span className="erro-campo">{erros.confirmacao}</span>}
            </label>
            <button className="botao-primario" type="submit" disabled={enviando}><UserPlus size={16} /> {enviando ? 'Criando…' : 'Criar conta e entrar'}</button>
          </form>
        )}
      </div>
    </div>
  )
}
