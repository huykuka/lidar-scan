import { useLidarStore } from '../state/useLidarStore'
import { useStatus } from '../hooks/useStatus'

const statusPalette: Record<string, string> = {
  connecting: 'text-yellow-300',
  open: 'text-emerald-300',
  closed: 'text-slate-300',
  error: 'text-red-300',
}

export function Hud() {
  const { topic, connection, frame } = useLidarStore()
  const { version } = useStatus()
  
  return (
    <div className="pointer-events-none absolute bottom-8 left-8 max-w-sm rounded-2xl border border-white/20 bg-black/50 p-6 backdrop-blur">
      <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Topic</p>
      <p className="font-mono text-lg text-white">{topic || 'None selected'}</p>
      <p className="text-xs uppercase tracking-[0.3em] text-slate-400 mt-4">Connection</p>
      <p className={`font-mono text-lg ${statusPalette[connection]}`}>{connection}</p>
      <p className="text-xs uppercase tracking-[0.3em] text-slate-400 mt-4">Last Frame</p>
      <p className="font-mono text-lg text-synergy-accent">{frame.summary}</p>
      {version && (
        <>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400 mt-4">Version</p>
          <p className="font-mono text-sm text-slate-300">{version}</p>
        </>
      )}
    </div>
  )
}
