/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: 'rgb(var(--color-primary) / <alpha-value>)',
          light: 'rgb(var(--color-primary-light) / <alpha-value>)',
          lighter: 'rgb(var(--color-primary-lighter) / <alpha-value>)',
          dark: 'rgb(var(--color-primary-dark) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--color-secondary) / <alpha-value>)',
          light: 'rgb(var(--color-secondary-light) / <alpha-value>)',
          dark: 'rgb(var(--color-secondary-dark) / <alpha-value>)',
        },
        cta: {
          DEFAULT: 'rgb(var(--color-cta) / <alpha-value>)',
          hover: 'rgb(var(--color-cta-hover) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--color-accent) / <alpha-value>)',
          light: 'rgb(var(--color-accent-light) / <alpha-value>)',
        },
        bg: {
          DEFAULT: 'rgb(var(--color-bg) / <alpha-value>)',
          dark: 'rgb(var(--color-bg-dark) / <alpha-value>)',
          warm: 'rgb(var(--color-bg-warm) / <alpha-value>)',
        },
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          hover: 'rgb(var(--color-surface-hover) / <alpha-value>)',
          dark: 'rgb(var(--color-surface-dark) / <alpha-value>)',
        },
        text: {
          DEFAULT: 'rgb(var(--color-text) / <alpha-value>)',
          muted: 'rgb(var(--color-text-muted) / <alpha-value>)',
          inverse: 'rgb(var(--color-text-inverse) / <alpha-value>)',
          'on-dark': 'rgb(var(--color-text-on-dark) / <alpha-value>)',
          'muted-on-dark': 'rgb(var(--color-text-muted-on-dark) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--color-border) / <alpha-value>)',
          light: 'rgb(var(--color-border-light) / <alpha-value>)',
          dark: 'rgb(var(--color-border-dark) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'rgb(var(--color-error) / <alpha-value>)',
          bg: 'rgb(var(--color-error-bg) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--color-success) / <alpha-value>)',
          bg: 'rgb(var(--color-success-bg) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--color-warning) / <alpha-value>)',
          bg: 'rgb(var(--color-warning-bg) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--color-info) / <alpha-value>)',
          bg: 'rgb(var(--color-info-bg) / <alpha-value>)',
        },
        supervisor: {
          DEFAULT: 'rgb(var(--color-supervisor) / <alpha-value>)',
          light: 'rgb(var(--color-supervisor-light) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        display: ['var(--font-display)'],
        brand: ['var(--font-brand)'],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        full: 'var(--radius-full)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
        note: 'var(--shadow-note)',
        'note-hover': 'var(--shadow-note-hover)',
        'note-float': 'var(--shadow-note-float)',
      },
      animation: {
        'pulse-slow': 'pulse-slow 2.5s ease-in-out infinite',
        'chip-enter': 'chip-enter 0.18s ease-out both',
        'text-rotate-in': 'text-rotate-in 280ms var(--ease-standard) both',
        'stagger-in': 'stagger-in 320ms var(--ease-standard) both',
      },
      keyframes: {
        'pulse-slow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'chip-enter': {
          from: { opacity: '0', transform: 'translateX(-6px) scale(0.9)' },
          to: { opacity: '1', transform: 'translateX(0) scale(1)' },
        },
        'text-rotate-in': {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'stagger-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
