import '@testing-library/jest-dom/vitest'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => true,
  }),
})

globalThis.requestAnimationFrame = (cb: FrameRequestCallback) => setTimeout(() => cb(Date.now()), 16)
globalThis.cancelAnimationFrame = (id: number) => clearTimeout(id)
