import { createMemoryHistory } from 'vue-router'

import { buildRouter, pageTitle, routes } from '@/router'

async function visit(path: string) {
  const router = buildRouter(createMemoryHistory())
  await router.push(path)
  return router.currentRoute.value
}

describe('router', () => {
  it('shows the overview at the root and titles the page', async () => {
    expect((await visit('/')).name).toBe('home')
    expect(document.title).toBe('Overview · AresGate')
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
    expect(pageTitle(await visit('/'))).toBe('Overview')
    expect(pageTitle({ meta: {} })).toBeUndefined()
  })

  it('lazy-loads every view module', async () => {
    const loaders = routes
      .map((route) => route.component)
      .filter((component): component is () => Promise<unknown> => typeof component === 'function')
    expect(loaders).toHaveLength(routes.length)
    const modules = await Promise.all(loaders.map((load) => load()))
    for (const module of modules) expect(module).toHaveProperty('default')
  })
})
