import { VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import VerdictPanel from '@/components/VerdictPanel.vue'
import { detail, signal } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given, verdict } from '@/test/verdicts'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(incident = detail(), verdicts: verdictsApi.Verdict[] = []) {
  const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(given())
  const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(VerdictPanel, {
    signedIn: 'admin',
    withApp: true,
    props: { incident, verdicts },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const press = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  const scope = (key: string) => {
    mounted.wrapper.findComponent(VSelect).vm.$emit('update:modelValue', key)
    return flushPromises()
  }
  const write = async (words: string) => {
    await mounted.wrapper.find('[data-test="verdict-note"] input').setValue(words)
  }
  return { ...mounted, give, remove, find, text, press, scope, write }
}

describe('VerdictPanel', () => {
  describe('what the verdicts say now', () => {
    it('says nothing has been said of a new incident', async () => {
      const { text, find } = await show()

      expect(text('verdict-standing')).toBe("You haven't said anything about it yet.")
      expect(find('verdict').exists()).toBe(false)
    })

    it('says what they say of it as a whole, with a chip', async () => {
      const { text } = await show(detail({ verdict: 'not_suspicious' }))

      expect(text('verdict')).toBe('Not suspicious')
      expect(text('verdict-standing')).toContain('will not raise an alarm')
    })

    it('says how many of its signals are left out', async () => {
      const { text } = await show(detail({ verdict_counts: { low_priority: 1 } }))

      expect(text('verdict-standing')).toBe(
        '1 of its 3 signals match a verdict you gave and are not counted.',
      )
    })
  })

  describe('the verdicts that apply here', () => {
    it('are listed with what they say and what they are about', async () => {
      const incident = detail({
        signals: [signal({ verdict_rule_id: 2 }), signal({ verdict_rule_id: 9 })],
      })
      const { wrapper } = await show(incident, [
        verdict({ id: 2, verdict: 'low_priority', signature: 'Brute force on ssh' }),
        verdict({ id: 1 }),
      ])

      const rows = wrapper.findAll('[data-test="applied"]')
      expect(rows).toHaveLength(1)
      expect(rows[0]?.find('[data-test="verdict"]').text()).toBe('Low priority')
      expect(rows[0]?.find('[data-test="applied-about"]').text()).toBe(
        '“Brute force on ssh” from 93.184.216.34',
      )
    })

    it('are not listed when none applies', async () => {
      const { wrapper } = await show(detail(), [verdict()])

      expect(wrapper.find('[data-test="applied"]').exists()).toBe(false)
    })

    it('can be taken back, and then the page is told', async () => {
      const incident = detail({ signals: [signal({ verdict_rule_id: 2 })] })
      const { remove, press, text, wrapper } = await show(incident, [verdict({ id: 2 })])

      await press('take-back')

      expect(remove).toHaveBeenCalledWith(2, 'a-security-token')
      expect(text('verdict-notice')).toBe('Taken back: 93.184.216.34.')
      expect(wrapper.findComponent(VerdictPanel).emitted('changed')).toHaveLength(1)
    })

    it('say why one could not be taken back, and keep the page as it was', async () => {
      const incident = detail({ signals: [signal({ verdict_rule_id: 2 })] })
      const { remove, press, text, wrapper, find } = await show(incident, [verdict({ id: 2 })])
      remove.mockRejectedValue(offline())

      await press('take-back')

      expect(text('verdict-error')).toContain("Can't reach AresGate.")
      expect(find('verdict-notice').exists()).toBe(false)
      expect(wrapper.findComponent(VerdictPanel).emitted('changed')).toBeUndefined()
      expect(find('take-back').attributes('disabled')).toBeUndefined()
    })
  })

  describe('giving a verdict', () => {
    it('is about the address to begin with', async () => {
      const { give, press, text, wrapper } = await show()

      await press('give-not_suspicious')

      expect(give).toHaveBeenCalledWith(
        { verdict: 'not_suspicious', address: '93.184.216.34' },
        'a-security-token',
      )
      expect(text('verdict-notice')).toBe('Remembered: 93.184.216.34 is not suspicious.')
      expect(wrapper.findComponent(VerdictPanel).emitted('changed')).toHaveLength(1)
    })

    it('offers all three, each in words', async () => {
      const { wrapper } = await show()

      const buttons = wrapper.findAll('[data-test^="give-"]')
      expect(buttons.map((button) => button.text())).toEqual([
        'Not suspicious',
        'Low priority',
        'Real threat',
      ])
    })

    it('can be about one of the alerts instead', async () => {
      const { give, press, scope, text } = await show()

      await scope('alert:opnsense:ET SCAN Potential SSH Scan')
      await press('give-low_priority')

      expect(give).toHaveBeenCalledWith(
        { verdict: 'low_priority', source: 'opnsense', signature: 'ET SCAN Potential SSH Scan' },
        'a-security-token',
      )
      expect(text('verdict-notice')).toBe(
        'Remembered: “ET SCAN Potential SSH Scan” is low priority.',
      )
    })

    it('says what the choice takes in', async () => {
      const { text, scope } = await show()
      expect(text('verdict-scope-hint')).toBe('Everything about this address.')

      await scope('alert-here:wazuh:Brute force on ssh')

      expect(text('verdict-scope-hint')).toBe('Only this address, as seen by Wazuh.')
    })

    it('says why, when it is told, and starts the next with no note', async () => {
      const { give, press, write, wrapper } = await show()

      await write('  my own scanner ')
      await press('give-threat')

      expect(give).toHaveBeenCalledWith(
        { verdict: 'threat', address: '93.184.216.34', note: 'my own scanner' },
        'a-security-token',
      )
      expect(wrapper.find<HTMLInputElement>('[data-test="verdict-note"] input').element.value).toBe(
        '',
      )
    })

    it('says why it could not be given, and keeps what was written', async () => {
      const { give, press, write, text, find, wrapper } = await show()
      give.mockRejectedValue(offline())
      await write('my own scanner')

      await press('give-threat')

      expect(text('verdict-error')).toContain("Can't reach AresGate.")
      expect(find('verdict-notice').exists()).toBe(false)
      expect(wrapper.findComponent(VerdictPanel).emitted('changed')).toBeUndefined()
      expect(wrapper.find<HTMLInputElement>('[data-test="verdict-note"] input').element.value).toBe(
        'my own scanner',
      )
    })

    it('forgets the last answer when another is given', async () => {
      const { give, press, find, text } = await show()
      give.mockRejectedValueOnce(offline())
      await press('give-threat')
      expect(find('verdict-error').exists()).toBe(true)

      await press('give-threat')

      expect(find('verdict-error').exists()).toBe(false)
      expect(text('verdict-notice')).toContain('Remembered')
    })

    it('has to wait for one to be given before another can be', async () => {
      const { give, find, wrapper } = await show()
      give.mockReturnValue(new Promise(() => {}))

      await find('give-threat').trigger('click')
      await flushPromises()

      expect(find('give-not_suspicious').attributes('disabled')).toBeDefined()
      expect(find('give-threat').classes()).toContain('v-btn--loading')
      expect(wrapper.find('[data-test="verdict-note"] input').attributes('disabled')).toBeDefined()
    })

    it('can be about nothing in an incident that has nothing to match', async () => {
      const { find, text } = await show(
        detail({ subject: 'rule:wazuh:5710', signals: [signal({ signature: null })] }),
      )

      expect(find('verdict-form').exists()).toBe(false)
      expect(text('verdict-unmatchable')).toContain('Nothing in it can be matched later')
    })
  })
})
