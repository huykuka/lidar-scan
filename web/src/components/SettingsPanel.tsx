import { SynCard, SynInput } from '@synergy-design-system/react'
import { useSettingsStore } from '../state/useSettingsStore'

export function SettingsPanel() {
  const { pointSize, pointColor, setPointSize, setPointColor } = useSettingsStore()

  const handleSizeChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    const value = parseFloat(target.value)
    if (!isNaN(value) && value > 0 && value <= 2) {
      setPointSize(value)
    }
  }

  const handleColorChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    setPointColor(target.value)
  }

  return (
    <SynCard className="bg-transparent border border-white/10 p-0">
      <div className="p-4 md:p-6 flex flex-col gap-3 md:gap-4">
        <label className="text-xs uppercase tracking-[0.2em] md:tracking-[0.4em] text-slate-400">Point Cloud Settings</label>
        
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-300">Point Size</span>
            <span className="text-sm text-slate-400 font-mono">{pointSize.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0.01"
            max="1"
            step="0.01"
            value={pointSize}
            onChange={(e) => handleSizeChange(e as unknown as Event)}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-synergy-accent"
          />
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm text-slate-300">Point Color</span>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={pointColor}
              onChange={(e) => handleColorChange(e as unknown as Event)}
              className="w-10 h-10 rounded cursor-pointer border border-white/20 bg-transparent"
            />
            <SynInput
              value={pointColor}
              onSynInput={handleColorChange}
              className="flex-1 font-mono"
              size="small"
            />
          </div>
        </div>
      </div>
    </SynCard>
  )
}
