import { COMMANDS, GROUPS, commandsFor, shortcutLabel } from '@/commands'
import { navItems } from '@/navigation'
import { settingsSections } from '@/settings'

const ids = (search: string) => commandsFor(search).map(({ id }) => id)

describe('the commands', () => {
  it('has every page in the menu, and every page of Settings by name', () => {
    const found = COMMANDS.map(({ id }) => id)
    for (const { route } of navItems.filter(({ route }) => route !== 'settings')) {
      expect(found).toContain(`go-${route}`)
    }
    for (const { key } of settingsSections) expect(found).toContain(`go-settings-${key}`)
    // Settings itself only opens its first page, which is already listed.
    expect(found).not.toContain('go-settings')
  })

  it('has a way to look at each group of incidents, and each theme', () => {
    const found = COMMANDS.map(({ id }) => id)
    expect(found).toContain('incidents-all')
    expect(found).toContain('incidents-resolved')
    expect(found).toEqual(expect.arrayContaining(['theme-light', 'theme-dark', 'theme-system']))
  })

  it('has a different id for each, since the palette keys its list by it', () => {
    expect(new Set(COMMANDS.map(({ id }) => id)).size).toBe(COMMANDS.length)
  })
})

describe('commandsFor', () => {
  it('lists everything, by group, for an empty search', () => {
    const all = commandsFor('   ')
    expect(all).toHaveLength(COMMANDS.length)
    const order = all.map(({ group }) => GROUPS.indexOf(group as (typeof GROUPS)[number]))
    expect(order).toEqual([...order].sort((a, b) => a - b))
  })

  it('narrows to what has every word that was typed, in any case', () => {
    expect(ids('INCIDENTS')).toContain('go-incidents')
    expect(ids('show resolved')).toEqual(['incidents-resolved'])
    expect(ids('resolved show')).toEqual(['incidents-resolved'])
  })

  it('finds by words that are not shown', () => {
    expect(ids('preferences')).toEqual(settingsSections.map(({ key }) => `go-settings-${key}`))
    expect(ids('mode')).toEqual(['theme-light', 'theme-dark', 'theme-system'])
  })

  it('puts a title that starts with the search first, then one that has it, then the rest', () => {
    // "Incidents" starts with it, and "Show … incidents" only has it.
    const found = ids('incidents')
    expect(found[0]).toBe('go-incidents')
    expect(found.slice(1)).toEqual([
      'incidents-active',
      'incidents-open',
      'incidents-investigating',
      'incidents-resolved',
      'incidents-dismissed',
      'incidents-all',
    ])
    // A word in the keywords only comes after one in a title.
    expect(commandsFor('list').every(({ group }) => group === 'Incidents')).toBe(true)
    expect(ids('theme dark')[0]).toBe('theme-dark')
  })

  it('finds nothing for what matches nothing', () => {
    expect(commandsFor('zzzz')).toEqual([])
  })

  it('offers to look for an address that was typed whole, before the rest', () => {
    const [first, ...rest] = commandsFor(' 93.184.216.34 ')
    expect(first).toMatchObject({
      id: 'incidents-address',
      group: 'Incidents',
      title: 'Find incidents about 93.184.216.34',
      action: {
        kind: 'go',
        to: { name: 'incidents', query: { view: 'all', address: '93.184.216.34' } },
      },
    })
    expect(rest).toEqual([])
    expect(commandsFor('2001:db8::1')[0]?.title).toBe('Find incidents about 2001:db8::1')
  })

  it('does not offer one for an address that is not whole yet', () => {
    expect(commandsFor('93.184')).toEqual([])
    expect(ids('93.184.216')).not.toContain('incidents-address')
  })
})

describe('shortcutLabel', () => {
  it('is ⌘K on Apple computers and phones', () => {
    expect(shortcutLabel('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe('⌘K')
    expect(shortcutLabel('Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)')).toBe('⌘K')
  })

  it('is Ctrl K on the rest', () => {
    expect(shortcutLabel('Mozilla/5.0 (X11; Linux x86_64)')).toBe('Ctrl K')
    expect(shortcutLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('Ctrl K')
  })
})
