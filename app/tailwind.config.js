/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./ui/**/*.py",
    "./adapters/inbound/**/*.py",
    "./components/**/*.py",
    "./ui/components/**/*.py",
    "./static/js/*.js",
    "./templates/**/*.html",
  ],
  safelist: [
    { pattern: /^gap-(0|1|2|3|4|5|6|8|10|12|16)$/ },
    { pattern: /^grid-cols-(1|2|3|4|5|6)$/ },
    { pattern: /^items-(start|center|end|stretch|baseline)$/ },
    'flex-grow', 'flex-shrink', 'flex-shrink-0',
    { pattern: /^max-w-(sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl)$/ },
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Base semantic tokens — components reference these via bg-primary, bg-card etc.
        // Values are hsl() wrappers over CSS vars owned by input.css; DaisyUI still
        // provides runtime fallbacks until Phase 2 removes it.
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',

        // SKUEL domain tokens — merged with shadcn/ui base tokens where names overlap
        surface: {
          DEFAULT: 'var(--surface)',
          secondary: 'var(--surface-secondary)',
          elevated: 'var(--surface-elevated)',
        },
        border: {
          DEFAULT: 'hsl(var(--border))',
          muted: 'var(--border-muted)',
        },
        content: {
          DEFAULT: 'var(--content)',
          secondary: 'var(--content-secondary)',
          muted: 'var(--content-muted)',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
          hover: 'var(--accent-hover)',
        },
        status: {
          success: 'var(--status-success)',
          warning: 'var(--status-warning)',
          error: 'var(--status-error)',
          info: 'var(--status-info)',
        },
        // Priority accents — mirrors main.css .border-priority-* oklch values.
        // Used on Today ribbons for dot indicators and optional fills.
        priority: {
          high:   'oklch(0.65 0.20 25)',
          medium: 'oklch(0.75 0.15 85)',
          low:    'oklch(0.70 0.15 145)',
        },
        // Principle strength accents — oklch analogues of palette.py StrengthColor.
        strength: {
          core:       'oklch(0.55 0.22 295)',
          strong:     'oklch(0.55 0.20 255)',
          developing: 'oklch(0.60 0.15 165)',
        },
      },
      boxShadow: {
        // Soft 2px ring matching hsl(var(--ring) / 0.2) — used as focus ring.
        focus: '0 0 0 2px hsl(var(--ring) / 0.2)',
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
    themes: true,
    darkTheme: "dark",
  },
}
