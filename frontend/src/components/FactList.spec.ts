import FactList from '@/components/FactList.vue'
import { mountWithPlugins } from '@/test/mount'

describe('FactList', () => {
  it('lists each label with its value', async () => {
    const { wrapper } = await mountWithPlugins(FactList, {
      props: {
        facts: [
          { id: 'version', label: 'Version', value: '0.0.1' },
          { id: 'python', label: 'Python', value: '3.14.8' },
        ],
      },
    })
    expect(wrapper.find('dl').exists()).toBe(true)
    const rows = wrapper
      .findAll('[data-test^="fact-"]')
      .filter((row) => row.element.tagName === 'DIV')
    expect(rows.map((row) => row.attributes('data-test'))).toEqual(['fact-version', 'fact-python'])
    expect(wrapper.find('[data-test="fact-version"] dt').text()).toBe('Version')
    expect(wrapper.find('[data-test="fact-version"] dd').text()).toBe('0.0.1')
    expect(wrapper.find('[data-test="fact-python"] dd').text()).toBe('3.14.8')
  })

  it('is empty without facts', async () => {
    const { wrapper } = await mountWithPlugins(FactList, { props: { facts: [] } })
    expect(wrapper.findAll('dt')).toHaveLength(0)
  })
})
