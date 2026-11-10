import CountedBars from '@/components/CountedBars.vue'
import { mountWithPlugins } from '@/test/mount'

describe('CountedBars', () => {
  it('writes each thing and its count, and draws the bars against the commonest', async () => {
    const { wrapper } = await mountWithPlugins(CountedBars, {
      props: {
        items: [
          { label: 'T1110 Brute Force', hint: 'Credential Access', count: 1200 },
          { label: 'T1078 Valid Accounts', count: 600 },
        ],
      },
    })

    expect(wrapper.findAll('[data-test="bar-label"]').map((each) => each.text())).toEqual([
      'T1110 Brute Force',
      'T1078 Valid Accounts',
    ])
    expect(wrapper.findAll('[data-test="bar-count"]').map((each) => each.text())).toEqual([
      '1,200',
      '600',
    ])
    expect(wrapper.text()).toContain('Credential Access')
    const fills = wrapper.findAll('.bars__fill').map((each) => each.attributes('style'))
    expect(fills[0]).toContain('width: 100%')
    expect(fills[1]).toContain('width: 50%')
  })

  it('draws nothing for a list with nothing in it', async () => {
    const { wrapper } = await mountWithPlugins(CountedBars, { props: { items: [] } })

    expect(wrapper.findAll('li')).toHaveLength(0)
  })
})
