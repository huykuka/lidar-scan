import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, test, beforeEach, vi, afterEach } from 'vitest'
import { useStatus } from '../useStatus'
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

describe('useStatus', () => {
  beforeEach(() => {
    useLidarStore.setState({ version: '' })
    mockApiGet.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('fetches version on mount', async () => {
    mockApiGet.mockResolvedValue({
      data: { version: '1.2.3' },
    })

    const { result } = renderHook(() => useStatus())

    await waitFor(() => {
      expect(result.current.version).toBe('1.2.3')
    })

    expect(mockApiGet).toHaveBeenCalledWith('/status')
  })

  test('sets version to Unknown on fetch error', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useStatus())

    await waitFor(() => {
      expect(result.current.version).toBe('Unknown')
    })
  })

  test('handles missing version in response', async () => {
    mockApiGet.mockResolvedValue({
      data: {},
    })

    const { result } = renderHook(() => useStatus())

    // Should not update if version is missing
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled()
    })
    
    // Version stays empty since no version was returned
    expect(result.current.version).toBe('')
  })
})
