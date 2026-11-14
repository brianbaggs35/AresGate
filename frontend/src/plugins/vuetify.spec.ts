import { buildVuetify } from '@/plugins/vuetify'

/** Every stylesheet and template in the app, as text. */
const sources = import.meta.glob<string>('../**/*.{vue,scss,css,ts}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

// What Vuetify itself puts in the page for a theme besides its colours.
const VUETIFY_OWN = new Set(['overlay-multiplier'])

describe('the theme colours the app draws with', () => {
  it('are all ones the themes define', () => {
    const themes = buildVuetify().theme.themes.value
    const colours = [
      ...Object.keys(themes.light?.colors ?? {}),
      ...Object.keys(themes.dark?.colors ?? {}),
    ]
    // Vuetify also makes an `on-` colour, the one to write on it, for each colour there is.
    const defined = new Set([...colours, ...colours.map((name) => `on-${name}`), ...VUETIFY_OWN])
    const unknown: string[] = []
    for (const [file, text] of Object.entries(sources)) {
      if (file.endsWith('.spec.ts')) continue
      for (const [, name] of text.matchAll(/--v-theme-([a-z][a-z0-9-]*)/g)) {
        // A colour that is not in the theme makes the whole declaration invalid at computed-value
        // time, so a border drawn with it is dropped and nothing says why.
        if (name && !defined.has(name)) unknown.push(`${file}: --v-theme-${name}`)
      }
    }

    expect(unknown).toEqual([])
  })

  it('have the ones the app leans on most, so the check can be trusted', () => {
    const themes = buildVuetify().theme.themes.value

    expect(Object.keys(themes.light?.colors ?? {})).toEqual(
      expect.arrayContaining(['primary', 'surface', 'surface-variant', 'error', 'background']),
    )
    expect(Object.keys(themes.light?.colors ?? {})).not.toContain('outline-variant')
  })
})
