import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsState {
  pointSize: number
  pointColor: string
  setPointSize: (size: number) => void
  setPointColor: (color: string) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      pointSize: 0.1,
      pointColor: '#00ff00',
      setPointSize: (pointSize) => set({ pointSize }),
      setPointColor: (pointColor) => set({ pointColor }),
    }),
    {
      name: 'lidar-settings',
    }
  )
)
