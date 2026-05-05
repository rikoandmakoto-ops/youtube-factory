import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#0f172a',
          card: '#1e293b',
          elev: '#273449',
        },
        accent: {
          DEFAULT: '#3b82f6',
          hover: '#2563eb',
        },
        border: {
          DEFAULT: '#334155',
        },
      },
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Hiragino Sans"',
          '"Noto Sans JP"',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};

export default config;
