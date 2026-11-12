import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import AiReading from '@/components/AiReading.vue'
import { detail, reading } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(
  incident = detail({ reading: reading() }),
  props: { asking?: boolean; failure?: string | null } = {},
) {
  const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(given())
  const mounted = await mountWithPlugins(AiReading, {
    signedIn: 'admin',
    withApp: true,
    props: { incident, asking: false, failure: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const emitted = (name: string) => mounted.wrapper.findComponent(AiReading).emitted(name)
  return { ...mounted, give, find, text, emitted }
}

describe('AiReading', () => {
  describe('an incident the AI has read', () => {
    it('says what it made of it, and that it is the AI’s opinion', async () => {
      const { text } = await show()

      expect(text('ai-class')).toBe('Probe')
      expect(text('ai-confidence')).toBe('91 of 100 sure')
      expect(text('ai-opinion')).toBe("The AI's opinion")
      expect(text('ai-headline')).toBe('An internet scanner tried ssh on one device')
      expect(text('ai-story')).toContain('Nothing got in')
    })

    it('shows where your review of the reading stands, and passes on an answer', async () => {
      const { find, emitted, wrapper } = await show(
        detail({ reading: reading({ review: 'pending' }) }),
      )

      expect(find('strip-state').text()).toContain('Waiting for you.')

      wrapper.findComponent({ name: 'ReviewStrip' }).vm.$emit('answered')
      expect(emitted('changed')).toHaveLength(1)
    })

    it('lists what to check, when there is something', async () => {
      const { wrapper } = await show()

      expect(wrapper.findAll('[data-test="ai-check"]').map((item) => item.text())).toEqual([
        'Make sure ssh is not open to the internet',
      ])
    })

    it('lists what stands out in what was sent, when the AI noted any', async () => {
      const { wrapper, find } = await show()

      expect(wrapper.findAll('[data-test="ai-observation"]').map((item) => item.text())).toEqual([
        'One address tried a few passwords over ssh and was turned away.',
      ])
      const none = await show(detail({ reading: reading({ observations: [] }) }))
      expect(none.find('ai-observations').exists()).toBe(false)
      expect(find('ai-observations').exists()).toBe(true)
    })

    it('lists nothing when there is nothing to check', async () => {
      const { find } = await show(detail({ reading: reading({ checks: [] }) }))

      expect(find('ai-check').exists()).toBe(false)
    })

    it('says who read it and when', async () => {
      const { text } = await show()

      expect(text('ai-source')).toBe('Read by Anthropic (claude-haiku-5-5) 3 minutes ago.')
    })

    it('says how many signals came in after it was read', async () => {
      const { text } = await show(
        detail({ signal_count: 8, reading: reading({ signals_read: 3 }) }),
      )

      expect(text('ai-new')).toBe('5 new signals have come in since.')
    })

    it('says nothing of new signals when none came in', async () => {
      const { find } = await show()

      expect(find('ai-new').exists()).toBe(false)
    })

    it('can be read again, which the page is asked to do', async () => {
      const { find, emitted } = await show()

      await find('ai-again').trigger('click')

      expect(emitted('ask')).toHaveLength(1)
    })

    it('offers no second reading while one is under way', async () => {
      const { find, text } = await show(detail({ reading: reading() }), { asking: true })

      expect(find('ai-again').exists()).toBe(false)
      expect(text('ai-busy')).toContain('The AI is reading this incident')
    })
  })

  describe('the assistant', () => {
    it('can be asked about the incident, whether or not the AI has read it', async () => {
      const read = await show(detail({ id: 14, reading: reading() }))
      expect(read.find('ai-chat').attributes('href')).toBe('/assistant?about=incident:14')

      const unread = await show(detail({ id: 15, reading: null }))
      expect(unread.find('ai-chat').attributes('href')).toBe('/assistant?about=incident:15')
    })
  })

  describe('the verdict it suggests', () => {
    it('is a button that says what it is about, with the AI’s reason', async () => {
      const { text, find } = await show()

      expect(text('ai-reason')).toBe('Routine background scanning.')
      expect(find('ai-suggestion').find('[data-test="verdict"]').text()).toBe('Low priority')
      expect(text('ai-accept')).toBe('Mark 93.184.216.34 as low priority')
    })

    it('gives the verdict when it is pressed, with the reason as the note', async () => {
      const { find, give, text, emitted } = await show()

      await find('ai-accept').trigger('click')
      await flushPromises()

      expect(give).toHaveBeenCalledWith(
        {
          verdict: 'low_priority',
          address: '93.184.216.34',
          note: 'Suggested by the AI: Routine background scanning.',
        },
        'a-security-token',
      )
      expect(text('ai-notice')).toBe('Remembered: 93.184.216.34 is low priority.')
      expect(emitted('changed')).toHaveLength(1)
    })

    it('says it was suggested even with no reason given', async () => {
      const { find, give } = await show(detail({ reading: reading({ verdict_reason: null }) }))

      await find('ai-accept').trigger('click')
      await flushPromises()

      expect(give).toHaveBeenCalledWith(
        { verdict: 'low_priority', address: '93.184.216.34', note: 'Suggested by the AI.' },
        'a-security-token',
      )
    })

    it('keeps the note within what a verdict takes', async () => {
      const { find, give } = await show(
        detail({ reading: reading({ verdict_reason: 'x'.repeat(600) }) }),
      )

      await find('ai-accept').trigger('click')
      await flushPromises()

      const request = give.mock.calls[0]?.[0]
      expect(request?.note).toHaveLength(500)
    })

    it('says why it did not work, and does not claim it did', async () => {
      const { find, give, text, emitted } = await show()
      give.mockRejectedValue(offline())

      await find('ai-accept').trigger('click')
      await flushPromises()

      expect(text('ai-problem')).toContain("Can't reach AresGate.")
      expect(find('ai-notice').exists()).toBe(false)
      expect(emitted('changed')).toBeUndefined()
    })

    it('is not suggested when you have already said something of the incident', async () => {
      const { find } = await show(detail({ verdict: 'threat', reading: reading() }))

      expect(find('ai-suggestion').exists()).toBe(false)
    })

    it('is not suggested when the AI has none to suggest', async () => {
      const { find } = await show(
        detail({ reading: reading({ verdict: null, verdict_reason: null }) }),
      )

      expect(find('ai-suggestion').exists()).toBe(false)
    })

    it('has no button for an incident that names nothing a verdict could be about', async () => {
      const { find, text } = await show(
        detail({
          subject: 'rule:wazuh:5710',
          signals: [],
          reading: reading(),
        }),
      )

      expect(text('ai-reason')).toBe('Routine background scanning.')
      expect(find('ai-accept').exists()).toBe(false)
    })
  })

  describe('an incident it has not read', () => {
    it('says so, and offers to ask', async () => {
      const { find, text, emitted } = await show(detail())

      expect(text('ai-unread')).toContain('The AI has not read this incident')
      expect(find('ai-reading').exists()).toBe(false)

      await find('ai-ask').trigger('click')

      expect(emitted('ask')).toHaveLength(1)
    })

    it('shows that the AI is reading it, and offers nothing meanwhile', async () => {
      const { find, text } = await show(detail(), { asking: true })

      expect(text('ai-busy')).toContain('up to a minute')
      expect(find('ai-ask').exists()).toBe(false)
      expect(find('ai-unread').exists()).toBe(false)
    })
  })

  describe('when the AI could not be asked', () => {
    it('says why in words and leads to the settings', async () => {
      const { text, find } = await show(detail(), {
        failure: 'AI is turned off. Turn it on under Settings > AI to use it.',
      })

      expect(text('ai-failure')).toContain('AI is turned off.')
      expect(find('ai-settings-link').attributes('href')).toBe('/settings/ai')
    })

    it('keeps the reading it has beside the reason', async () => {
      const { find } = await show(detail({ reading: reading() }), {
        failure: 'The AI provider didn’t answer.',
      })

      expect(find('ai-failure').exists()).toBe(true)
      expect(find('ai-reading').exists()).toBe(true)
    })
  })
})
