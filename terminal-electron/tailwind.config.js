/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        nock: {
          // Deeper near-black with faintest blue cast
          bg: '#08080D',
          'bg-elevated': '#0C0C14',
          card: '#0E0E16',
          'card-hover': '#13131E',
          border: '#1A1A2A',
          'border-bright': '#262640',
          // Primary brand gradient (matches logo)
          'accent-blue': '#3B6FD4',
          'accent-purple': '#7C5CFC',
          'accent-cyan': '#00E5FF',  // live/active telemetry
          'accent-amber': '#FFB020', // warnings
          // Text
          text: '#E8E8F0',
          'text-dim': '#8A8AA0',
          'text-muted': '#4A4A5E',
          // Status
          green: '#34D399',
          yellow: '#FBBF24',
          red: '#F87171',
        },
      },
      fontFamily: {
        sans: ['Sora', 'system-ui', 'sans-serif'],
        display: ['"Chakra Petch"', 'Sora', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      fontSize: {
        // Tighter, more editorial defaults
        'xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
        'sm': ['0.8125rem', { lineHeight: '1.25rem' }],
      },
      letterSpacing: {
        'widest-plus': '0.18em',
      },
      boxShadow: {
        'glow-blue': '0 0 20px -4px rgba(59, 111, 212, 0.4)',
        'glow-purple': '0 0 20px -4px rgba(124, 92, 252, 0.4)',
        'glow-green': '0 0 12px -2px rgba(52, 211, 153, 0.5)',
        'glow-cyan': '0 0 16px -2px rgba(0, 229, 255, 0.45)',
        'card-hover': '0 20px 40px -20px rgba(59, 111, 212, 0.25), 0 0 0 1px rgba(124, 92, 252, 0.15) inset',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out forwards',
        'slide-up': 'slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'pulse-glow': 'pulseGlow 2.5s ease-in-out infinite',
        'grid-scan': 'gridScan 8s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '1', filter: 'brightness(1)' },
          '50%': { opacity: '0.6', filter: 'brightness(1.3)' },
        },
        gridScan: {
          '0%': { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '0% 100%' },
        },
      },
    },
  },
  plugins: [],
};
