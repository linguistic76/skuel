/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./ui/**/*.py",
    "./adapters/inbound/**/*.py",
    "./components/**/*.py",
    "./templates/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Semantic color tokens
        surface: {
          DEFAULT: 'var(--surface)',
          secondary: 'var(--surface-secondary)',
          elevated: 'var(--surface-elevated)',
        },
        border: {
          DEFAULT: 'var(--border)',
          muted: 'var(--border-muted)',
        },
        content: {
          DEFAULT: 'var(--content)',
          secondary: 'var(--content-secondary)',
          muted: 'var(--content-muted)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
        },
        status: {
          success: 'var(--status-success)',
          warning: 'var(--status-warning)',
          error: 'var(--status-error)',
          info: 'var(--status-info)',
        },
      },
      // Typography plugin configuration (Syntax-style)
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            // Base colors
            '--tw-prose-body': '#374151',        // gray-700
            '--tw-prose-headings': '#111827',    // gray-900
            '--tw-prose-lead': '#4b5563',        // gray-600
            '--tw-prose-links': '#2563eb',       // blue-600
            '--tw-prose-bold': '#111827',        // gray-900
            '--tw-prose-counters': '#6b7280',    // gray-500
            '--tw-prose-bullets': '#9ca3af',     // gray-400
            '--tw-prose-hr': '#e5e7eb',          // gray-200
            '--tw-prose-quotes': '#374151',      // gray-700
            '--tw-prose-quote-borders': '#2563eb', // blue-600
            '--tw-prose-captions': '#6b7280',    // gray-500
            '--tw-prose-code': '#111827',        // gray-900
            '--tw-prose-pre-code': '#e5e7eb',    // gray-200
            '--tw-prose-pre-bg': '#1f2937',      // gray-800
            '--tw-prose-th-borders': '#d1d5db',  // gray-300
            '--tw-prose-td-borders': '#e5e7eb',  // gray-200

            // Line height for readability
            lineHeight: '1.75',

            // Headings
            'h1': {
              fontSize: '2.25rem',
              fontWeight: '700',
              letterSpacing: '-0.025em',
              marginTop: '0',
              marginBottom: '0.875rem',
            },
            'h2': {
              fontSize: '1.5rem',
              fontWeight: '600',
              letterSpacing: '-0.025em',
              marginTop: '2rem',
              marginBottom: '1rem',
              paddingBottom: '0.5rem',
              borderBottomWidth: '1px',
              borderBottomColor: 'var(--tw-prose-hr)',
            },
            'h3': {
              fontSize: '1.25rem',
              fontWeight: '600',
              marginTop: '1.75rem',
              marginBottom: '0.75rem',
            },
            'h4': {
              fontSize: '1.125rem',
              fontWeight: '600',
              marginTop: '1.5rem',
              marginBottom: '0.5rem',
            },

            // Links
            'a': {
              color: 'var(--tw-prose-links)',
              textDecoration: 'underline',
              textDecorationColor: '#93c5fd', // blue-300
              textUnderlineOffset: '2px',
              fontWeight: '500',
              '&:hover': {
                color: '#1d4ed8', // blue-700
                textDecorationColor: '#1d4ed8',
              },
            },

            // Inline code
            'code': {
              backgroundColor: '#f3f4f6', // gray-100
              color: '#be185d',           // pink-700
              padding: '0.125rem 0.375rem',
              borderRadius: '0.25rem',
              fontSize: '0.875em',
              fontWeight: '500',
              '&::before': { content: 'none' },
              '&::after': { content: 'none' },
            },

            // Code blocks
            'pre': {
              backgroundColor: 'var(--tw-prose-pre-bg)',
              color: 'var(--tw-prose-pre-code)',
              padding: '1rem 1.25rem',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
              lineHeight: '1.7',
              overflowX: 'auto',
            },
            'pre code': {
              backgroundColor: 'transparent',
              color: 'inherit',
              padding: '0',
              borderRadius: '0',
              fontSize: 'inherit',
              fontWeight: '400',
            },

            // Blockquotes
            'blockquote': {
              borderLeftColor: 'var(--tw-prose-quote-borders)',
              borderLeftWidth: '4px',
              paddingLeft: '1rem',
              fontStyle: 'italic',
              color: 'var(--tw-prose-quotes)',
            },
            'blockquote p:first-of-type::before': { content: 'none' },
            'blockquote p:last-of-type::after': { content: 'none' },

            // Lists
            'ul': {
              paddingLeft: '1.5rem',
            },
            'ol': {
              paddingLeft: '1.5rem',
            },
            'li': {
              marginTop: '0.375rem',
              marginBottom: '0.375rem',
            },

            // Tables
            'table': {
              width: '100%',
            },
            'thead': {
              borderBottomWidth: '2px',
              borderBottomColor: 'var(--tw-prose-th-borders)',
            },
            'th': {
              padding: '0.75rem 1rem',
              textAlign: 'left',
              fontWeight: '600',
            },
            'td': {
              padding: '0.75rem 1rem',
              borderBottomWidth: '1px',
              borderBottomColor: 'var(--tw-prose-td-borders)',
            },
            'tbody tr:hover': {
              backgroundColor: '#f9fafb', // gray-50
            },

            // Images
            'img': {
              borderRadius: '0.5rem',
            },

            // Horizontal rules
            'hr': {
              borderTopColor: 'var(--tw-prose-hr)',
              marginTop: '2rem',
              marginBottom: '2rem',
            },
          },
        },
        // Large size variant
        lg: {
          css: {
            fontSize: '1.125rem',
            lineHeight: '1.75',
            'h1': {
              fontSize: '2.5rem',
            },
            'h2': {
              fontSize: '1.75rem',
            },
            'h3': {
              fontSize: '1.375rem',
            },
          },
        },
      }),
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('daisyui'),
  ],
  daisyui: {
    themes: ["light", "dark"],
    darkTheme: "dark",
  },
}
