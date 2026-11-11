import ChainCard from '@/components/ChainCard.vue'
import { mountWithPlugins } from '@/test/mount'
import { chain } from '@/test/threats'

async function open(changes = {}) {
  return mountWithPlugins(ChainCard, { props: { chain: chain(changes) } })
}

describe('ChainCard', () => {
  it('names the device, says what happened and leads to the chain', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="chain-device"]').text()).toBe('Kitchen camera (192.168.1.20)')
    expect(wrapper.find('[data-test="chain-summary"]').text()).toBe(
      '93.184.216.34 attacked 192.168.1.20, which then called 8.8.4.4.',
    )
    expect(wrapper.find('[data-test="chain"]').attributes('href')).toBe('/threats/chains/4')
  })

  it('says a link that was seen is seen, and one that was not is inferred', async () => {
    const seen = await open()
    const guessed = await open({ confirmed: false })

    expect(seen.wrapper.find('[data-test="chain-link"]').text()).toBe('Seen')
    expect(guessed.wrapper.find('[data-test="chain-link"]').text()).toBe('Inferred')
  })
})
