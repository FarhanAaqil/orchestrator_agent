/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: { dark: '#1B2632', light: '#EEE9DF' },
        surface: { primary: '#2C3B4D', muted: '#C9C1B1' },
        accent: { primary: '#FFB162' },
        state: { warning: '#A35139', success: '#5A8A6B', danger: '#B4453A' },
        text: { primary: '#EEE9DF', onLight: '#1B2632', muted: '#7C8A99' },
      },
      borderRadius: {
        pill: '999px',
      },
    },
  },
  plugins: [],
};
