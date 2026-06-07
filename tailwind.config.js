/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,js}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        elevated: 'var(--color-bg-elevated)',
        primary: 'var(--color-text-primary)',
        secondary: 'var(--color-text-secondary)',
        accent: 'var(--color-accent)',
      },
      fontFamily: {
        ui: 'var(--font-ui)',
        diary: 'var(--font-diary)',
      },
      borderRadius: {
        outer: 'var(--radius-outer)',
        inner: 'var(--radius-inner)',
      },
    },
  },
  plugins: [],
}
