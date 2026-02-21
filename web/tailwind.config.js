import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"Space Mono"', 'monospace'],
      },
      colors: {
        synergy: {
          primary: '#00BAC7',
          secondary: '#0B1224',
          accent: '#83f8ff',
          panel: '#0f172a',
          border: 'rgba(131,208,255,.24)',
        },
      },
    },
  },
  plugins: [animate],
}
