import type { SearchTerm } from '@/api/incidents'
import IncidentSearch from '@/components/IncidentSearch.vue'
import { RECENT_KEY, SEARCH_EXAMPLES } from '@/search'
import { mountWithPlugins } from '@/test/mount'

const term = (label: string, start: number, end: number, negated = false): SearchTerm => ({
  field: null,
  label,
  negated,
  start,
  end,
})

async function open(props: Partial<InstanceType<typeof IncidentSearch>['$props']> = {}) {
  const mounted = await mountWithPlugins(IncidentSearch, {
    signedIn: 'admin',
    props: { modelValue: '', terms: [], error: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const box = () => mounted.wrapper.find<HTMLInputElement>('[data-test="search"] input')
  const emitted = () => mounted.wrapper.emitted('update:modelValue') ?? []
  return { ...mounted, find, box, emitted }
}

afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
})

describe('IncidentSearch', () => {
  it('is a search landmark with a labelled box that has what is applied in it', async () => {
    const { wrapper, box } = await open({ modelValue: 'source:wazuh' })

    expect(wrapper.find('[role="search"]').attributes('aria-label')).toBe('Search incidents')
    expect(wrapper.find('label').text()).toBe('Search incidents')
    expect(box().element.value).toBe('source:wazuh')
  })

  it('hints at the slash key while the box is empty, where there is a keyboard', async () => {
    const { find, box } = await open()
    expect(find('search-key').text()).toBe('/')
    expect(find('search-key').attributes('aria-hidden')).toBe('true')

    await box().setValue('ssh')

    expect(find('search-key').exists()).toBe(false)
  })

  describe('applying what is typed', () => {
    it('waits for a pause in the typing', async () => {
      const { box, emitted } = await open()
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

      await box().setValue('s')
      vi.advanceTimersByTime(300)
      await box().setValue('ssh')
      vi.advanceTimersByTime(399)
      expect(emitted()).toEqual([])

      vi.advanceTimersByTime(1)
      expect(emitted()).toEqual([['ssh']])
    })

    it('does not apply what is already applied', async () => {
      const { box, emitted } = await open({ modelValue: 'ssh' })
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

      await box().setValue('ssh  ')
      vi.advanceTimersByTime(400)

      expect(emitted()).toEqual([])
    })

    it('does not apply after the page is left', async () => {
      const { box, emitted, wrapper } = await open()
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
      await box().setValue('ssh')

      wrapper.unmount()
      vi.advanceTimersByTime(400)

      expect(emitted()).toEqual([])
    })

    it('applies at once with Enter, and remembers it', async () => {
      const { box, emitted } = await open()

      await box().setValue('  port:22 ')
      await box().trigger('keydown.enter')

      expect(emitted()).toEqual([['port:22']])
      expect(JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')).toEqual(['port:22'])
    })

    it('applies at once when the box is left, and does not remember nothing', async () => {
      const { box, emitted } = await open({ modelValue: 'ssh' })

      await box().setValue('')
      await box().trigger('blur')

      expect(emitted()).toEqual([['']])
      expect(localStorage.getItem(RECENT_KEY)).toBeNull()
    })

    it('is emptied by the button for it, at once', async () => {
      const { wrapper, emitted, box } = await open({ modelValue: 'ssh' })

      await wrapper.find('[aria-label="Clear Search incidents"]').trigger('click')

      expect(emitted()).toEqual([['']])
      expect(box().element.value).toBe('')
    })

    it('shows a search that arrives from outside, and leaves alone what was typed', async () => {
      const { wrapper, box } = await open({ modelValue: 'ssh' })

      await wrapper.setProps({ modelValue: 'port:22' })
      expect(box().element.value).toBe('port:22')

      await box().setValue('ssh ')
      await wrapper.setProps({ modelValue: 'ssh' })
      expect(box().element.value).toBe('ssh ')
    })
  })

  describe('the terms', () => {
    const terms = [
      term('Source: Wazuh', 0, 12),
      term('Not port: 22', 13, 22, true),
      term('Contains: ssh', 23, 26),
    ]
    const modelValue = 'source:wazuh -port:22 ssh'

    it('are chips, one for each, with the turned around ones marked', async () => {
      const { wrapper } = await open({ modelValue, terms })

      const chips = wrapper.findAll('[data-test="search-term"]')
      expect(chips.map((chip) => chip.text())).toEqual([
        'Source: Wazuh',
        'Not port: 22',
        'Contains: ssh',
      ])
      expect(chips[1]?.classes()).toContain('search__term--not')
      expect(wrapper.find('ul[aria-label="What the search means"]').exists()).toBe(true)
    })

    it('are not there when there are none', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('ul[aria-label="What the search means"]').exists()).toBe(false)
    })

    it('each come off with a tap, which applies the rest at once', async () => {
      const { wrapper, emitted, box } = await open({ modelValue, terms })

      await wrapper.find('[aria-label="Remove Not port: 22"]').trigger('click')

      expect(emitted()).toEqual([['source:wazuh ssh']])
      expect(box().element.value).toBe('source:wazuh ssh')
    })
  })

  it('says why a search can not be understood, under the box', async () => {
    const { find } = await open({ modelValue: 'sevrity:high', error: 'No such field.' })

    expect(find('search').text()).toContain('No such field.')
    expect(find('search').classes()).toContain('v-input--error')
  })

  describe('the ways to search', () => {
    it('are shown by the button for them, and put away by it', async () => {
      const { find } = await open()
      const button = find('search-help')
      expect(button.attributes('aria-expanded')).toBe('false')
      expect(find('search-panel').exists()).toBe(false)

      await button.trigger('click')

      expect(button.attributes('aria-expanded')).toBe('true')
      expect(button.attributes('aria-controls')).toBe(find('search-panel').attributes('id'))
      expect(find('search-panel').findAll('[data-test="search-example"]')).toHaveLength(
        SEARCH_EXAMPLES.length,
      )

      await button.trigger('click')
      expect(find('search-panel').exists()).toBe(false)
    })

    it('are put away by Escape', async () => {
      const { find } = await open()
      await find('search-help').trigger('click')

      await find('search-panel').trigger('keydown', { key: 'Escape' })

      expect(find('search-panel').exists()).toBe(false)
    })

    it('add an example to what is there, and apply it after a pause', async () => {
      const { wrapper, find, box, emitted } = await open({ modelValue: 'ssh' })
      await find('search-help').trigger('click')
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

      await wrapper.findAll('[data-test="search-example"]')[4]?.trigger('click')

      expect(box().element.value).toBe(`ssh ${SEARCH_EXAMPLES[4]?.text ?? ''}`)
      vi.advanceTimersByTime(400)
      expect(emitted()).toEqual([[`ssh ${SEARCH_EXAMPLES[4]?.text ?? ''}`]])
    })

    it('add an example to an empty box as it is', async () => {
      const { wrapper, find, box } = await open()
      await find('search-help').trigger('click')

      await wrapper.findAll('[data-test="search-example"]')[0]?.trigger('click')

      expect(box().element.value).toBe(SEARCH_EXAMPLES[0]?.text)
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    })
  })

  describe('the recent searches', () => {
    beforeEach(() => {
      localStorage.setItem(RECENT_KEY, JSON.stringify(['severity>=high', 'source:wazuh']))
    })

    it('are listed first, newest first, when there are any', async () => {
      const { wrapper, find } = await open()
      await find('search-help').trigger('click')

      expect(wrapper.findAll('[data-test="search-recent"]').map((row) => row.text())).toEqual([
        'severity>=high',
        'source:wazuh',
      ])
    })

    it('are not listed when there are none', async () => {
      localStorage.clear()
      const { wrapper, find } = await open()
      await find('search-help').trigger('click')

      expect(wrapper.find('[data-test="search-recent"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="search-forget"]').exists()).toBe(false)
    })

    it('are used with a tap, which applies at once and puts the panel away', async () => {
      const { wrapper, find, box, emitted } = await open()
      await find('search-help').trigger('click')

      await wrapper.findAll('[data-test="search-recent"]')[1]?.trigger('click')

      expect(emitted()).toEqual([['source:wazuh']])
      expect(box().element.value).toBe('source:wazuh')
      expect(find('search-panel').exists()).toBe(false)
      expect(JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')).toEqual([
        'source:wazuh',
        'severity>=high',
      ])
    })

    it('can all be forgotten', async () => {
      const { wrapper, find } = await open()
      await find('search-help').trigger('click')

      await find('search-forget').trigger('click')

      expect(wrapper.find('[data-test="search-recent"]').exists()).toBe(false)
      expect(localStorage.getItem(RECENT_KEY)).toBeNull()
    })
  })

  it('can be given the keyboard', async () => {
    const { wrapper, box } = await open()
    const focus = vi.spyOn(box().element, 'focus')

    ;(wrapper.vm as unknown as { focus: () => void }).focus()

    expect(focus).toHaveBeenCalled()
  })
})
