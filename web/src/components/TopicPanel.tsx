import { useMemo } from 'react'
import { SynCard, SynSelect, SynOption, SynButton, SynBadge, SynSpinner } from '@synergy-design-system/react'
import { useLidarStore } from '../state/useLidarStore'
import { useTopics } from '../hooks/useTopics'
import { SettingsPanel } from './SettingsPanel'

const connectionColors: Record<string, string> = {
  connecting: 'bg-yellow-400 text-yellow-950',
  open: 'bg-emerald-400 text-emerald-950',
  closed: 'bg-gray-400 text-gray-900',
  error: 'bg-red-400 text-red-950',
}

export function TopicPanel() {
  const { topic, setTopic, connection, frame } = useLidarStore()
  const { topics, topicsLoading, topicsError, refetchTopics } = useTopics()

  const badgeClass = useMemo(() => connectionColors[connection], [connection])

  const handleTopicChange = (event: Event) => {
    const target = event.target as HTMLSelectElement
    if (target.value) {
      setTopic(target.value)
    }
  }

  return (
    <aside className="border-b md:border-b-0 md:border-r border-white/10 bg-synergy-panel/80 backdrop-blur-xl p-4 md:p-6 lg:p-8 flex flex-col gap-4 md:gap-6 lg:gap-8 font-display overflow-y-auto max-h-[50vh] md:max-h-none">
      <header>
        <p className="uppercase tracking-[0.2em] md:tracking-[0.4em] text-xs md:text-sm text-synergy-accent/80">Synergy Control Deck</p>
        <h1 className="text-xl md:text-2xl lg:text-3xl mt-1 md:mt-2 font-semibold">LiDAR Command Surface</h1>
        <p className="text-xs md:text-sm text-slate-300 mt-2 md:mt-3 hidden sm:block">
          Stream LiDAR frames via WebSocket and orbit through point clouds rendered with React Three Fiber.
        </p>
      </header>
      <SynCard className="bg-transparent border border-white/10 p-0">
        <div className="p-4 md:p-6 flex flex-col gap-3 md:gap-4">
          <label className="text-xs uppercase tracking-[0.2em] md:tracking-[0.4em] text-slate-400">Topic</label>
          
          {topicsLoading ? (
            <div className="flex items-center gap-2 text-slate-400">
              <SynSpinner />
              <span className="text-sm">Loading topics...</span>
            </div>
          ) : topicsError ? (
            <div className="flex flex-col gap-2">
              <p className="text-red-400 text-sm">{topicsError}</p>
              <SynButton variant="outline" size="small" onClick={() => refetchTopics()}>
                Retry
              </SynButton>
            </div>
          ) : topics.length === 0 ? (
            <div className="flex flex-col gap-2">
              <p className="text-slate-400 text-sm">No topics available</p>
              <SynButton variant="outline" size="small" onClick={() => refetchTopics()}>
                Refresh
              </SynButton>
            </div>
          ) : (
            <>
              <SynSelect
                value={topic || ''}
                onSynChange={handleTopicChange}
                placeholder="Select a topic"
              >
                {topics.map((t) => (
                  <SynOption key={t} value={t}>
                    {t}
                  </SynOption>
                ))}
              </SynSelect>
              <SynButton
                variant="text"
                size="small"
                onClick={() => refetchTopics()}
              >
                Refresh Topics
              </SynButton>
            </>
          )}

          <div className="flex items-center gap-2">
            <SynBadge className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.3em] ${badgeClass}`}>
              {connection}
            </SynBadge>
            <p className="text-slate-400 text-xs font-mono">{frame.summary}</p>
          </div>
        </div>
      </SynCard>
      <SettingsPanel />
    </aside>
  )
}
