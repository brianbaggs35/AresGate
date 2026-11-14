import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as api from '@/api/integrations'
import type { Call } from '@/api/integrations'
import ApiCallDialog from '@/components/ApiCallDialog.vue'
import { call, callDetail, callFull } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const first = call({ id: 2 })
const second = call({ id: 1, method: 'POST', path: '/other' })

async function mountSheet(
  options: {
    call?: Call | null
    open?: boolean
    older?: boolean
    newer?: boolean
    connection?: string | null
    width?: number
  } = {},
) {
  const shown = ref<Call | null>(options.call === undefined ? first : options.call)
  const open = ref(options.open ?? true)
  const flags = ref({ older: options.older ?? true, newer: options.newer ?? true })
  const stepped = vi.fn<(direction: string) => void>()
  const Page = defineComponent({
    render: () =>
      h(ApiCallDialog, {
        modelValue: open.value,
        'onUpdate:modelValue': (value: boolean) => (open.value = value),
        integration: 'ntopng',
        call: shown.value,
        connection: options.connection ?? null,
        hasOlder: flags.value.older,
        hasNewer: flags.value.newer,
        onStep: stepped,
      }),
  })
  const mounted = await mountWithPlugins(Page, {
    withApp: true,
    signedIn: 'admin',
    width: options.width,
  })
  await flushPromises()
  const inSheet = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  /** What is written in it, a space between the parts that are laid out apart. */
  const text = (selector: string) => {
    const walker = document.createTreeWalker(
      inSheet(selector) ?? document.body,
      NodeFilter.SHOW_TEXT,
    )
    const words: string[] = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const said = (node.textContent ?? '').replaceAll(/\s+/g, ' ').trim()
      if (said) words.push(said)
    }
    return words.join(' ')
  }
  const click = async (selector: string) => {
    inSheet(selector)?.click()
    await flushPromises()
  }
  const press = async (key: string, modifiers: KeyboardEventInit = {}) => {
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...modifiers }))
    await flushPromises()
  }
  return { ...mounted, shown, open, flags, stepped, inSheet, text, click, press }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ApiCallDialog', () => {
  it('is closed until it is opened, and asks for nothing while it is', async () => {
    const fetch = vi.spyOn(api, 'fetchCall')
    const { inSheet } = await mountSheet({ open: false })

    expect(inSheet('call-sheet')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows nothing where there is no request', async () => {
    const fetch = vi.spyOn(api, 'fetchCall')
    const { inSheet } = await mountSheet({ call: null })

    expect(inSheet('call-sheet')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows what the list had at once, while it asks for the rest', async () => {
    vi.spyOn(api, 'fetchCall').mockReturnValue(new Promise(() => undefined))
    const { text, inSheet } = await mountSheet()

    expect(text('sheet-title')).toBe('GET /lua/rest/v2/get/ntopng/interfaces.lua')
    expect(text('sheet-result')).toBe('200')
    expect(inSheet('sheet-loading')).not.toBeNull()
    expect(inSheet('sheet-address')).toBeNull()
  })

  it('names the dialog by the request', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const { inSheet } = await mountSheet()

    const dialog = document.querySelector('[role="dialog"]')
    expect(dialog?.getAttribute('aria-labelledby')).toBe(inSheet('sheet-title')?.id)
  })

  it('shows where the request went, with the credentials hidden', async () => {
    const fetch = vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const { text, inSheet } = await mountSheet({ connection: 'REST API' })

    expect(fetch).toHaveBeenCalledWith('ntopng', 2)
    expect(text('sheet-address')).toContain(
      'https://192.168.1.1:8443/lua/rest/v2/get/ntopng/interfaces.lua?ifid=0&token=***',
    )
    expect(text('sheet-connection')).toBe('REST API')
    expect(text('sheet-caller')).toBe('ntopng collector interfaces')
    expect(text('sheet-query')).toBe('ifid 0 token hidden')
    expect(text('sheet-request-headers')).toBe('accept application/json authorization hidden')
    expect(
      inSheet('sheet-address')?.querySelector('[aria-label="Copy the address"]'),
    ).not.toBeNull()
    expect(
      inSheet('sheet-address')?.querySelector('[aria-label="Copy as a curl command"]'),
    ).not.toBeNull()
  })

  it('says when it is not known who made the request, and leaves out a query that is not there', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(
      callFull({ detail: callDetail({ caller: null, query: [] }) }),
    )
    const { text, inSheet } = await mountSheet()

    expect(text('sheet-caller')).toBe('Not recorded')
    expect(inSheet('sheet-query')).toBeNull()
    expect(inSheet('sheet-connection')).toBeNull()
  })

  it('shows how long it took and how it was answered', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const { text, inSheet } = await mountSheet()

    expect(text('sheet-timing')).toBe('Until the answer began 30 ms Whole request 42 ms')
    expect(text('sheet-result')).toBe('HTTP/1.1 200 OK')
    expect(text('sheet-answer-facts')).toBe(
      'Status HTTP/1.1 200 OK Type application/json Size 2.0 KB Came from 192.168.1.1',
    )
    expect(text('sheet-response-headers')).toBe('content-type application/json')
    expect(text('sheet-certificate')).toContain('Subject CN=ntopng')
    expect(text('sheet-certificate')).toContain('Issuer CN=Home CA')
    expect(text('sheet-certificate')).toContain('Fingerprint AA:BB:CC')
    expect(inSheet('sheet-unanswered')).toBeNull()
  })

  it('says when the answer was cut', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(
      callFull({ detail: callDetail({ cut: true, certificate: null, content_type: null }) }),
    )
    const { text, inSheet } = await mountSheet()

    expect(text('sheet-size')).toContain('(cut: only what was asked for was read)')
    expect(inSheet('sheet-certificate')).toBeNull()
    expect(text('sheet-answer-facts')).not.toContain('Type')
  })

  it('shows the start of the answer as plain text, and offers to copy it', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(
      callFull({ excerpt: '<img src=x onerror=alert(1)>' }),
    )
    const { inSheet } = await mountSheet()

    const excerpt = inSheet('sheet-excerpt')
    expect(excerpt?.textContent).toBe('<img src=x onerror=alert(1)>')
    expect(excerpt?.querySelector('img')).toBeNull()
    expect(document.querySelector('[aria-label="Copy the answer"]')).not.toBeNull()
  })

  it('says why there is no start of an answer', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull({ excerpt: null }))
    const { text, inSheet } = await mountSheet()

    expect(inSheet('sheet-excerpt')).toBeNull()
    expect(text('sheet-no-excerpt')).toContain('No answer was kept.')
    expect(document.querySelector('[aria-label="Copy the answer"]')).toBeNull()
  })

  it('says so when no answer came, and why', async () => {
    const failed = call({ id: 2, status_code: null, error: "10.0.0.1:443 didn't answer in time." })
    vi.spyOn(api, 'fetchCall').mockResolvedValue(
      callFull({
        ...failed,
        excerpt: null,
        detail: callDetail({ first_byte_ms: undefined, status_line: undefined }),
      }),
    )
    const { text, inSheet } = await mountSheet({ call: failed })

    expect(text('sheet-result')).toBe('No answer')
    expect(text('sheet-error')).toBe("10.0.0.1:443 didn't answer in time.")
    expect(text('sheet-unanswered')).toBe('No answer came.')
    expect(inSheet('sheet-answer-facts')).toBeNull()
    expect(text('sheet-timing')).toBe('Whole request 42 ms')
  })

  it('does not call a limit that held a request back a failure', async () => {
    const held = call({ id: 2, status_code: 429, error: 'Too Many Requests' })
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull({ ...held }))
    const { text } = await mountSheet({ call: held })

    expect(text('sheet-error')).toBe(
      "Too Many Requests . A limit held it back, which isn't a failure.",
    )
  })

  it('says what is missing for a request made before more was kept', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull({ detail: null, excerpt: null }))
    const { text, inSheet } = await mountSheet()

    expect(text('sheet-old')).toContain('so the rest was not kept')
    expect(text('sheet-result')).toBe('200')
    expect(inSheet('sheet-address')).toBeNull()
    expect(inSheet('sheet-caller')).toBeNull()
  })

  it('has a card of its own width on a desktop', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const mounted = await mountSheet({ width: 1400 })

    expect(mounted.wrapper.findComponent(VDialog).props('fullscreen')).toBe(false)
  })

  it('fills the screen on a phone', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const mounted = await mountSheet({ width: 400 })

    expect(mounted.wrapper.findComponent(VDialog).props('fullscreen')).toBe(true)
  })

  describe('going to another request', () => {
    it('has buttons for the older and the newer, which are off where there is none', async () => {
      vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
      const { inSheet, click, stepped, flags } = await mountSheet()

      await click('sheet-older')
      await click('sheet-newer')
      expect(stepped.mock.calls).toEqual([['older'], ['newer']])

      flags.value = { older: false, newer: false }
      await flushPromises()
      expect(inSheet('sheet-older')?.hasAttribute('disabled')).toBe(true)
      expect(inSheet('sheet-newer')?.hasAttribute('disabled')).toBe(true)
    })

    it('is j for the older and k for the newer', async () => {
      vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
      const { press, stepped } = await mountSheet()

      await press('j')
      await press('k')

      expect(stepped.mock.calls).toEqual([['older'], ['newer']])
    })

    it('is not heard while typing, with another key held, where there is nothing, or once closed', async () => {
      vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
      const { press, stepped, open, flags } = await mountSheet()
      const field = document.body.appendChild(document.createElement('input'))

      field.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))
      await press('j', { ctrlKey: true })
      await press('j', { metaKey: true })
      await press('k', { altKey: true })
      await press('x')
      expect(stepped).not.toHaveBeenCalled()

      flags.value = { older: false, newer: false }
      await flushPromises()
      await press('j')
      await press('k')
      expect(stepped).not.toHaveBeenCalled()

      flags.value = { older: true, newer: true }
      open.value = false
      await flushPromises()
      await press('j')
      expect(stepped).not.toHaveBeenCalled()
      field.remove()
    })

    it('stops listening when it is taken away while open', async () => {
      vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
      const { stepped, wrapper } = await mountSheet()

      wrapper.unmount()
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))

      expect(stepped).not.toHaveBeenCalled()
    })

    it('asks for the request it is given, and drops the answer for one it has left', async () => {
      let answerFirst: (found: ReturnType<typeof callFull>) => void = () => undefined
      const fetch = vi
        .spyOn(api, 'fetchCall')
        .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
        .mockResolvedValueOnce(callFull({ ...second, excerpt: 'second' }))
      const { shown, inSheet, text } = await mountSheet()

      shown.value = second
      await flushPromises()
      answerFirst(callFull({ excerpt: 'first' }))
      await flushPromises()

      expect(fetch.mock.calls).toEqual([
        ['ntopng', 2],
        ['ntopng', 1],
      ])
      expect(inSheet('sheet-excerpt')?.textContent).toBe('second')
      expect(text('sheet-title')).toBe('POST /other')
    })
  })

  it('is closed by its button', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const { click, open } = await mountSheet()

    await click('sheet-close')

    expect(open.value).toBe(false)
  })

  it('is closed by the dialog itself, as with the Escape key', async () => {
    vi.spyOn(api, 'fetchCall').mockResolvedValue(callFull())
    const { open } = await mountSheet()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(open.value).toBe(false)
  })

  describe('when the request cannot be read', () => {
    it('says why, keeps what the list had, and tries again on request', async () => {
      const fetch = vi
        .spyOn(api, 'fetchCall')
        .mockRejectedValueOnce(new ApiError(404, "That request isn't there.", 'not_found'))
        .mockResolvedValueOnce(callFull())
      const { inSheet, click, text } = await mountSheet()

      expect(document.body.textContent).toContain("That request isn't there.")
      expect(text('sheet-title')).toContain('/lua/rest/v2/get/ntopng/interfaces.lua')
      expect(inSheet('sheet-loading')).toBeNull()

      await click('sheet-retry')

      expect(fetch).toHaveBeenCalledTimes(2)
      expect(document.body.textContent).not.toContain("That request isn't there.")
      expect(inSheet('sheet-address')).not.toBeNull()
    })

    it('drops the error of a request it has left', async () => {
      let failFirst: (error: Error) => void = () => undefined
      vi.spyOn(api, 'fetchCall')
        .mockReturnValueOnce(new Promise((_resolve, reject) => (failFirst = reject)))
        .mockResolvedValueOnce(callFull())
      const { shown } = await mountSheet()

      shown.value = second
      await flushPromises()
      failFirst(new Error('late'))
      await flushPromises()

      expect(document.body.textContent).not.toContain('late')
    })
  })
})
