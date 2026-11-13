import FamilyCard from '@/components/FamilyCard.vue'
import { mountWithPlugins } from '@/test/mount'
import { family } from '@/test/threats'

async function open(changes = {}) {
  return mountWithPlugins(FamilyCard, { props: { family: family(changes) } })
}

describe('FamilyCard', () => {
  it('says what the kind says, where it is from and how many there are', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="family-title"]').text()).toBe(
      'ET SCAN Potential SSH Scan from <address>',
    )
    expect(wrapper.find('[data-test="family-reach"]').text()).toBe('From the internet')
    expect(wrapper.find('[data-test="family-incidents"]').text()).toBe(
      '41 incidents from 41 addresses',
    )
    expect(wrapper.find('[data-test="family-alerts"]').text()).toBe('3,200 alerts')
    expect(wrapper.find('[data-test="family"]').attributes('href')).toBe('/threats/kinds/7')
  })

  it('counts only the lanes it has incidents in', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="family-threats"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="family-suspects"]').text()).toBe('1 suspect')
    expect(wrapper.find('[data-test="family-background"]').text()).toBe('40 in the background')
  })

  it('says it in the singular', async () => {
    const { wrapper } = await open({ incidents: 1, actors: 1, alerts: 1, threats: 1 })

    expect(wrapper.find('[data-test="family-incidents"]').text()).toBe('1 incident from 1 address')
    expect(wrapper.find('[data-test="family-alerts"]').text()).toBe('1 alert')
    expect(wrapper.find('[data-test="family-threats"]').text()).toBe('1 threat')
  })

  it('shows what the AI made of it', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="family-ai"]').text()).toBe('AI: Probe, 92% sure')
  })

  it('shows your word instead, which comes first', async () => {
    const { wrapper } = await open({ owner_call: 'watch' })

    expect(wrapper.find('[data-test="family-owner"]').text()).toBe('You watch it')
    expect(wrapper.find('[data-test="family-ai"]').exists()).toBe(false)
  })

  it('says it has changed since it was judged only when it has', async () => {
    const { wrapper } = await open()
    expect(wrapper.find('[data-test="family-changed"]').exists()).toBe(false)

    const changed = await open({ changes: ['It comes from many more addresses.'] })

    expect(changed.wrapper.find('[data-test="family-changed"]').text()).toBe('Changed since judged')
  })

  it('says when no one has judged it', async () => {
    const { wrapper } = await open({ classification: null, confidence: null })

    expect(wrapper.find('[data-test="family-waiting"]').text()).toBe('Not judged yet')
  })
})
