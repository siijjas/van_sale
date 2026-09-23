/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        // Semantic tokens — driven by CSS variables (see index.css).
        // Use the `/<alpha>` modifier for soft fills, e.g. bg-success/10.
        background: 'rgb(var(--c-background) / <alpha-value>)',
        elevated: 'rgb(var(--c-elevated) / <alpha-value>)',
        card: 'rgb(var(--c-card) / <alpha-value>)',
        'card-muted': 'rgb(var(--c-card-muted) / <alpha-value>)',
        foreground: 'rgb(var(--c-foreground) / <alpha-value>)',
        muted: 'rgb(var(--c-muted) / <alpha-value>)',
        subtle: 'rgb(var(--c-subtle) / <alpha-value>)',
        line: 'rgb(var(--c-line) / <alpha-value>)',
        'line-strong': 'rgb(var(--c-line-strong) / <alpha-value>)',
        input: 'rgb(var(--c-input) / <alpha-value>)',
        ring: 'rgb(var(--c-ring) / <alpha-value>)',
        primary: {
          DEFAULT: 'rgb(var(--c-primary) / <alpha-value>)',
          fg: 'rgb(var(--c-primary-fg) / <alpha-value>)',
          soft: 'rgb(var(--c-primary-soft) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--c-success) / <alpha-value>)',
          fg: 'rgb(var(--c-success-fg) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--c-warning) / <alpha-value>)',
          fg: 'rgb(var(--c-warning-fg) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--c-danger) / <alpha-value>)',
          fg: 'rgb(var(--c-danger-fg) / <alpha-value>)',
        },
        info: {
          DEFAULT: 'rgb(var(--c-info) / <alpha-value>)',
          fg: 'rgb(var(--c-info-fg) / <alpha-value>)',
        },
      },
      borderRadius: {
        // Tightened one full step — reads as a field tool, not a consumer app.
        lg: '0.5rem', // 8
        xl: '0.625rem', // 10 — icon tiles, inner chips
        '2xl': '0.75rem', // 12 — buttons, inputs
        '3xl': '0.875rem', // 14 — cards, sheets-on-desktop
        '4xl': '1.25rem', // 20 — bottom-sheet top corners
      },
      boxShadow: {
        // Theme-aware elevation (variables flip in dark mode).
        card: 'var(--shadow-card)',
        raised: 'var(--shadow-raised)',
        pop: 'var(--shadow-pop)',
        btn: 'var(--shadow-btn)',
      },
      spacing: {
        // Field-ergonomic touch targets — nudged up from 44/52/60.
        touch: '2.875rem', // 46px
        'touch-lg': '3.375rem', // 54px — primary actions
        'touch-xl': '3.875rem', // 62px — hero CTAs
      },
      fontFamily: {
        sans: ['Geist', 'Inter var', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['Geist Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      letterSpacing: {
        tightest: '-0.03em',
      },
      transitionTimingFunction: {
        emphasis: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      },
      keyframes: {
        'sheet-up': {
          from: { transform: 'translateY(100%)' },
          to: { transform: 'translateY(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'sheet-up': 'sheet-up 0.28s cubic-bezier(0.2, 0.8, 0.2, 1)',
        'fade-in': 'fade-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
