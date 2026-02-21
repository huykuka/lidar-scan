/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 
   * API host for development (e.g., http://localhost:8004)
   * WebSocket URL is automatically derived by converting http(s) to ws(s)
   */
  readonly VITE_API_HOST?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
