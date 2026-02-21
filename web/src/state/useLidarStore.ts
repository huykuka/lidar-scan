import { create } from 'zustand'

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error'

interface FrameState {
  points: Float32Array
  count: number
  timestamp: number
  summary: string
}

interface LidarState {
  // Topics
  topics: string[]
  topicsLoading: boolean
  topicsError: string | null
  setTopics: (topics: string[]) => void
  setTopicsLoading: (loading: boolean) => void
  setTopicsError: (error: string | null) => void

  // Version/Status
  version: string
  setVersion: (version: string) => void

  // Selected topic & connection
  topic: string | null
  connection: ConnectionState
  frame: FrameState
  setTopic: (topic: string | null) => void
  setConnection: (state: ConnectionState) => void
  setFrame: (frame: FrameState) => void
}

const defaultFrame: FrameState = {
  points: new Float32Array(),
  count: 0,
  timestamp: 0,
  summary: 'No frames yet',
}

export const useLidarStore = create<LidarState>((set) => ({
  // Topics
  topics: [],
  topicsLoading: false,
  topicsError: null,
  setTopics: (topics) => set({ topics }),
  setTopicsLoading: (topicsLoading) => set({ topicsLoading }),
  setTopicsError: (topicsError) => set({ topicsError }),

  // Version
  version: '',
  setVersion: (version) => set({ version }),

  // Selected topic & connection
  topic: null,
  connection: 'closed',
  frame: defaultFrame,
  setTopic: (topic) => set({ topic }),
  setConnection: (connection) => set({ connection }),
  setFrame: (frame) => set({ frame }),
}))
