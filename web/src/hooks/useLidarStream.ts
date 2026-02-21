import { useEffect } from 'react'
import { formatFrameSummary, parseLidrFrame } from '../lib/frames'
import { useLidarStore } from '../state/useLidarStore'
import { buildWsUrl } from '../lib/api'

export function useLidarStream() {
  const { topic, setConnection, setFrame } = useLidarStore()

  useEffect(() => {
    // Don't connect if no topic is selected
    if (!topic) {
      setConnection('closed')
      return
    }

    const wsUrl = buildWsUrl(topic)
    console.log(`Connecting to WebSocket: ${wsUrl}`)
    
    const socket = new WebSocket(wsUrl)
    socket.binaryType = 'arraybuffer'
    setConnection('connecting')

    socket.addEventListener('open', () => {
      console.log(`WebSocket connected to topic: ${topic}`)
      setConnection('open')
    })

    socket.addEventListener('close', (event) => {
      console.log(`WebSocket closed: code=${event.code}, reason=${event.reason}`)
      setConnection('closed')
    })

    socket.addEventListener('error', (event) => {
      console.error('WebSocket error:', event)
      setConnection('error')
    })

    socket.addEventListener('message', (event) => {
      if (!(event.data instanceof ArrayBuffer)) return
      try {
        const frame = parseLidrFrame(event.data)
        setFrame({
          ...frame,
          summary: formatFrameSummary(frame),
        })
      } catch (error) {
        console.warn('Failed to parse frame', error)
      }
    })

    return () => {
      console.log(`Closing WebSocket for topic: ${topic}`)
      socket.close(1000, 'Topic changed')
    }
  }, [topic, setConnection, setFrame])
}
