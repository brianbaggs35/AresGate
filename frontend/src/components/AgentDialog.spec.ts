import type { MockInstance } from 'vitest'
import { defineComponent, ref } from 'vue'

import * as agentsApi from '@/api/agents'
import type { Agent, Template } from '@/api/agents'
import { ApiError } from '@/api/client'
import AgentDialog from '@/components/AgentDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { SCANNER, agent, template } from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const HUNTER = template()
const ANALYST = template({
  key: 'intelligence_analyst',
  name: 'Intelligence analyst',
  tagline: 'Checks who is behind the traffic',
  goal: 'Point out addresses that several engines flag.',
  interval_minutes: 360,
})
const TEMPLATES: Template[] = [HUNTER, ANALYST, SCANNER]

/** What is in an open window, which is outside the component itself. */
const at = (selector: string) =>
  document.body.querySelector<HTMLElement>(`.v-overlay--active [data-test="${selector}"]`)

const field = (selector: string) =>
  at(selector)!.querySelector<HTMLInputElement | HTMLTextAreaElement>('input, textarea')!

async function type(selector: string, value: string) {
  const input = field(selector)
  input.value = value
  input.dispatchEvent(new Event('input'))
  await flushPromises()
}

async function press(selector: string) {
  at(selector)!.click()
  await flushPromises()
  await flushPromises()
}

async function choose(key: string) {
  const radio = document.body.querySelector<HTMLInputElement>(
    `.v-overlay--active input[value="${key}"]`,
  )!
  radio.click()
  await flushPromises()
}

interface Props {
  item?: Agent | null
  starter?: string | null
  templates?: Template[]
}

async function open({ item = null, starter = null, templates = TEMPLATES }: Props = {}) {
  const visible = ref(true)
  const saved: [string, number][] = []
  const removed: string[] = []
  const host = defineComponent({
    components: { AgentDialog },
    setup: () => ({
      visible,
      item,
      starter,
      templates,
      saved: (text: string, made: Agent) => saved.push([text, made.id]),
      removed: (text: string) => removed.push(text),
    }),
    template: `<AgentDialog v-model="visible" :agent="item" :templates="templates" :starter="starter"
      @saved="saved" @removed="removed" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin', withApp: true })
  await flushPromises()
  return { ...mounted, visible, saved, removed }
}

describe('AgentDialog', () => {
  let create: MockInstance<typeof agentsApi.createAgent>
  let change: MockInstance<typeof agentsApi.changeAgent>
  let remove: MockInstance<typeof agentsApi.removeAgent>

  beforeEach(() => {
    create = vi.spyOn(agentsApi, 'createAgent').mockResolvedValue(agent({ id: 9 }))
    change = vi.spyOn(agentsApi, 'changeAgent').mockResolvedValue(agent())
    remove = vi.spyOn(agentsApi, 'removeAgent').mockResolvedValue(undefined)
  })

  describe('making an agent', () => {
    it('offers each kind and starts as the first, with what it starts with', async () => {
      await open()

      expect(at('dialog-title')!.textContent.trim()).toBe('Make an agent')
      expect(
        document.body.querySelectorAll('.v-overlay--active [data-test="dialog-kind"]'),
      ).toHaveLength(3)
      expect(field('dialog-name').value).toBe('Threat hunter')
      expect(field('dialog-goal').value).toBe(HUNTER.goal)
      expect(at('dialog-about')!.textContent).toContain('Reads the incidents')
      expect(at('dialog-interval')).not.toBeNull()
      expect(at('dialog-remove')).toBeNull()
    })

    it('starts as the kind it was asked to', async () => {
      await open({ starter: 'intelligence_analyst' })

      expect(field('dialog-name').value).toBe('Intelligence analyst')
      expect(field('dialog-goal').value).toBe(ANALYST.goal)
    })

    it('starts as the first kind when it is asked for one that is not there', async () => {
      await open({ starter: 'gone' })

      expect(field('dialog-name').value).toBe('Threat hunter')
    })

    it('has nothing to start from when there are no kinds, and cannot be made', async () => {
      await open({ templates: [] })

      expect(field('dialog-name').value).toBe('')
      expect(at('dialog-about')).toBeNull()
      expect(at('dialog-save')!.hasAttribute('disabled')).toBe(true)
    })

    it('takes on what another kind starts with, but keeps a name that was typed', async () => {
      await open()

      await choose('intelligence_analyst')
      expect(field('dialog-name').value).toBe('Intelligence analyst')
      expect(field('dialog-goal').value).toBe(ANALYST.goal)

      await type('dialog-name', 'My watcher')
      await choose('threat_hunter')

      expect(field('dialog-name').value).toBe('My watcher')
      expect(field('dialog-goal').value).toBe(HUNTER.goal)
    })

    it('makes it with what was filled in, and says so', async () => {
      const { visible, saved } = await open()

      await type('dialog-name', '  Night watch ')
      await type('dialog-goal', ' Watch the cameras ')
      await press('dialog-save')

      expect(create).toHaveBeenCalledWith(
        'threat_hunter',
        {
          name: 'Night watch',
          goal: 'Watch the cameras',
          interval_minutes: 60,
          enabled: true,
          allow_active: false,
        },
        TOKEN,
      )
      expect(saved).toEqual([['Night watch is ready.', 9]])
      expect(visible.value).toBe(false)
    })

    it('can be set to run on a schedule it can be switched off', async () => {
      await open()

      expect(at('dialog-enabled')).not.toBeNull()
      field('dialog-enabled').click()
      await flushPromises()
      await press('dialog-save')

      expect(create.mock.calls[0]![1]).toMatchObject({ interval_minutes: 60, enabled: false })
    })

    it('takes the schedule that was chosen', async () => {
      const { wrapper } = await open()

      wrapper.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 120)
      await flushPromises()
      await press('dialog-save')

      expect(create.mock.calls[0]![1]).toMatchObject({ interval_minutes: 120 })
    })

    it('closes when the window asks to, as when the owner clicks outside it', async () => {
      const { wrapper, visible } = await open()

      wrapper.findComponent({ name: 'VDialog' }).vm.$emit('update:modelValue', false)
      await flushPromises()

      expect(visible.value).toBe(false)
    })

    it('has no schedule to switch when it runs only when started', async () => {
      await open()
      await choose('exposure_scanner')
      expect(at('dialog-enabled')).toBeNull()
    })

    it('says what a kind that tests the network does, and is never on a schedule', async () => {
      await open()

      await choose('exposure_scanner')

      expect(at('dialog-interval')).toBeNull()
      expect(at('dialog-active')!.textContent).toContain('never by itself')
      expect(at('dialog-active')!.textContent).toContain('never sends anything else')
      await press('dialog-save')
      expect(create.mock.calls[0]![1]).toMatchObject({
        interval_minutes: null,
        allow_active: false,
      })
    })

    it('allows it to test the network only when the owner turns that on', async () => {
      await open()
      await choose('exposure_scanner')

      field('dialog-allow').click()
      await flushPromises()
      await press('dialog-save')

      expect(create).toHaveBeenCalledWith(
        'exposure_scanner',
        expect.objectContaining({ allow_active: true, interval_minutes: null }),
        TOKEN,
      )
    })

    it('says why it was refused, in the words it was given, and stays open', async () => {
      create.mockRejectedValue(new ApiError(422, 'That isn’t a kind of agent.', 'x'))
      const { visible, saved } = await open()

      await press('dialog-save')

      expect(at('dialog-problem')!.textContent).toContain('isn’t a kind of agent')
      expect(visible.value).toBe(true)
      expect(saved).toEqual([])
      expect(at('dialog-save')!.hasAttribute('disabled')).toBe(false)
    })

    it('does nothing when asked to make one with no name', async () => {
      await open()
      await type('dialog-name', '  ')

      document.body.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
      await flushPromises()

      expect(create).not.toHaveBeenCalled()
    })

    it('forgets what was typed and said when it is opened again', async () => {
      create.mockRejectedValue(new ApiError(422, 'No.', 'x'))
      const { visible } = await open()
      await type('dialog-name', 'Cameras')
      await press('dialog-save')
      expect(at('dialog-problem')).not.toBeNull()

      visible.value = false
      await flushPromises()
      visible.value = true
      await flushPromises()

      expect(field('dialog-name').value).toBe('Threat hunter')
      expect(at('dialog-problem')).toBeNull()
    })
  })

  describe('changing one', () => {
    const item = agent({
      id: 3,
      name: 'Night watch',
      goal: 'Watch the cameras.',
      interval_minutes: 120,
    })

    it('starts as it is, without the choice of kind, and can be removed', async () => {
      await open({ item, templates: [HUNTER] })

      expect(at('dialog-title')!.textContent.trim()).toBe('Edit Night watch')
      expect(field('dialog-name').value).toBe('Night watch')
      expect(field('dialog-goal').value).toBe('Watch the cameras.')
      expect(document.body.querySelector('.v-overlay--active [data-test="dialog-kind"]')).toBeNull()
      expect(at('dialog-save')!.textContent.trim()).toBe('Save')
      expect(at('dialog-remove')).not.toBeNull()
    })

    it('saves what was changed, and says so', async () => {
      const { visible, saved } = await open({ item, templates: [HUNTER] })

      await type('dialog-name', 'Day watch')
      await press('dialog-save')

      expect(change).toHaveBeenCalledWith(
        3,
        {
          name: 'Day watch',
          goal: 'Watch the cameras.',
          interval_minutes: 120,
          enabled: true,
          allow_active: false,
        },
        TOKEN,
      )
      expect(saved).toEqual([['Day watch saved.', 3]])
      expect(visible.value).toBe(false)
    })

    it('keeps what a kind that tests the network was allowed', async () => {
      const scanner = agent({
        id: 4,
        template: 'exposure_scanner',
        active: true,
        allow_active: true,
        interval_minutes: null,
      })
      await open({ item: scanner, templates: [SCANNER] })

      await press('dialog-save')

      expect(change).toHaveBeenCalledWith(
        4,
        expect.objectContaining({ allow_active: true, interval_minutes: null }),
        TOKEN,
      )
    })

    it('shows one whose kind is gone, which can be changed but not told what the kind does', async () => {
      await open({ item: agent({ id: 5, template: 'retired', active: false }), templates: [] })

      expect(at('dialog-about')).toBeNull()
      expect(at('dialog-save')!.hasAttribute('disabled')).toBe(false)
    })

    it('can be cancelled or closed without saving', async () => {
      const { visible } = await open({ item, templates: [HUNTER] })
      await press('dialog-cancel')
      expect(visible.value).toBe(false)

      visible.value = true
      await flushPromises()
      await press('dialog-close')
      expect(visible.value).toBe(false)
      expect(change).not.toHaveBeenCalled()
    })

    it('asks before removing, and says its runs go with it', async () => {
      const { visible } = await open({ item, templates: [HUNTER] })

      await press('dialog-remove')

      expect(at('confirm-title')!.textContent).toBe('Remove Night watch?')
      expect(at('confirm-message')!.textContent).toContain('runs and what they found are deleted')
      expect(remove).not.toHaveBeenCalled()
      expect(visible.value).toBe(true)
    })

    it('forgets the question when the confirmation closes, and removes nothing', async () => {
      const { wrapper, visible, removed } = await open({ item, templates: [HUNTER] })
      await press('dialog-remove')

      wrapper.findComponent(ConfirmDialog).vm.$emit('update:modelValue', false)
      await flushPromises()

      expect(wrapper.findComponent(ConfirmDialog).props('modelValue')).toBe(false)
      expect(remove).not.toHaveBeenCalled()
      expect(removed).toEqual([])
      expect(visible.value).toBe(true)
    })

    it('removes it once that is confirmed, and says so', async () => {
      const { visible, removed } = await open({ item, templates: [HUNTER] })
      await press('dialog-remove')

      await press('confirm-accept')

      expect(remove).toHaveBeenCalledWith(3, TOKEN)
      expect(removed).toEqual(['Night watch removed, with its runs.'])
      expect(visible.value).toBe(false)
    })

    it('says why it could not be removed, and closes the question', async () => {
      remove.mockRejectedValue(new ApiError(404, 'There is no such agent.', 'x'))
      const { visible, removed } = await open({ item, templates: [HUNTER] })
      await press('dialog-remove')

      await press('confirm-accept')

      expect(at('confirm-title')).toBeNull()
      expect(at('dialog-problem')!.textContent).toContain('no such agent')
      expect(visible.value).toBe(true)
      expect(removed).toEqual([])
    })
  })
})
