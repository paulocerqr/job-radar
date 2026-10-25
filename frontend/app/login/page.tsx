'use client'

import { useState } from 'react'
import { LogIn } from 'lucide-react'
import { RadarMark } from '@/components/AppShell'
import { api, ErroApi } from '@/lib/api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function entrar(evento: React.FormEvent) {
    evento.preventDefault()
    setErro('')
    setEnviando(true)
    try {
      await api('/login', { metodo: 'POST', corpo: { email, senha } })
      window.location.assign('/')
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : 'Não foi possível conectar à API.')
      setEnviando(false)
    }
  }

  return (
    <div className="login-tela">
      <form className="login-cartao" onSubmit={entrar}>
        <div className="brand login-marca"><div className="brand-mark"><RadarMark /></div><span>job<span>radar</span></span></div>
        <h1>Entrar</h1>
        <p className="login-sub">Vagas coletadas, filtradas e auditadas por IA.</p>
        {erro && <p className="alerta alerta-erro" role="alert">{erro}</p>}
        <label className="campo">E-mail
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required autoFocus />
        </label>
        <label className="campo">Senha
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="current-password" required />
        </label>
        <button className="botao-primario" type="submit" disabled={enviando}><LogIn size={16} /> {enviando ? 'Entrando…' : 'Entrar'}</button>
      </form>
    </div>
  )
}
