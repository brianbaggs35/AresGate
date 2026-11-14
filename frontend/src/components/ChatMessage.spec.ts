import ChatMessage from '@/components/ChatMessage.vue'
import { answer, question } from '@/test/aiChat'
import { mountWithPlugins } from '@/test/mount'

async function show(message = answer(), canRetry = false) {
  const mounted = await mountWithPlugins(ChatMessage, { props: { message, canRetry } })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ChatMessage', () => {
  it('shows what the owner asked as they wrote it', async () => {
    const { find, wrapper } = await show(question({ text: 'Is [incident 1] bad?' }))

    expect(find('message-owner').exists()).toBe(true)
    expect(find('message-text').text()).toBe('Is [incident 1] bad?')
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('shows an answer with the incidents it names as links', async () => {
    const { find } = await show()

    expect(find('message-text').text()).toBe(
      'Start with incident 3: it is the one that needs you most.',
    )
    expect(find('message-incident').attributes('href')).toBe('/incidents/3')
  })

  it('shows lists as lists', async () => {
    const { wrapper } = await show(
      answer({ text: 'Check:\n- the [incident 3] firewall\n- the NAS' }),
    )

    const items = wrapper.findAll('li')
    expect(items.map((item) => item.text())).toEqual(['the incident 3 firewall', 'the NAS'])
    expect(items[0]?.find('a').attributes('href')).toBe('/incidents/3')
  })

  it('says what it looked at and what it is based on', async () => {
    const { find, wrapper } = await show(
      answer({
        lookups: [
          { tool: 'open_incidents', summary: '2 open incidents' },
          { tool: 'integrations', summary: '3 integrations, 0 collectors failing' },
        ],
        cites: [
          { kind: 'incident', key: '3', label: 'Incident 3' },
          { kind: 'integration', key: 'ntopng', label: 'ntopng' },
          { kind: 'device', key: '9', label: 'vault' },
          { kind: 'mystery', key: '1', label: 'Something with no page' },
        ],
      }),
    )

    expect(wrapper.findAll('[data-test="message-lookup"]').map((chip) => chip.text())).toEqual([
      '2 open incidents',
      '3 integrations, 0 collectors failing',
    ])
    // A device links to its page, and a thing with no page of its own is not offered as a link.
    const cites = wrapper.findAll('[data-test="message-cite"]')
    expect(cites.map((chip) => chip.text())).toEqual(['Incident 3', 'ntopng', 'vault'])
    expect(cites.map((chip) => chip.attributes('href'))).toEqual([
      '/incidents/3',
      '/integrations/ntopng',
      '/assets/device-9',
    ])
    expect(find('message-lookups').exists()).toBe(true)
  })

  it('has no rows for what it did not look at', async () => {
    const { find } = await show(answer({ lookups: [], cites: [], call_ids: [] }))

    expect(find('message-lookups').exists()).toBe(false)
    expect(find('message-cites').exists()).toBe(false)
    expect(find('message-call').exists()).toBe(false)
  })

  it('offers to show each request that made it', async () => {
    const { wrapper } = await show(answer({ call_ids: [11, 12] }))

    const buttons = wrapper.findAll('[data-test="message-call"]')
    expect(buttons.map((button) => button.text())).toEqual([
      'See what was sent (1 of 2)',
      'See what was sent (2 of 2)',
    ])

    await buttons[1]?.trigger('click')

    expect(wrapper.emitted('show-call')).toEqual([[12]])
  })

  it('calls a single request what it is', async () => {
    const { find } = await show(answer({ call_ids: [11] }))

    expect(find('message-call').text()).toBe('See what was sent')
  })

  describe('an answer that could not be made', () => {
    const failed = () => answer({ ok: false, text: 'AI is turned off.', lookups: [], cites: [] })

    it('says why, and leads to the settings', async () => {
      const { find } = await show(failed())

      expect(find('message-failed').text()).toContain('AI is turned off.')
      expect(find('message-settings').attributes('href')).toBe('/settings/ai')
      expect(find('message-lookups').exists()).toBe(false)
    })

    it('can be asked again when it is the last', async () => {
      const { find, wrapper } = await show(failed(), true)

      await find('message-retry').trigger('click')

      expect(wrapper.emitted('retry')).toHaveLength(1)
    })

    it('cannot be asked again otherwise', async () => {
      const { find } = await show(failed(), false)

      expect(find('message-retry').exists()).toBe(false)
    })
  })
})
