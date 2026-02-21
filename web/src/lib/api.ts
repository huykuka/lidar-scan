import axios from 'axios'

/**
 * API Configuration
 * 
 * In development: Set VITE_API_HOST to your backend URL (e.g., http://localhost:8004)
 * In production: Leave empty to use same origin
 */

// Get base URL from environment or default to same origin
const getBaseUrl = (): string => {
  const apiHost = import.meta.env.VITE_API_HOST
  if (apiHost) {
    return apiHost.replace(/\/+$/, '') // Remove trailing slashes
  }
  // Production: use same origin
  return ''
}

const baseURL = getBaseUrl()

// Log configuration in development
if (import.meta.env.DEV) {
  console.log('[API] Base URL:', baseURL || '(same origin)')
}

// Create axios instance with base configuration
export const api = axios.create({
  baseURL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Build WebSocket URL from the same base host
 * Automatically converts http(s) to ws(s)
 */
export const buildWsUrl = (topic: string): string => {
  const apiHost = import.meta.env.VITE_API_HOST
  
  if (apiHost) {
    // Convert http(s) to ws(s)
    const wsHost = apiHost
      .replace(/^http:/, 'ws:')
      .replace(/^https:/, 'wss:')
      .replace(/\/+$/, '')
    const url = `${wsHost}/ws/${topic}`
    if (import.meta.env.DEV) {
      console.log('[WebSocket] URL:', url)
    }
    return url
  }
  
  // Production: derive from current origin
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/${topic}`
}

// Type definitions for API responses
export interface TopicsResponse {
  topics: string[]
}

export interface StatusResponse {
  version: string
}
