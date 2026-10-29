/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        velora: {
          void: '#090A0C',
          obsidian: '#303236',
          charcoal: '#111111',
          slate: '#4A4B50',
          muted: '#95979E',
          secondary: '#A9A9AA',
          light: '#FFFFFF',
          linen: '#E5E5E7',
          iris: '#5683DA',
          ember: '#FF8964',
          'deep-ember': '#5A250A',
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          300: '#7cc7fb',
          400: '#36abf6',
          500: '#0c8ee7',
          600: '#0270c5',
          700: '#03599f',
          800: '#074c83',
          900: '#0b3f6d',
          950: '#072848',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Sora', 'Inter', 'system-ui', 'sans-serif'],
      },
      minHeight: {
        touch: '44px',
      },
      minWidth: {
        touch: '44px',
      },
    },
  },
  plugins: [],
};
