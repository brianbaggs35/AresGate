import { BOTTOM_BAR_LIMIT, bottomBar, navItems } from '@/navigation'
import { routes } from '@/router'

describe('navigation', () => {
  it('opens a route that exists from every item', () => {
    const names = routes.flatMap((route) => route.children ?? [route]).map((route) => route.name)
    for (const item of navItems) expect(names).toContain(item.route)
  })

  it('lists each place once', () => {
    expect(new Set(navItems.map((item) => item.route)).size).toBe(navItems.length)
  })

  it('has a bottom bar that holds all the places while they fit', () => {
    const items = navItems.slice(0, 3)

    expect(bottomBar(items, 5)).toEqual({ bar: items, more: [] })
    expect(bottomBar(navItems.slice(0, 5), 5).more).toEqual([])
  })

  it('puts the places that do not fit behind More, leaving room for its button', () => {
    const { bar, more } = bottomBar(navItems, 5)

    expect(bar).toHaveLength(BOTTOM_BAR_LIMIT - 1)
    expect(new Set([...bar, ...more])).toEqual(new Set(navItems))
    expect(bar.length + more.length).toBe(navItems.length)
    expect(more.length).toBeGreaterThan(0)
  })

  it('keeps a place that asks to be behind More out of the bar, and the rest in their order', () => {
    const { bar, more } = bottomBar(navItems, 5)

    expect(bar.map((item) => item.route)).toEqual(['home', 'threats', 'incidents', 'review'])
    expect(more.map((item) => item.route).slice(0, 2)).toEqual(['incident-response', 'assistant'])
    expect(bar.some((item) => item.behindMore)).toBe(false)
  })

  it('has more behind it than the bar has room for only when it must', () => {
    const items = [
      { route: 'a', title: 'A', icon: 'x' },
      { route: 'b', title: 'B', icon: 'x', behindMore: true },
      { route: 'c', title: 'C', icon: 'x' },
    ]

    expect(bottomBar(items, 3)).toEqual({ bar: items, more: [] })
    expect(bottomBar(items, 2)).toEqual({ bar: [items[0]], more: [items[1], items[2]] })
  })

  it('keeps the places in the order they are listed, Threats next to the Dashboard, Incident response and Review next to Incidents, and the Assistant and Agents after them', () => {
    expect(navItems.map((item) => item.route)).toEqual([
      'home',
      'threats',
      'incidents',
      'incident-response',
      'review',
      'assistant',
      'agents',
      'logs',
      'assets',
      'devices',
      'integrations',
      'threat-intelligence',
      'interfaces',
      'ai-usage',
      'trust',
      'alerts',
      'status',
      'settings',
    ])
  })
})
