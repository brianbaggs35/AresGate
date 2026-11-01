import { defineComponent, ref } from 'vue'
import type { MockInstance } from 'vitest'

import { ApiError } from '@/api/client'
import * as interfacesApi from '@/api/interfaces'
import type { Interface, Role } from '@/api/interfaces'
import InterfaceEditor from '@/components/InterfaceEditor.vue'
import { iface } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'

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

interface Props {
  item?: Interface | null
  starter?: { name: string; role: Role; feeds: number[] } | null
  open?: boolean
}

async function open({ item = null, starter = null, open: shown = true }: Props = {}) {
  const visible = ref(shown)
  const saved: string[] = []
  const removed: string[] = []
  const host = defineComponent({
    components: { InterfaceEditor },
    setup: () => ({
      visible,
      item,
      starter,
      saved: (text: string) => saved.push(text),
      removed: (text: string) => removed.push(text),
    }),
    template: `<InterfaceEditor v-model="visible" :interface="item" :starter="starter"
      @saved="saved" @removed="removed" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin', withApp: true })
  await flushPromises()
  return { ...mounted, visible, saved, removed }
}

describe('InterfaceEditor', () => {
  let create: MockInstance<typeof interfacesApi.createInterface>
  let change: MockInstance<typeof interfacesApi.changeInterface>
  let remove: MockInstance<typeof interfacesApi.removeInterface>

  beforeEach(() => {
    create = vi.spyOn(interfacesApi, 'createInterface').mockResolvedValue(iface({ id: 9 }))
    change = vi.spyOn(interfacesApi, 'changeInterface').mockResolvedValue(iface())
    remove = vi.spyOn(interfacesApi, 'removeInterface').mockResolvedValue(undefined)
  })

  describe('making a new interface', () => {
    it('starts empty, as a home network, and cannot be added without a name', async () => {
      await open()

      expect(at('editor-title')!.textContent.trim()).toBe('Add an interface')
      expect(field('editor-name').value).toBe('')
      expect((document.body.querySelector('input[value="home"]') as HTMLInputElement).checked).toBe(
        true,
      )
      expect(at('editor-save')!.hasAttribute('disabled')).toBe(true)
      expect(at('editor-remove')).toBeNull()
    })

    it('adds it with what was filled in, and says so', async () => {
      const { visible, saved } = await open()

      await type('editor-name', '  Guests ')
      ;(document.body.querySelector('input[value="guest"]') as HTMLInputElement).click()
      await type('editor-networks', '192.168.30.0/24, fd00::/64\n10.0.0.0/8')
      await type('editor-notes', ' For visitors ')
      await press('editor-save')

      expect(create).toHaveBeenCalledWith(
        {
          name: 'Guests',
          role: 'guest',
          notes: 'For visitors',
          networks: ['192.168.30.0/24', 'fd00::/64', '10.0.0.0/8'],
          feeds: [],
        },
        TOKEN,
      )
      expect(saved).toEqual(['Guests added.'])
      expect(visible.value).toBe(false)
    })

    it('starts as what a suggestion or a feed said, and places the feeds on it', async () => {
      const { saved } = await open({ starter: { name: 'igc2', role: 'iot', feeds: [4, 5] } })

      expect(field('editor-name').value).toBe('igc2')
      expect((document.body.querySelector('input[value="iot"]') as HTMLInputElement).checked).toBe(
        true,
      )

      await press('editor-save')

      expect(create.mock.calls[0]![0]).toMatchObject({ name: 'igc2', role: 'iot', feeds: [4, 5] })
      expect(saved).toEqual(['igc2 added.'])
    })

    it('says why it was refused, in the words it was given, and stays open', async () => {
      create.mockRejectedValue(
        new ApiError(409, 'There is already an interface named Guests.', 'x'),
      )
      const { visible, saved } = await open({
        starter: { name: 'Guests', role: 'guest', feeds: [] },
      })

      await press('editor-save')

      expect(at('editor-problem')!.textContent).toContain('already an interface named Guests')
      expect(visible.value).toBe(true)
      expect(saved).toEqual([])
      expect(at('editor-save')!.hasAttribute('disabled')).toBe(false)
    })

    it('does nothing when asked to add with no name', async () => {
      await open()

      document.body.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
      await flushPromises()

      expect(create).not.toHaveBeenCalled()
    })

    it('forgets what was typed and said when it is opened again', async () => {
      create.mockRejectedValue(new ApiError(422, 'No.', 'x'))
      const { visible } = await open()
      await type('editor-name', 'Cameras')
      await press('editor-save')
      expect(at('editor-problem')).not.toBeNull()

      visible.value = false
      await flushPromises()
      visible.value = true
      await flushPromises()

      expect(field('editor-name').value).toBe('')
      expect(at('editor-problem')).toBeNull()
    })
  })

  describe('changing one', () => {
    const item = iface({
      id: 3,
      name: 'Internet',
      role: 'internet',
      notes: 'Fibre',
      networks: ['203.0.113.0/24', '198.51.100.0/24'],
    })

    it('starts as it is, and can be removed', async () => {
      await open({ item })

      expect(at('editor-title')!.textContent.trim()).toBe('Edit Internet')
      expect(field('editor-name').value).toBe('Internet')
      expect(field('editor-notes').value).toBe('Fibre')
      expect(field('editor-networks').value).toBe('203.0.113.0/24\n198.51.100.0/24')
      expect(at('editor-save')!.textContent.trim()).toBe('Save')
      expect(at('editor-remove')).not.toBeNull()
    })

    it('saves what was changed, and says so', async () => {
      const { visible, saved } = await open({ item })

      await type('editor-name', 'Fibre')
      await press('editor-save')

      expect(change).toHaveBeenCalledWith(
        3,
        {
          name: 'Fibre',
          role: 'internet',
          notes: 'Fibre',
          networks: ['203.0.113.0/24', '198.51.100.0/24'],
        },
        TOKEN,
      )
      expect(saved).toEqual(['Fibre saved.'])
      expect(visible.value).toBe(false)
    })

    it('can be cancelled or closed without saving', async () => {
      const { visible } = await open({ item })
      await press('editor-cancel')
      expect(visible.value).toBe(false)

      visible.value = true
      await flushPromises()
      await press('editor-close')
      expect(visible.value).toBe(false)
      expect(change).not.toHaveBeenCalled()
    })

    it('asks before removing, and says what happens to its feeds', async () => {
      const { visible } = await open({ item })

      await press('editor-remove')

      expect(at('confirm-title')!.textContent).toBe('Remove Internet?')
      expect(at('confirm-message')!.textContent).toContain('Its feeds stay')
      expect(remove).not.toHaveBeenCalled()
      expect(visible.value).toBe(true)
    })

    it('removes it once that is confirmed, and says so', async () => {
      const { visible, removed } = await open({ item })
      await press('editor-remove')

      await press('confirm-accept')

      expect(remove).toHaveBeenCalledWith(3, TOKEN)
      expect(removed).toEqual(['Internet removed. Its feeds are not placed now.'])
      expect(visible.value).toBe(false)
    })

    it('says why it could not be removed, and closes the question', async () => {
      remove.mockRejectedValue(new ApiError(404, 'That interface is not there.', 'x'))
      const { visible, removed } = await open({ item })
      await press('editor-remove')

      await press('confirm-accept')

      expect(at('confirm-title')).toBeNull()
      expect(at('editor-problem')!.textContent).toContain('not there')
      expect(visible.value).toBe(true)
      expect(removed).toEqual([])
    })
  })
})
