import UsageMeter from '@/components/UsageMeter.vue'
import { mountWithPlugins } from '@/test/mount'

const GB = 1024 ** 3

async function mountMeter(used: number, total: number) {
  const { wrapper } = await mountWithPlugins(UsageMeter, {
    props: { label: 'Memory', used, total },
  })
  return wrapper
}

describe('UsageMeter', () => {
  it('says how much is used in words and in a bar', async () => {
    const wrapper = await mountMeter(1 * GB, 4 * GB)
    expect(wrapper.find('[data-test="usage-label"]').text()).toBe('Memory')
    expect(wrapper.find('[data-test="usage-figures"]').text()).toBe('1.0 GB of 4.0 GB · 25%')
    const bar = wrapper.find('[role="progressbar"]')
    expect(bar.attributes('aria-label')).toBe('Memory in use')
    expect(bar.attributes('aria-valuenow')).toBe('25')
  })

  it.each([
    [50, 'bg-primary'],
    [75, 'bg-warning'],
    [89, 'bg-warning'],
    [90, 'bg-error'],
    [100, 'bg-error'],
  ])('colors the bar at %d%% as %s', async (percent, color) => {
    const wrapper = await mountMeter(percent, 100)
    expect(wrapper.find('.v-progress-linear__determinate').classes()).toContain(color)
  })

  it('never goes past full, nor divides by nothing', async () => {
    expect((await mountMeter(5 * GB, 4 * GB)).find('[data-test="usage-figures"]').text()).toContain(
      '100%',
    )
    expect((await mountMeter(0, 0)).find('[data-test="usage-figures"]').text()).toContain('0%')
  })
})
