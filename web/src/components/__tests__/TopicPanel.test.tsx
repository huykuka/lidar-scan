import { render, screen, waitFor, act } from '@testing-library/react'
import { describe, expect, test, beforeEach, vi, afterEach } from 'vitest'
import { TopicPanel } from '../TopicPanel'
import { useLidarStore } from '../../state/useLidarStore'
import { api } from '../../lib/api'

// Mock axios
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api')
  return {
    ...actual,
    api: {
      get: vi.fn(),
    },
  }
})

const mockApiGet = vi.mocked(api.get)

describe('TopicPanel', () => {
  beforeEach(() => {
    // Reset store state before each test
    useLidarStore.setState({
      topics: [],
      topicsLoading: false,
      topicsError: null,
      topic: null,
      connection: 'closed',
      frame: {
        points: new Float32Array(),
        count: 0,
        timestamp: 0,
        summary: 'No frames yet',
      },
      version: '',
    })
    mockApiGet.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('shows loading state while fetching topics', async () => {
    mockApiGet.mockImplementation(() => new Promise(() => {})) // Never resolves
    render(<TopicPanel />)
    expect(screen.getByText(/loading topics/i)).toBeInTheDocument()
  })

  test('shows error message when fetch fails', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))
    render(<TopicPanel />)
    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeInTheDocument()
    })
  })

  test('shows "no topics available" when API returns empty list', async () => {
    mockApiGet.mockResolvedValue({
      data: { topics: [] },
    })
    render(<TopicPanel />)
    await waitFor(() => {
      expect(screen.getByText(/no topics available/i)).toBeInTheDocument()
    })
  })

  test('auto-selects first topic when topics are loaded', async () => {
    mockApiGet.mockResolvedValue({
      data: { topics: ['auto_topic', 'other_topic'] },
    })
    render(<TopicPanel />)
    await waitFor(() => {
      const state = useLidarStore.getState()
      expect(state.topic).toBe('auto_topic')
    })
  })

  test('displays connection status badge', async () => {
    // Set connection state before render
    await act(async () => {
      useLidarStore.setState({ connection: 'open', topics: ['test'], topic: 'test' })
    })
    
    mockApiGet.mockResolvedValue({
      data: { topics: ['test'] },
    })
    
    render(<TopicPanel />)
    
    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument()
    })
  })
})
