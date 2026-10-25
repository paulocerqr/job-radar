/** @type {import('next').NextConfig} */
const desenvolvimento = process.env.NODE_ENV !== 'production'

const nextConfig = {
  // Produção: exportação estática que a API (FastAPI) serve; sem servidor Node
  ...(desenvolvimento ? {} : { output: 'export' }),
  trailingSlash: true, // /perfil → perfil/index.html, que o StaticFiles da API encontra
  images: { unoptimized: true },
  poweredByHeader: false,
  // `pnpm dev`: repassa /api para a API local (mesma origem, como em produção)
  ...(desenvolvimento
    ? { rewrites: async () => [{ source: '/api/:caminho*', destination: 'http://127.0.0.1:8000/api/:caminho*' }] }
    : {}),
}

export default nextConfig
