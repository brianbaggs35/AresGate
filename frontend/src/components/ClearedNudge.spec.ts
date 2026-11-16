import ClearedNudge from '@/components/ClearedNudge.vue'
import { mountWithPlugins } from '@/test/mount'

async function open(waiting: number, cleared: number) {
  return mountWithPlugins(ClearedNudge, {
    signedIn: 'admin',
    props: { counts: { waiting, cleared } },
  })
}

describe('ClearedNudge', () => {
  it('is not there with nothing to say', async () => {
    const { wrapper } = await open(0, 0)

    expect(wrapper.find('[data-test="cleared-nudge"]').exists()).toBe(false)
  })

  it('says what the AI cleared, and takes you to it', async () => {
    const { wrapper } = await open(0, 2)

    expect(wrapper.find('[data-test="cleared-nudge-text"]').text()).toBe(
      '2 incidents cleared by the AI that are not confirmed.',
    )
    expect(wrapper.find('[data-test="cleared-nudge-open"]').attributes('href')).toBe(
      '/cleared?state=cleared',
    )
  })

  it('says what waits when nothing was cleared', async () => {
    const { wrapper } = await open(3, 0)

    expect(wrapper.find('[data-test="cleared-nudge-text"]').text()).toContain('3 incidents')
    expect(wrapper.find('[data-test="cleared-nudge-open"]').attributes('href')).toBe('/cleared')
  })
})
