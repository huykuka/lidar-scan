import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, expect, test, beforeEach, vi, afterEach } from 'vitest'
import { useTopics } from '../useTopics'
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

describe('useTopics', () => {
  beforeEach(() => {
    // Reset store state before each test
    useLidarStore.setState({
      topics: [],
      topicsLoading: false,
      topicsError: null,
      topic: null,
    })
    mockApiGet.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('fetches topics on mount', async () => {
    mockApiGet.mockResolvedValue({
      data: { topics: ['topic1', 'topic2'] },
    })

    const { result } = renderHook(() => useTopics())

    await waitFor(() => {
      expect(result.current.topics).toEqual(['topic1', 'topic2'])
    })

    expect(mockApiGet).toHaveBeenCalledWith('/topics')
  })

  test('sets loading state while fetching', async () => {
    let resolvePromise: (value: unknown) => void
    mockApiGet.mockImplementation(
      () => new Promise((resolve) => {
        resolvePromise = resolve
      })
    )

    const { result } = renderHook(() => useTopics())

    // Should be loading initially
    await waitFor(() => {
      expect(result.current.topicsLoading).toBe(true)
    })

    // Resolve the fetch
    await act(async () => {
      resolvePromise!({
        data: { topics: [] },
      })
    })

    await waitFor(() => {
      expect(result.current.topicsLoading).toBe(false)
    })
  })

  test('sets error on fetch failure', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useTopics())

    await waitFor(() => {
      expect(result.current.topicsError).toBe('Network error')
    })
  })

  test('auto-selects first topic when none selected', async () => {
    mockApiGet.mockResolvedValue({
      data: { topics: ['first', 'second'] },
    })

    renderHook(() => useTopics())

    await waitFor(() => {
      expect(useLidarStore.getState().topic).toBe('first')
    })
  })

  test('keeps current topic if still in list', async () => {
    useLidarStore.setState({ topic: 'second' })

    mockApiGet.mockResolvedValue({
      data: { topics: ['first', 'second', 'third'] },
    })

    renderHook(() => useTopics())

    await waitFor(() => {
      expect(useLidarStore.getState().topics).toEqual(['first', 'second', 'third'])
    })
    // Topic should remain 'second' since it's in the list
    expect(useLidarStore.getState().topic).toBe('second')
  })

  test('selects first topic if current topic not in new list', async () => {
    useLidarStore.setState({ topic: 'old_topic' })

    mockApiGet.mockResolvedValue({
      data: { topics: ['new1', 'new2'] },
    })

    renderHook(() => useTopics())

    await waitFor(() => {
      expect(useLidarStore.getState().topic).toBe('new1')
    })
  })

  test('refetchTopics triggers new fetch', async () => {
    let callCount = 0
    mockApiGet.mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        return Promise.resolve({
          data: { topics: ['initial'] },
        })
      }
      return Promise.resolve({
        data: { topics: ['refreshed'] },
      })
    })

    const { result } = renderHook(() => useTopics())

    // Wait for initial fetch
    await waitFor(() => {
      expect(result.current.topics).toEqual(['initial'])
    })

    // Trigger refetch
    await act(async () => {
      await result.current.refetchTopics()
    })

    await waitFor(() => {
      expect(result.current.topics).toEqual(['refreshed'])
    })

    expect(mockApiGet).toHaveBeenCalledTimes(2)
  })
})
