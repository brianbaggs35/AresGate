import { BOTTOM_BAR_LIMIT, navItems } from '@/navigation'
import { routes } from '@/router'

describe('navigation', () => {
  it('opens a route that exists from every item', () => {
    const names = routes.map((route) => route.name)
    for (const item of navItems) expect(names).toContain(item.route)
  })

  it('lists each place once', () => {
    expect(new Set(navItems.map((item) => item.route)).size).toBe(navItems.length)
  })

  // A sixth place needs the phone's bar to make room, e.g. a "More" button that opens the rest
  // in a sheet. Add that, with its tests, along with the sixth item.
  it("has no more places than a phone's bottom bar holds", () => {
    expect(navItems.length).toBeLessThanOrEqual(BOTTOM_BAR_LIMIT)
  })
})
