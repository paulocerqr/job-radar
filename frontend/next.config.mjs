/** @type {import('next').NextConfig} */
const nextConfig = {
  // Exportação estática: a API (FastAPI) serve os arquivos; sem servidor Node em produção
  output: 'export',
  images: { unoptimized: true },
  poweredByHeader: false,
}

export default nextConfig
