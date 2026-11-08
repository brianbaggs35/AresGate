import { defineComponent, h, ref } from 'vue'
import {
  VAutocomplete,
  VDialog,
  VRadioGroup,
  VSelect,
  VSwitch,
  VTextField,
} from 'vuetify/components'

import * as alertsApi from '@/api/alerts'
import type { Destination, Rules, RulesPreview } from '@/api/alerts'
import { ApiError } from '@/api/client'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import ModeCards from '@/components/ModeCards.vue'
import RulesDialog from '@/components/RulesDialog.vue'
import { choices, destination, preview, rules, sample, threatRules } from '@/test/alerts'
import { flushPromises, mountWithPlugins } from '@/test/mount'

interface Props {
  destination?: Destination
  busy?: boolean
  problems?: Record<string, string>
  failure?: string | null
}

/** The sheet in a page with a button that opens it, as pages use it. */
async function mountSheet(props: Props = {}, startOpen = false) {
  const saved = vi.fn<(answer: Rules) => void>()
  const open = ref(startOpen)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Open'),
        h(RulesDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          destination: destination(),
          choices: choices(),
          previewDelay: DELAY,
          ...props,
          onSave: saved,
        }),
      ]),
  })
  const ask = vi.spyOn(alertsApi, 'previewRules').mockResolvedValue(preview())
  const makeSample = vi.spyOn(alertsApi, 'fetchSample').mockResolvedValue(sample())
  const mounted = await mountWithPlugins(Page, { withApp: true, signedIn: 'admin' })
  const inSheet = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const openIt = async () => {
    await mounted.wrapper.find('[data-test="opener"]').trigger('click')
    await flushPromises()
  }
  type Field = typeof VSelect | typeof VSwitch | typeof VTextField | typeof VAutocomplete
  /** The Vuetify field with this label. */
  const component = (kind: Field, label: string) =>
    mounted.wrapper
      .findAllComponents(kind as typeof VSelect)
      .find((found) => found.props('label') === label)!
  /** Sets a field the way the person using it would: Vuetify says its value changed. */
  const set = async (kind: Field, label: string, value: unknown) => {
    component(kind, label).vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  const radio = () => mounted.wrapper.findComponent(VRadioGroup)
  const cards = () => mounted.wrapper.findComponent(ModeCards)
  /** Chooses a card, as a tap on it does. */
  const pick = async (purpose: 'threats' | 'serious' | 'custom') => {
    cards().vm.$emit('update:modelValue', purpose)
    await flushPromises()
  }
  const story = () => mounted.wrapper.findComponent(ChoiceToggle)
  /** What the choice of which message to show is given. */
  const told = () =>
    story().vm.$props as unknown as {
      modelValue: string
      options: { label: string }[]
    }
  const save = async () => {
    inSheet('rules-save')!.click()
    await flushPromises()
  }
  return {
    ...mounted,
    saved,
    open,
    ask,
    makeSample,
    inSheet,
    openIt,
    component,
    set,
    radio,
    save,
    cards,
    pick,
    story,
    told,
  }
}

/** A short pause before a change is asked about, so that the tests need not wait for long. */
const DELAY = 30

/** Waits out the pause before a change is asked about. */
async function pause() {
  await new Promise((resolve) => setTimeout(resolve, DELAY * 3))
  await flushPromises()
}

describe('RulesDialog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('opening', () => {
    it('is closed until it is opened', async () => {
      const { inSheet, ask } = await mountSheet()

      expect(inSheet('rules-dialog')).toBeNull()
      expect(ask).not.toHaveBeenCalled()
    })

    it('says whose rules they are, and shows them as they are kept', async () => {
      const { inSheet, openIt, component } = await mountSheet({
        destination: destination({
          name: 'Phone',
          rules: rules({ min_severity: 3, min_confidence: 35, max_per_hour: 3 }),
        }),
      })

      await openIt()

      expect(inSheet('rules-title')!.textContent.trim()).toBe('What Phone is told')
      expect(component(VSelect, 'How serious').props('modelValue')).toBe(3)
      expect(component(VSelect, 'How sure AresGate is').props('modelValue')).toBe(35)
      expect(component(VSelect, 'Limit').props('modelValue')).toBe(3)
    })

    it('shows what the kept rules would have done at once', async () => {
      const { inSheet, openIt, ask } = await mountSheet()

      await openIt()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(ask).toHaveBeenCalledWith(
        1,
        rules({ time_zone: expect.any(String) as string }),
        'a-security-token',
      )
      expect(inSheet('preview-summary')!.textContent).toContain('would have sent 2 messages')
    })

    it('shows what the kept rules would have done when it is made already open', async () => {
      // A page that makes the sheet and opens it in one go never sees it closed.
      const { inSheet, ask } = await mountSheet({}, true)
      await flushPromises()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(inSheet('preview-summary')!.textContent).toContain('would have sent 2 messages')
    })

    it('never says what a webhook address is', async () => {
      const { openIt } = await mountSheet()

      await openIt()

      expect(document.body.textContent).not.toMatch(/webhooks\/\d/)
    })

    it('shows the kept rules again when it is opened after changes that were not saved', async () => {
      const { inSheet, openIt, set, open, component } = await mountSheet()
      await openIt()
      await set(VSelect, 'How serious', 4)
      inSheet('rules-cancel')!.click()
      await flushPromises()
      expect(open.value).toBe(false)

      await openIt()

      expect(component(VSelect, 'How serious').props('modelValue')).toBe(2)
    })

    it('starts quiet hours that are off in the time zone of this computer', async () => {
      vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
        timeZone: 'Europe/Berlin',
      } as Intl.ResolvedDateTimeFormatOptions)
      const { openIt, ask } = await mountSheet()

      await openIt()

      expect(ask).toHaveBeenCalledWith(1, rules({ time_zone: 'Europe/Berlin' }), 'a-security-token')
    })

    it('keeps the time zone of quiet hours that are on', async () => {
      const { openIt, ask } = await mountSheet({
        destination: destination({ rules: rules({ quiet_hours: true, time_zone: 'Asia/Tokyo' }) }),
      })

      await openIt()

      expect(ask).toHaveBeenCalledWith(
        1,
        rules({ quiet_hours: true, time_zone: 'Asia/Tokyo' }),
        'a-security-token',
      )
    })
  })

  describe('the preview', () => {
    it('asks again after a change, once the changes have stopped', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      await openIt()
      ask.mockClear()
      ask.mockResolvedValue(preview({ would_send: 5 }))

      await set(VSelect, 'How serious', 3)
      await set(VSelect, 'How sure AresGate is', 35)
      expect(ask).not.toHaveBeenCalled()
      await pause()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(ask.mock.calls[0]?.[1]).toMatchObject({ min_severity: 3, min_confidence: 35 })
      expect(inSheet('preview-summary')!.textContent).toContain('would have sent 5 messages')
    })

    it('asks nothing when a change puts the rules back as they were asked about', async () => {
      const { openIt, set, ask } = await mountSheet()
      await openIt()
      ask.mockClear()

      await set(VSelect, 'How serious', 3)
      await set(VSelect, 'How serious', 2)
      await pause()

      expect(ask).not.toHaveBeenCalled()
    })

    it('shows the answer to the latest question, not a late answer to an earlier one', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      await openIt()
      let first: (answer: RulesPreview) => void = () => undefined
      ask.mockImplementationOnce(
        () =>
          new Promise<RulesPreview>((resolve) => {
            first = resolve
          }),
      )
      await set(VSelect, 'How serious', 3)
      await pause()
      ask.mockResolvedValueOnce(preview({ would_send: 7 }))
      await set(VSelect, 'How serious', 4)
      await pause()

      first(preview({ would_send: 1 }))
      await flushPromises()

      expect(inSheet('preview-summary')!.textContent).toContain('would have sent 7 messages')
    })

    it('says why there is no answer, and clears it when there is one', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      ask.mockRejectedValueOnce(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await openIt()
      expect(inSheet('preview-failure')!.textContent).toContain("Can't reach AresGate.")

      await set(VSelect, 'How serious', 3)
      await pause()

      expect(inSheet('preview-failure')).toBeNull()
      expect(inSheet('preview-answer')).not.toBeNull()
    })

    it('does not mind a late failure of an earlier question', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      await openIt()
      let first: (error: Error) => void = () => undefined
      ask.mockImplementationOnce(
        () =>
          new Promise<RulesPreview>((_, reject) => {
            first = reject
          }),
      )
      await set(VSelect, 'How serious', 3)
      await pause()
      await set(VSelect, 'How serious', 4)
      await pause()

      first(new ApiError(0, 'Too late.', 'offline'))
      await flushPromises()

      expect(inSheet('preview-failure')).toBeNull()
    })

    it('stops asking when it is closed, and forgets what was on its way', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      await openIt()
      ask.mockClear()
      let late: (answer: RulesPreview) => void = () => undefined
      ask.mockImplementationOnce(
        () =>
          new Promise<RulesPreview>((resolve) => {
            late = resolve
          }),
      )
      await set(VSelect, 'How serious', 3)
      await pause()
      await set(VSelect, 'How serious', 4)
      inSheet('rules-cancel')!.click()
      await flushPromises()

      await pause()
      late(preview({ would_send: 9 }))
      await flushPromises()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(inSheet('preview-summary')?.textContent ?? '').not.toContain('9 messages')
    })

    it('tells the preview the limit of messages an hour it is working with', async () => {
      const { openIt, set, ask, inSheet } = await mountSheet()
      ask.mockResolvedValue(preview({ busiest_hour: 9, over_limit: 3 }))
      await openIt()
      expect(inSheet('preview-limit')!.textContent).toContain('at most 6 messages an hour')

      await set(VSelect, 'Limit', 2)

      expect(inSheet('preview-limit')!.textContent).toContain('at most 2 messages an hour')
    })
  })

  describe('choosing', () => {
    it('keeps Save out of reach until something is changed', async () => {
      const { openIt, set, inSheet } = await mountSheet()
      await openIt()
      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(true)

      await set(VSelect, 'How serious', 3)

      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(false)
    })

    it('hands over every rule as chosen when saved', async () => {
      const { openIt, set, save, saved, radio } = await mountSheet()
      await openIt()

      await set(VSelect, 'How serious', 3)
      await set(VSelect, 'How sure AresGate is', 0)
      await set(VSelect, 'Reported by', ['wazuh'])
      await set(VSelect, 'Kind of activity', ['scan'])
      await set(VSelect, 'Limit', 10)
      await set(VSwitch, 'Tell me again if it gets worse', false)
      radio().vm.$emit('update:modelValue', 'brief')
      await save()

      expect(saved).toHaveBeenCalledWith(
        rules({
          min_severity: 3,
          min_confidence: 0,
          sources: ['wazuh'],
          activities: ['scan'],
          max_per_hour: 10,
          again_when_worse: false,
          detail: 'brief',
          time_zone: expect.any(String) as string,
        }),
      )
    })

    it('offers a number it was given that its lists lack', async () => {
      const { openIt, component } = await mountSheet({
        destination: destination({ rules: rules({ min_confidence: 50, max_per_hour: 4 }) }),
      })

      await openIt()

      const sure = component(VSelect, 'How sure AresGate is').props('items') as { title: string }[]
      const limit = component(VSelect, 'Limit').props('items') as { title: string }[]
      expect(sure.map((item) => item.title)).toContain('50% or more')
      expect(limit.map((item) => item.title)).toContain('At most 4 messages an hour')
    })

    it('names the programs and kinds it can be limited to', async () => {
      const { openIt, component } = await mountSheet()

      await openIt()

      const programs = component(VSelect, 'Reported by').props('items') as { title: string }[]
      const kinds = component(VSelect, 'Kind of activity').props('items') as { title: string }[]
      expect(programs.map((item) => item.title)).toEqual(['OPNsense', 'ntopng', 'Wazuh'])
      expect(kinds.map((item) => item.title)).toEqual(['scanning', 'brute force'])
    })

    it('says what is never sent', async () => {
      const { openIt, inSheet } = await mountSheet()

      await openIt()

      expect(inSheet('rules-never')!.textContent).toContain('not suspicious or low priority')
      expect(inSheet('rules-never')!.textContent).toContain('real threat')
    })

    it('describes how much each level of detail says', async () => {
      const { openIt, inSheet } = await mountSheet()

      await openIt()

      const text = inSheet('rules-detail')!.textContent
      expect(text).toContain('No addresses')
      expect(text).toContain('a device on your network')
      expect(text).toContain('only you can read')
    })
  })

  describe('what the channel is for', () => {
    it('starts on real attacks only for a destination told of threats', async () => {
      const { openIt, cards, inSheet } = await mountSheet({
        destination: destination({ rules: threatRules() }),
      })

      await openIt()

      expect(cards().props('modelValue')).toBe('threats')
      expect(inSheet('rules-threats-note')!.textContent).toContain('becomes a threat')
      expect(inSheet('rules-floors')).toBeNull()
    })

    it('links the note on threats to where it is set what a threat is', async () => {
      const { openIt, inSheet } = await mountSheet({
        destination: destination({ rules: threatRules() }),
      })

      await openIt()

      expect(inSheet('rules-threat-link')!.getAttribute('href')).toBe('/settings/threat-detection')
    })

    it('starts on everything serious for the plain rules a channel got before', async () => {
      const { openIt, cards, inSheet } = await mountSheet()

      await openIt()

      expect(cards().props('modelValue')).toBe('serious')
      expect(inSheet('rules-floors')).not.toBeNull()
      expect(inSheet('rules-purpose-note')).toBeNull()
    })

    it.each([
      ['how serious', { min_severity: 3 }],
      ['how sure', { min_confidence: 35 }],
      ['the programs', { sources: ['wazuh'] }],
      ['the kinds of activity', { activities: ['scan'] }],
    ])('starts on custom when %s is the owner’s own', async (_what, changes) => {
      const { openIt, cards } = await mountSheet({
        destination: destination({ rules: rules(changes) }),
      })

      await openIt()

      expect(cards().props('modelValue')).toBe('custom')
    })

    it('has nothing to save when a choice is put back as it was', async () => {
      const { openIt, pick, save, saved } = await mountSheet({
        destination: destination({ rules: threatRules({ min_severity: 3 }) }),
      })
      await openIt()

      await pick('custom')
      await pick('threats')
      await save()

      expect(saved).not.toHaveBeenCalled()
    })

    it('changes what a channel is told when another card is chosen', async () => {
      const { openIt, pick, save, saved, inSheet, cards } = await mountSheet({
        destination: destination({ rules: rules({ min_severity: 3, sources: ['wazuh'] }) }),
      })
      await openIt()

      await pick('threats')

      expect(cards().props('modelValue')).toBe('threats')
      expect(inSheet('rules-floors')).toBeNull()
      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(false)
      await save()
      expect(saved).toHaveBeenCalledWith(
        rules({
          mode: 'threats',
          min_severity: 3,
          sources: ['wazuh'],
          time_zone: expect.any(String) as string,
        }),
      )
    })

    it('puts the plain rules back when everything serious is chosen', async () => {
      const { openIt, pick, save, saved } = await mountSheet({
        destination: destination({
          rules: rules({
            min_severity: 4,
            min_confidence: 0,
            sources: ['wazuh'],
            activities: ['scan'],
          }),
        }),
      })
      await openIt()

      await pick('serious')
      await save()

      expect(saved).toHaveBeenCalledWith(rules({ time_zone: expect.any(String) as string }))
    })

    it('opens the rules of a channel that is told of threats when custom is chosen', async () => {
      const { openIt, pick, inSheet, cards } = await mountSheet({
        destination: destination({ rules: threatRules() }),
      })
      await openIt()

      await pick('custom')

      expect(cards().props('modelValue')).toBe('custom')
      expect(inSheet('rules-floors')).not.toBeNull()
      expect(inSheet('rules-threats-note')).toBeNull()
    })

    it('calls the plain rules the owner’s own once one of them is changed', async () => {
      const { openIt, set, cards } = await mountSheet()
      await openIt()

      await set(VSelect, 'How serious', 3)

      expect(cards().props('modelValue')).toBe('custom')
    })

    it('stays on custom when the rules are changed back to the plain ones', async () => {
      const { openIt, set, cards } = await mountSheet({
        destination: destination({ rules: rules({ min_severity: 3 }) }),
      })
      await openIt()

      await set(VSelect, 'How serious', 2)

      expect(cards().props('modelValue')).toBe('custom')
    })

    it('says escalate, not get worse, for a destination told of threats', async () => {
      const { openIt, component, told } = await mountSheet({
        destination: destination({ rules: threatRules() }),
      })
      await openIt()

      expect(component(VSwitch, 'Tell me again if it escalates')).toBeDefined()
      const options = told().options
      expect(options.map((item) => item.label)).toEqual(['First message', 'If it escalates'])
    })

    it('says get worse for the rules that are the owner’s own', async () => {
      const { openIt, told } = await mountSheet()
      await openIt()

      const options = told().options
      expect(options.map((item) => item.label)).toEqual(['First message', 'If it gets worse'])
    })
  })

  describe('the sample message', () => {
    it('is asked for when the sheet opens, and drawn as Discord will show it', async () => {
      const { openIt, makeSample, inSheet } = await mountSheet()

      await openIt()

      expect(makeSample).toHaveBeenCalledTimes(1)
      expect(makeSample).toHaveBeenCalledWith('custom', 'standard', 'new')
      expect(inSheet('discord-title')!.textContent).toContain('Attack in progress')
      expect(inSheet('sample-wait')).toBeNull()
    })

    it('is asked for when the sheet is made already open', async () => {
      const { makeSample, inSheet } = await mountSheet({}, true)
      await flushPromises()

      expect(makeSample).toHaveBeenCalledTimes(1)
      expect(inSheet('discord-title')).not.toBeNull()
    })

    it('says it is being made until it has come', async () => {
      const { makeSample, openIt, inSheet } = await mountSheet()
      makeSample.mockReturnValue(new Promise(() => undefined))

      await openIt()

      expect(inSheet('sample-wait')!.textContent).toContain('Making a sample message')
      expect(inSheet('discord-preview')).toBeNull()
    })

    it('is made again for the other purpose when one is chosen', async () => {
      const { openIt, pick, makeSample } = await mountSheet()
      await openIt()

      await pick('threats')

      expect(makeSample).toHaveBeenCalledTimes(2)
      expect(makeSample).toHaveBeenLastCalledWith('threats', 'standard', 'new')
    })

    it('is made again for the other level of detail when one is chosen', async () => {
      const { openIt, radio, makeSample } = await mountSheet()
      await openIt()

      radio().vm.$emit('update:modelValue', 'full')
      await flushPromises()

      expect(makeSample).toHaveBeenCalledTimes(2)
      expect(makeSample).toHaveBeenLastCalledWith('custom', 'full', 'new')
    })

    it('is made again for the later message of the story when that is chosen', async () => {
      const { openIt, story, makeSample } = await mountSheet({
        destination: destination({ rules: threatRules() }),
      })
      await openIt()

      story().vm.$emit('update:modelValue', 'worse')
      await flushPromises()

      expect(makeSample).toHaveBeenLastCalledWith('threats', 'standard', 'worse')
    })

    it('goes back to the first message of the story each time the sheet opens', async () => {
      const { openIt, story, told, makeSample, open } = await mountSheet()
      await openIt()
      story().vm.$emit('update:modelValue', 'worse')
      await flushPromises()

      open.value = false
      await flushPromises()
      await openIt()

      expect(told().modelValue).toBe('new')
      expect(makeSample).toHaveBeenLastCalledWith('custom', 'standard', 'new')
    })

    it('is not asked for again by a change that does not change it', async () => {
      const { openIt, set, makeSample } = await mountSheet()
      await openIt()

      await set(VSelect, 'How serious', 3)
      await set(VSelect, 'Limit', 10)

      expect(makeSample).toHaveBeenCalledTimes(1)
    })

    it('says why there is no sample, and shows the next one that comes', async () => {
      const { openIt, makeSample, inSheet, pick } = await mountSheet()
      makeSample.mockRejectedValueOnce(new ApiError(500, 'Could not make a sample.'))

      await openIt()

      expect(inSheet('sample-failure')!.textContent).toContain('Could not make a sample.')
      expect(inSheet('discord-preview')).toBeNull()
      await pick('threats')
      expect(inSheet('sample-failure')).toBeNull()
      expect(inSheet('discord-preview')).not.toBeNull()
    })

    it('shows the answer to the latest question, not a late answer to an earlier one', async () => {
      const { openIt, makeSample, pick, inSheet } = await mountSheet()
      let first: (value: alertsApi.Sample) => void = () => undefined
      makeSample.mockReturnValueOnce(new Promise((resolve) => (first = resolve)))
      await openIt()
      makeSample.mockResolvedValueOnce(sample({ title: 'The later one' }))

      await pick('threats')
      first(sample({ title: 'The earlier one' }))
      await flushPromises()

      expect(inSheet('discord-title')!.textContent).toBe('The later one')
    })

    it('does not mind a late failure of an earlier question', async () => {
      const { openIt, makeSample, pick, inSheet } = await mountSheet()
      let first: (error: Error) => void = () => undefined
      makeSample.mockReturnValueOnce(new Promise((_, reject) => (first = reject)))
      await openIt()

      await pick('threats')
      first(new ApiError(500, 'Too late.'))
      await flushPromises()

      expect(inSheet('sample-failure')).toBeNull()
      expect(inSheet('discord-title')).not.toBeNull()
    })

    it('forgets what was on its way when it is closed', async () => {
      const { openIt, makeSample, open, inSheet } = await mountSheet()
      let late: (value: alertsApi.Sample) => void = () => undefined
      makeSample.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await openIt()

      open.value = false
      await flushPromises()
      late(sample({ title: 'Too late' }))
      await flushPromises()
      await openIt()

      expect(inSheet('discord-title')!.textContent).not.toBe('Too late')
    })
  })

  describe('quiet hours', () => {
    it('shows their times only when they are on', async () => {
      const { openIt, set, inSheet } = await mountSheet()
      await openIt()
      expect(inSheet('rules-from')).toBeNull()
      expect(inSheet('rules-critical')).toBeNull()

      await set(VSwitch, 'Quiet hours', true)

      expect(inSheet('rules-from')).not.toBeNull()
      expect(inSheet('rules-until')).not.toBeNull()
      expect(inSheet('rules-zone')).not.toBeNull()
      expect(inSheet('rules-critical')).not.toBeNull()
    })

    it('reads times as minutes after midnight', async () => {
      const { openIt, set, save, saved, component } = await mountSheet()
      await openIt()
      await set(VSwitch, 'Quiet hours', true)
      expect(component(VTextField, 'From').props('modelValue')).toBe('22:00')
      expect(component(VTextField, 'Until').props('modelValue')).toBe('07:00')

      await set(VTextField, 'From', '23:30')
      await set(VTextField, 'Until', '06:15')
      await set(VAutocomplete, 'Time zone', 'Europe/Berlin')
      await set(VSwitch, 'Still send critical threats', false)
      await save()

      expect(saved).toHaveBeenCalledWith(
        rules({
          quiet_hours: true,
          quiet_from: 23 * 60 + 30,
          quiet_until: 6 * 60 + 15,
          time_zone: 'Europe/Berlin',
          quiet_critical: false,
        }),
      )
    })

    it('keeps the time it had when what is typed is not a time', async () => {
      const { openIt, set, component } = await mountSheet()
      await openIt()
      await set(VSwitch, 'Quiet hours', true)

      await set(VTextField, 'From', '')
      await set(VTextField, 'Until', 'later')

      expect(component(VTextField, 'From').props('modelValue')).toBe('22:00')
      expect(component(VTextField, 'Until').props('modelValue')).toBe('07:00')
    })

    it('cannot be saved when they start and end together', async () => {
      const { openIt, set, inSheet } = await mountSheet()
      await openIt()
      await set(VSwitch, 'Quiet hours', true)

      await set(VTextField, 'Until', '22:00')

      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(true)
      await set(VSwitch, 'Quiet hours', false)
      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(false)
    })

    it('offers the time zone it was given even when the system does not list it', async () => {
      const { openIt, component } = await mountSheet({
        destination: destination({
          rules: rules({ quiet_hours: true, time_zone: 'Mars/Olympus' }),
        }),
      })

      await openIt()

      const zones = component(VAutocomplete, 'Time zone').props('items') as string[]
      expect(zones).toContain('Mars/Olympus')
      expect(zones).toContain('UTC')
      expect(zones).toContain('Europe/Berlin')
    })
  })

  describe('saving', () => {
    it('waits while it is saved, and cannot be closed', async () => {
      const { openIt, set, inSheet } = await mountSheet({ busy: true })
      await openIt()
      await set(VSelect, 'How serious', 3)

      expect(inSheet('rules-save')!.hasAttribute('disabled')).toBe(true)
      expect(inSheet('rules-cancel')!.hasAttribute('disabled')).toBe(true)
      expect(inSheet('rules-close')!.hasAttribute('disabled')).toBe(true)
    })

    it('shows what was wrong with a field, and what went wrong that is not about one', async () => {
      const { openIt } = await mountSheet({
        problems: { max_per_hour: 'Use a number from 1 to 60.' },
        failure: 'Something went wrong.',
      })

      await openIt()

      expect(document.body.textContent).toContain('Use a number from 1 to 60.')
      expect(document.querySelector('[data-test="rules-failure"]')!.textContent).toContain(
        'Something went wrong.',
      )
    })

    it('saves nothing that is not ready', async () => {
      const { openIt, save, saved } = await mountSheet()
      await openIt()

      await save()
      document.querySelector('form')!.dispatchEvent(new Event('submit'))
      await flushPromises()

      expect(saved).not.toHaveBeenCalled()
    })

    it('saves from the keyboard', async () => {
      const { openIt, set, saved } = await mountSheet()
      await openIt()
      await set(VSelect, 'How serious', 3)

      document.querySelector('form')!.dispatchEvent(new Event('submit'))
      await flushPromises()

      expect(saved).toHaveBeenCalledTimes(1)
    })

    it('gives the keyboard back to what opened it, once it has gone', async () => {
      const { wrapper, openIt, inSheet } = await mountSheet()
      const opener = wrapper.find<HTMLButtonElement>('[data-test="opener"]').element
      opener.focus()
      await openIt()
      inSheet('rules-cancel')!.click()
      await flushPromises()
      opener.blur()

      wrapper.findComponent(VDialog).vm.$emit('afterLeave')

      expect(document.activeElement).toBe(opener)
    })

    it('closes with its button', async () => {
      const { openIt, inSheet, open } = await mountSheet()
      await openIt()

      inSheet('rules-close')!.click()
      await flushPromises()

      expect(open.value).toBe(false)
    })

    it('closes when the dialog asks to, as it does for the escape key or a tap beside it', async () => {
      const { wrapper, openIt, open } = await mountSheet()
      await openIt()

      wrapper.findComponent(VDialog).vm.$emit('update:modelValue', false)
      await flushPromises()

      expect(open.value).toBe(false)
    })
  })
})
