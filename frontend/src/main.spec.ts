describe('main', () => {
  // Loads the whole app, which takes a few seconds, and longer on a busy machine.
  it('mounts the app on #app', { timeout: 30_000 }, async () => {
    const root = document.createElement('div')
    root.id = 'app'
    document.body.appendChild(root)
    const { mountApp } = await import('@/main')
    await vi.waitFor(() => {
      expect(root.querySelector('.v-application')).not.toBeNull()
    })

    const other = document.createElement('div')
    other.id = 'other'
    document.body.appendChild(other)
    const app = mountApp('#other')
    expect(other.querySelector('.v-application')).not.toBeNull()
    app.unmount()
  })
})
