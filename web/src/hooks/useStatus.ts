import { useEffect } from 'react'
import { useLidarStore } from '../state/useLidarStore'
import { api } from '../lib/api'
import type { StatusResponse } from '../lib/api'

export function useStatus() {
  const { version, setVersion } = useLidarStore()

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const { data } = await api.get<StatusResponse>('/status')
        if (data.version) {
          setVersion(data.version)
        }
      } catch (err) {
        console.error('Error fetching status:', err)
        setVersion('Unknown')
      }
    }

    fetchStatus()
  }, [setVersion])

  return { version }
}
