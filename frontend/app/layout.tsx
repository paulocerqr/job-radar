import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Job Radar',
  description: 'Vagas de estágio coletadas, filtradas e auditadas por IA',
  icons: { icon: '/radar.svg' }, // nome novo: o /icon.svg antigo (logo do v0) ficou em cache na Cloudflare
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#10131a',
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  )
}
