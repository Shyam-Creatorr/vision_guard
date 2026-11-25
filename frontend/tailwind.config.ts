import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        apple: {
          DEFAULT: 'var(--vg-apple)',
          light: 'var(--vg-apple-light)',
          dark: 'var(--vg-apple-dark)',
        },
        sky: {
          DEFAULT: 'var(--vg-sky)',
          light: 'var(--vg-sky-light)',
          dark: 'var(--vg-sky-dark)',
        },
        mango: {
          DEFAULT: 'var(--vg-mango)',
          light: 'var(--vg-mango-light)',
          dark: 'var(--vg-mango-dark)',
        },
        beige: {
          DEFAULT: 'var(--vg-beige)',
          deep: 'var(--vg-beige-deep)',
        },
        ink: 'var(--vg-black)',
        pure: 'var(--vg-white)',
        grey: {
          50: 'var(--vg-grey-50)',
          300: 'var(--vg-grey-300)',
          500: 'var(--vg-grey-500)',
          700: 'var(--vg-grey-700)',
        },
        surface: {
          page: 'var(--vg-surface-page)',
          elevated: 'var(--vg-surface-elevated)',
          glass: 'var(--vg-surface-glass)',
          clay: 'var(--vg-surface-clay)',
        },
        text: {
          primary: 'var(--vg-text-primary)',
          secondary: 'var(--vg-text-secondary)',
          muted: 'var(--vg-text-muted)',
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', '"Sora"', 'system-ui', 'sans-serif'],
        sans: ['"Inter"', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        clay: '24px',
        'clay-sm': '20px',
        'clay-lg': '28px',
      },
      boxShadow: {
        clay: 'var(--vg-shadow-clay)',
        glass: 'var(--vg-shadow-glass)',
        'soft-lg': 'var(--vg-shadow-soft-lg)',
      },
      spacing: {
        18: '4.5rem',
        22: '5.5rem',
      },
    },
  },
  plugins: [],
};

export default config;
