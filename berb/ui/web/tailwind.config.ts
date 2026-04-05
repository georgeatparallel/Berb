import type { Config } from 'tailwindcss';

export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: 'var(--berb-background)',
        surface: 'var(--berb-surface)',
        surfaceHover: 'var(--berb-surfaceHover)',
        border: 'var(--berb-border)',
        borderSubtle: 'var(--berb-borderSubtle)',
        textPrimary: 'var(--berb-textPrimary)',
        textSecondary: 'var(--berb-textSecondary)',
        textTertiary: 'var(--berb-textTertiary)',
        textInverse: 'var(--berb-textInverse)',
        accent: 'var(--berb-accent)',
        accentHover: 'var(--berb-accentHover)',
        accentActive: 'var(--berb-accentActive)',
        accentLight: 'var(--berb-accentLight)',
        success: 'var(--berb-success)',
        successLight: 'var(--berb-successLight)',
        warning: 'var(--berb-warning)',
        warningLight: 'var(--berb-warningLight)',
        error: 'var(--berb-error)',
        errorLight: 'var(--berb-errorLight)',
        stageComplete: 'var(--berb-stageComplete)',
        stageRunning: 'var(--berb-stageRunning)',
        stagePending: 'var(--berb-stagePending)',
        stageError: 'var(--berb-stageError)',
        stagePaused: 'var(--berb-stagePaused)',
        citationSupporting: 'var(--berb-citationSupporting)',
        citationContrasting: 'var(--berb-citationContrasting)',
        citationMentioning: 'var(--berb-citationMentioning)',
        codeBackground: 'var(--berb-codeBackground, #F5F5F7)',
        codeText: 'var(--berb-codeText, #1D1D1F)',
      },
      fontFamily: {
        sans: ['-apple-system', 'SF Pro Display', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"SF Mono"', 'Fira Code', 'Consolas', 'Monaco', 'monospace'],
        serif: ['Georgia', '"Times New Roman"', 'serif'],
      },
      spacing: {
        '0': '0px',
        '1': '4px',
        '2': '8px',
        '3': '16px',
        '4': '24px',
        '5': '32px',
        '6': '48px',
        '8': '64px',
      },
      borderRadius: {
        sm: '6px',
        md: '10px',
        lg: '14px',
        xl: '20px',
        pill: '100px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(0,0,0,0.04)',
        md: '0 2px 8px rgba(0,0,0,0.08)',
        lg: '0 8px 30px rgba(0,0,0,0.12)',
        xl: '0 12px 40px rgba(0,0,0,0.16)',
        focus: '0 0 0 4px rgba(0,113,227,0.3)',
        inset: 'inset 0 1px 3px rgba(0,0,0,0.06)',
      },
      animation: {
        'fade-in': 'fadeIn 300ms ease-out',
        'fade-in-up': 'fadeInUp 300ms ease-out',
        'fade-in-down': 'fadeInDown 300ms ease-out',
        'slide-in-left': 'slideInLeft 300ms ease-out',
        'slide-in-right': 'slideInRight 300ms ease-out',
        'slide-in-up': 'slideInUp 300ms ease-out',
        'slide-in-down': 'slideInDown 300ms ease-out',
        'bounce-spring': 'bounceSpring 400ms cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeInDown: {
          '0%': { opacity: '0', transform: 'translateY(-20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInDown: {
          '0%': { opacity: '0', transform: 'translateY(-20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        bounceSpring: {
          '0%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
          '100%': { transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [
    // Add custom utilities for border and background colors
    function({ addUtilities, theme }: any) {
      addUtilities({
        '.border-border': {
          'border-color': theme('colors.border'),
        },
        '.bg-background': {
          'background-color': theme('colors.background'),
        },
        '.text-textPrimary': {
          'color': theme('colors.textPrimary'),
        },
        '.text-textSecondary': {
          'color': theme('colors.textSecondary'),
        },
        '.text-textTertiary': {
          'color': theme('colors.textTertiary'),
        },
        '.bg-surface': {
          'background-color': theme('colors.surface'),
        },
        '.bg-surfaceHover': {
          'background-color': theme('colors.surfaceHover'),
        },
        '.bg-accentLight': {
          'background-color': theme('colors.accentLight'),
        },
        '.bg-successLight': {
          'background-color': theme('colors.successLight'),
        },
        '.bg-warningLight': {
          'background-color': theme('colors.warningLight'),
        },
        '.bg-errorLight': {
          'background-color': theme('colors.errorLight'),
        },
      });
    },
  ],
} satisfies Config;
