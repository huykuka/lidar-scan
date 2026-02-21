import type { PropsWithChildren } from 'react'

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-[320px_1fr] lg:grid-cols-[360px_1fr] bg-gradient-to-br from-synergy-secondary to-black text-white">
      {children}
    </div>
  )
}
