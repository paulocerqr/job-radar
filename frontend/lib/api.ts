// Cliente da API JSON do Job Radar (mesma origem: o cookie da sessão vai sozinho).
// Escritas levam o token CSRF da sessão no cabeçalho X-CSRF-Token.

export type Usuario = { nome: string; email: string }

export class ErroApi extends Error {
  constructor(public status: number, public corpo: Record<string, unknown>) {
    super(typeof corpo.erro === 'string' ? corpo.erro : `HTTP ${status}`)
  }
}

let csrf = ''

export function definirCsrf(token: string) {
  csrf = token
}

export async function api<T>(caminho: string, opcoes: { metodo?: string; corpo?: unknown } = {}): Promise<T> {
  const metodo = opcoes.metodo ?? 'GET'
  const resposta = await fetch(`/api${caminho}`, {
    method: metodo,
    credentials: 'same-origin',
    headers: metodo === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: opcoes.corpo === undefined ? (metodo === 'GET' ? undefined : '{}') : JSON.stringify(opcoes.corpo),
  })
  const corpo = await resposta.json().catch(() => ({}))
  if (resposta.status === 401 && caminho !== '/login') {
    window.location.assign('/login/')
  }
  if (!resposta.ok) throw new ErroApi(resposta.status, corpo)
  return corpo as T
}
