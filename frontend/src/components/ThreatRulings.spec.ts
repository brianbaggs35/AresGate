import { ApiError } from '@/api/client'
import * as threatIntel from '@/api/threatIntel'
import type { Ruling } from '@/api/threatIntel'
import ThreatRulings from '@/components/ThreatRulings.vue'
import ThreatRulingDialog from '@/components/ThreatRulingDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { SAFE_RULING } from '@/test/threatIntel'

const SUSPICIOUS: Ruling = {
  kind: 'domain',
  subject: 'tidy.example.org',
  verdict: 'suspicious',
  note: null,
  set_at: '2026-11-10T09:00:00Z',
  judgement: 'suspicious',
}

async function mountRulings(result: Ruling[] | Error = [SAFE_RULING, SUSPICIOUS]) {
  const fetch = vi.spyOn(threatIntel, 'fetchRulings')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue({ items: result })
  const mounted = await mountWithPlugins(ThreatRulings, {
    signedIn: 'brian',
    props: { version: 0 },
  })
  await flushPromises()
  const { wrapper } = mounted
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  const rows = () => wrapper.findAll('[data-test="ruling-row"]')
  const dialog = () => wrapper.findComponent(ThreatRulingDialog)
  const type = async (text: string) => {
    await find('rulings-subject').find('input').setValue(text)
  }
  return { ...mounted, fetch, find, rows, dialog, type }
}

describe('ThreatRulings', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists what the owner ruled, with what it was, what kind of thing it is, when and why', async () => {
    const { rows } = await mountRulings()

    expect(rows().map((row) => row.find('[data-test="ruling-subject-name"]').text())).toEqual([
      '93.184.216.34',
      'tidy.example.org',
    ])
    expect(rows().map((row) => row.find('[data-test="ruling-verdict"]').text())).toEqual([
      'Safe',
      'Suspicious',
    ])
    expect(rows()[0]?.text()).toContain('IP address')
    expect(rows()[0]?.text()).toContain('Ruled ')
    expect(rows()[0]?.find('[data-test="ruling-note-text"]').text()).toBe("“My friend's server”")
    expect(rows()[1]?.find('[data-test="ruling-note-text"]').exists()).toBe(false)
  })

  it('says nothing is ruled yet, and still offers to rule on something', async () => {
    const { find } = await mountRulings([])

    expect(find('rulings-empty').text()).toContain('Nothing is ruled yet')
    expect(find('rulings-form').exists()).toBe(true)
  })

  it('says the list could not be read and tries again', async () => {
    const { find, fetch } = await mountRulings(new ApiError(500, 'The server could not answer.'))
    expect(find('threat-rulings-error').exists()).toBe(true)
    fetch.mockResolvedValue({ items: [SAFE_RULING] })

    await find('threat-rulings-retry').trigger('click')
    await flushPromises()

    expect(find('rulings-list').exists()).toBe(true)
  })

  it('has nothing to rule on until something is typed, then opens the window on what was typed', async () => {
    const { find, type, dialog } = await mountRulings()
    expect(find('rulings-rule').attributes('disabled')).toBeDefined()
    expect(dialog().exists()).toBe(false)

    await type('  203.0.113.7  ')
    await find('rulings-form').trigger('submit')

    expect(dialog().props('subject')).toBe('203.0.113.7')
    expect(dialog().props('ruling')).toBeNull()
    expect(dialog().props('modelValue')).toBe(true)
  })

  it('does not open the window on nothing', async () => {
    const { find, type, dialog } = await mountRulings()
    await type('   ')

    await find('rulings-form').trigger('submit')

    expect(dialog().exists()).toBe(false)
  })

  it('opens the window on a ruling to change it, which starts from what was ruled', async () => {
    const { rows, dialog } = await mountRulings()

    await rows()[1]?.find('[data-test="ruling-change"]').trigger('click')

    expect(dialog().props('subject')).toBe('tidy.example.org')
    expect(dialog().props('ruling')).toEqual(SUSPICIOUS)
  })

  it('reads the list again and tells the page when a ruling is made in the window', async () => {
    const { wrapper, find, type, dialog, fetch } = await mountRulings([])
    await type('203.0.113.7')
    await find('rulings-form').trigger('submit')
    fetch.mockResolvedValue({ items: [SAFE_RULING] })

    dialog().vm.$emit('changed', SAFE_RULING)
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(find('rulings-list').exists()).toBe(true)
  })

  it('takes a ruling back, reads the list again and tells the page', async () => {
    const back = vi.spyOn(threatIntel, 'takeBackRuling').mockResolvedValue(undefined)
    const { wrapper, rows, fetch } = await mountRulings()
    fetch.mockResolvedValue({ items: [SUSPICIOUS] })

    await rows()[0]?.find('[data-test="ruling-remove"]').trigger('click')
    await flushPromises()

    expect(back).toHaveBeenCalledWith('93.184.216.34', 'a-security-token')
    expect(rows()).toHaveLength(1)
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('says why a ruling could not be taken back and leaves it', async () => {
    vi.spyOn(threatIntel, 'takeBackRuling').mockRejectedValue(
      new ApiError(404, 'Nothing is ruled of that.'),
    )
    const { wrapper, rows, find } = await mountRulings()

    await rows()[0]?.find('[data-test="ruling-remove"]').trigger('click')
    await flushPromises()

    expect(find('rulings-problem').text()).toBe('Nothing is ruled of that.')
    expect(rows()).toHaveLength(2)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('takes back one ruling at a time', async () => {
    let finish: () => void = () => undefined
    const back = vi.spyOn(threatIntel, 'takeBackRuling').mockReturnValue(
      new Promise((resolve) => {
        finish = () => {
          resolve(undefined)
        }
      }),
    )
    const { rows } = await mountRulings()

    await rows()[0]?.find('[data-test="ruling-remove"]').trigger('click')
    await rows()[1]?.find('[data-test="ruling-remove"]').trigger('click')
    finish()
    await flushPromises()

    expect(back).toHaveBeenCalledTimes(1)
  })

  it('reads the list again when the page says something was ruled', async () => {
    const { wrapper, fetch } = await mountRulings()

    await wrapper.setProps({ version: 1 })
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
