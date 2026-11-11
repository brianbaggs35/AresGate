import AgentSetup from '@/components/AgentSetup.vue'
import { check, template } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(item = template()) {
  return mountWithPlugins(AgentSetup, { props: { template: item } })
}

describe('AgentSetup', () => {
  it('says everything is set up when nothing is missing', async () => {
    const { wrapper } = await open(template({ checks: [check()], ready: true }))

    expect(wrapper.find('[data-test="setup-title"]').text()).toBe('Everything it needs is set up')
    expect(wrapper.find('[data-test="setup-check"]').text()).toContain(': ready')
    expect(wrapper.find('[data-test="setup-link"]').exists()).toBe(false)
  })

  it('says what is missing, what to do about it, and where', async () => {
    const { wrapper } = await open(
      template({
        ready: false,
        checks: [check({ ok: false, fix: 'Add a free VirusTotal key.' })],
      }),
    )

    expect(wrapper.find('[data-test="setup-title"]').text()).toBe('It needs a little setup first')
    const row = wrapper.find('[data-test="setup-check"]')
    expect(row.text()).toContain(': missing')
    expect(row.text()).toContain('Add a free VirusTotal key.')
    expect(wrapper.find('[data-test="setup-link"]').attributes('href')).toBe(
      '/integrations/virustotal',
    )
  })

  it('lists the steps to set it up in order', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('[data-test="setup-step"]').map((step) => step.text())).toEqual([
      'Connect an integration.',
      'Start it once by hand.',
    ])
  })

  it('leaves out what it has nothing to say about', async () => {
    const { wrapper } = await open(template({ checks: [], setup: [] }))

    expect(wrapper.find('[data-test="setup-check"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="setup-steps"]').exists()).toBe(false)
  })
})
