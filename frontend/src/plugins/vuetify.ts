import '@fontsource-variable/inter'
import 'vuetify/styles'
import '@/styles/main.scss'
import '@/styles/charts.scss'

import { createVuetify, type ThemeDefinition } from 'vuetify'

import { aliases, lucide } from '@/plugins/icons'

const light: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#f4f6fa',
    surface: '#ffffff',
    'surface-variant': '#e6ebf2',
    'on-surface-variant': '#334155',
    // Dark enough for white text on each colour, and for each colour's text on its own tonal
    // tint, to meet WCAG AA contrast (4.5:1).
    primary: '#0e7490',
    secondary: '#5b21b6',
    accent: '#854d0e',
    success: '#157439',
    info: '#0369a1',
    warning: '#a54a0b',
    error: '#b91c1c',
    // The logo's red, dark enough for text on white (5.5:1).
    brand: '#d11229',
  },
  variables: {
    // Vuetify's 0.6 leaves field labels, hints and subtitles, which it dims twice, below
    // WCAG AA contrast (4.5:1) on white. The dark theme already uses 0.7.
    'medium-emphasis-opacity': 0.7,
  },
}

// The "mission control" theme: deep navy surfaces with cyan and violet lit up against them.
const dark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#070b14',
    surface: '#0e1626',
    'surface-variant': '#1b2740',
    'on-surface-variant': '#cbd5e1',
    primary: '#22d3ee',
    secondary: '#a78bfa',
    accent: '#fbbf24',
    success: '#34d399',
    info: '#60a5fa',
    warning: '#fbbf24',
    error: '#f87171',
    // The logo's red, lifted to read as text on the dark surfaces (5:1).
    brand: '#ff3b4a',
    // Vuetify would put white on these light colours, which is hard to read.
    'on-primary': '#04141a',
    'on-error': '#000000',
  },
}

export function buildVuetify() {
  return createVuetify({
    theme: { defaultTheme: 'system', themes: { light, dark } },
    icons: { defaultSet: 'lucide', aliases, sets: { lucide } },
    defaults: {
      VCard: { rounded: 'xl', elevation: 0, border: true },
      VBtn: { rounded: 'lg', style: 'text-transform: none; letter-spacing: normal' },
      VTextField: { variant: 'outlined', density: 'comfortable' },
      VSelect: { variant: 'outlined', density: 'comfortable' },
      VChip: { rounded: 'lg' },
    },
  })
}
