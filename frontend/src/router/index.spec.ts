import { createMemoryHistory } from 'vue-router'

import { buildRouter, pageTitle, routes } from '@/router'

async function visit(path: string) {
  const router = buildRouter(createMemoryHistory())
  await router.push(path)
  return router.currentRoute.value
}

describe('router', () => {
  it('shows the dashboard at the root and titles the page', async () => {
    expect((await visit('/')).name).toBe('home')
    expect(document.title).toBe('Dashboard · AresGate')
  })

  it('shows the not-found page for any other address', async () => {
    expect((await visit('/no/such/page')).name).toBe('not-found')
    expect(document.title).toBe('Page not found · AresGate')
  })

  it('falls back to the bare name for a route without a title', async () => {
    const router = buildRouter(createMemoryHistory())
    router.addRoute({ path: '/untitled', component: { render: () => null } })
    await router.push('/untitled')
    expect(document.title).toBe('AresGate')
  })

  it("gives a page's title, if it has one", async () => {
    expect(pageTitle(await visit('/'))).toBe('Dashboard')
    expect(pageTitle({ meta: {} })).toBeUndefined()
  })

  it('shows the integrations, and each one’s page, under one title', async () => {
    const list = await visit('/integrations')
    expect(list.name).toBe('integrations')
    expect(pageTitle(list)).toBe('Integrations')
    const one = await visit('/integrations/opnsense')
    expect(one.name).toBe('integration')
    expect(one.params.key).toBe('opnsense')
    expect(document.title).toBe('Integrations · AresGate')
  })

  it('shows the incidents, and each one’s page, under one title', async () => {
    const list = await visit('/incidents')
    expect(list.name).toBe('incidents')
    expect(pageTitle(list)).toBe('Incidents')
    const one = await visit('/incidents/12')
    expect(one.name).toBe('incident')
    expect(one.params.id).toBe('12')
    expect(document.title).toBe('Incidents · AresGate')
  })

  it('shows an address that is not a number as a page that is not there', async () => {
    expect((await visit('/incidents/twelve')).name).toBe('not-found')
  })

  it('lazy-loads every view module', async () => {
    const records = routes.flatMap((route) => [route, ...(route.children ?? [])])
    const loaders = records
      .map((route) => route.component)
      .filter((component): component is () => Promise<unknown> => typeof component === 'function')
    // A route shows a view, goes on to one that does, or only groups others under one address.
    const grouping = (route: (typeof records)[number]) => route.children && !route.component
    expect(loaders).toHaveLength(
      records.filter((route) => !route.redirect && !grouping(route)).length,
    )
    const modules = await Promise.all(loaders.map((load) => load()))
    for (const module of modules) expect(module).toHaveProperty('default')
  })

  it('shows the status page under its own title', async () => {
    const page = await visit('/status')
    expect(page.name).toBe('status')
    expect(pageTitle(page)).toBe('Status')
    expect(document.title).toBe('Status · AresGate')
  })

  it('shows the settings pages under one title', async () => {
    for (const [path, name] of [
      ['/settings/account', 'settings-account'],
      ['/settings/sign-ins', 'settings-sign-ins'],
      ['/settings/activity', 'settings-activity'],
      ['/settings/verdicts', 'settings-verdicts'],
      ['/settings/ai', 'settings-ai'],
      ['/settings/data', 'settings-data'],
    ] as const) {
      const page = await visit(path)
      expect(page.name).toBe(name)
      expect(pageTitle(page)).toBe('Settings')
    }
    expect(document.title).toBe('Settings · AresGate')
  })

  it('opens the account settings from the settings address, and from the old security one', async () => {
    expect((await visit('/settings')).name).toBe('settings-account')
    expect((await visit('/security')).name).toBe('settings-account')
  })
})
