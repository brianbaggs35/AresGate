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
    expect([...bar, ...more]).toEqual(navItems)
    expect(more.length).toBeGreaterThan(0)
  })

  it('keeps Logs in the menu, between Incidents and Integrations', () => {
    expect(navItems.map((item) => item.route)).toEqual([
      'home',
      'incidents',
      'logs',
      'integrations',
      'status',
      'settings',
    ])
  })
})
