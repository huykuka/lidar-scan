import { useEffect, useCallback, useRef } from 'react'
import { useLidarStore } from '../state/useLidarStore'
import { api } from '../lib/api'
import type { TopicsResponse } from '../lib/api'

export function useTopics() {
  const {
    topics,
    topicsLoading,
    topicsError,
    setTopics,
    setTopicsLoading,
    setTopicsError,
    topic,
    setTopic,
  } = useLidarStore()

  // Use ref to get latest topic value without adding it as a dependency
  const topicRef = useRef(topic)
  topicRef.current = topic

  const fetchTopics = useCallback(async () => {
    setTopicsLoading(true)
    setTopicsError(null)

    try {
      const { data } = await api.get<TopicsResponse>('/topics')
      const fetchedTopics = data.topics || []
      setTopics(fetchedTopics)

      // Auto-select first topic if none selected or current selection is invalid
      const currentTopic = topicRef.current
      if (fetchedTopics.length > 0) {
        if (!currentTopic || !fetchedTopics.includes(currentTopic)) {
          setTopic(fetchedTopics[0])
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch topics'
      setTopicsError(message)
      console.error('Error fetching topics:', err)
    } finally {
      setTopicsLoading(false)
    }
  }, [setTopics, setTopicsLoading, setTopicsError, setTopic])

  // Fetch topics on mount only
  useEffect(() => {
    fetchTopics()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    topics,
    topicsLoading,
    topicsError,
    refetchTopics: fetchTopics,
  }
}
