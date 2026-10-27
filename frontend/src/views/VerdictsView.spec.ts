import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import VerdictDialog from '@/components/VerdictDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { verdict } from '@/test/verdicts'
import VerdictsView from '@/views/VerdictsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

const SOME = [
  verdict({
    id: 2,
    verdict: 'low_priority',
    signature: 'ET SCAN',
    source: 'wazuh',
    source_name: 'Wazuh',
  }),
  verdict({ id: 1, note: 'my scanner' }),
]

async function open(answer: verdictsApi.Verdict[] | Error = SOME) {
  const fetchIt = vi.spyOn(verdictsApi, 'fetchVerdicts')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const change = vi.spyOn(verdictsApi, 'changeVerdict')
  const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(VerdictsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const rows = () => mounted.wrapper.findAll('[data-test="verdict-row"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLButtonElement>(`[data-test="${selector}"]`)
  const changing = () => mounted.wrapper.findComponent(VerdictDialog).props('modelValue')
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  const choose = async (index: number, action: 'change' | 'remove') => {
    await rows()[index]?.find(`[data-test="verdict-${action}"]`).trigger('click')
    await flushPromises()
  }
  return {
    ...mounted,
    fetchIt,
    change,
    remove,
    find,
    text,
    rows,
    inDialog,
    changing,
    confirming,
    choose,
  }
}

describe('VerdictsView', () => {
  describe('looking at them', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(verdictsApi, 'fetchVerdicts').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(VerdictsView, { signedIn: 'admin' })

      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
    })

    it('lists each verdict, the one given last first', async () => {
      const { rows } = await open()

      expect(rows()).toHaveLength(2)
      expect(rows()[0]?.find('[data-test="verdict-about"]').text()).toBe(
        '“ET SCAN” from 93.184.216.34, as seen by Wazuh',
      )
      expect(rows()[1]?.find('[data-test="verdict-why"]').text()).toBe('Why: my scanner')
    })

    it('says none have been given, and where to give one', async () => {
      const { text, find } = await open([])

      expect(text('no-verdicts')).toContain("You haven't given a verdict yet")
      expect(find('see-incidents').attributes('href')).toBe('/incidents')
      expect(find('verdict-list').exists()).toBe(false)
    })

    it('says so when they cannot be loaded, and loads once they can', async () => {
      const { find, fetchIt, rows } = await open(offline())
      expect(find('verdicts-error').exists()).toBe(true)
      expect(find('verdict-list').exists()).toBe(false)

      fetchIt.mockResolvedValue(SOME)
      await find('verdicts-error').find('button').trigger('click')
      await flushPromises()

      expect(rows()).toHaveLength(2)
    })

    it('asks again by the button', async () => {
      const { find, fetchIt, rows } = await open()
      fetchIt.mockResolvedValue([verdict({ id: 3 })])

      await find('refresh-verdicts').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(rows()).toHaveLength(1)
    })
  })

  describe('changing one', () => {
    it('opens a dialog for the one chosen', async () => {
      const { choose, changing, inDialog } = await open()

      await choose(1, 'change')

      expect(changing()).toBe(true)
      expect(inDialog('dialog-about')?.textContent.trim()).toBe('93.184.216.34')
    })

    it('closes without changing anything when it is cancelled', async () => {
      const { choose, change, inDialog, changing, rows } = await open()
      await choose(1, 'change')

      inDialog('dialog-cancel')!.click()
      await flushPromises()

      expect(changing()).toBe(false)
      expect(change).not.toHaveBeenCalled()
      expect(rows()[1]?.find('[data-test="verdict"]').text()).toBe('Not suspicious')
    })

    it('saves what was chosen, and shows the verdict as it is now', async () => {
      const { choose, change, inDialog, text, rows, changing } = await open()
      change.mockResolvedValue(verdict({ id: 1, verdict: 'threat', note: null, hits: 14 }))
      await choose(1, 'change')

      inDialog('say-threat')!.querySelector('input')!.click()
      await flushPromises()
      inDialog('dialog-save')!.click()
      await flushPromises()
      await flushPromises()

      expect(change).toHaveBeenCalledWith(
        1,
        { verdict: 'threat', note: 'my scanner' },
        'a-security-token',
      )
      expect(rows()[1]?.find('[data-test="verdict"]').text()).toBe('Real threat')
      expect(rows()[1]?.find('[data-test="verdict-why"]').exists()).toBe(false)
      expect(text('verdicts-notice')).toBe('Changed: 93.184.216.34.')
      expect(changing()).toBe(false)
    })

    it('says why it could not be saved, and keeps the verdict as it was', async () => {
      const { choose, change, inDialog, text, rows, changing } = await open()
      change.mockRejectedValue(offline())
      await choose(1, 'change')

      inDialog('dialog-save')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('verdicts-failure')).toContain("Can't reach AresGate.")
      expect(rows()[1]?.find('[data-test="verdict"]').text()).toBe('Not suspicious')
      expect(changing()).toBe(false)
    })
  })

  describe('taking one back', () => {
    it('asks first, saying what it was about and how many signals it was applied to', async () => {
      const { choose, confirming, inDialog } = await open()

      await choose(1, 'remove')

      expect(confirming()).toBe(true)
      expect(inDialog('confirm-message')?.textContent).toContain('93.184.216.34')
      expect(inDialog('confirm-message')?.textContent).toContain(
        '12 signals it was applied to are judged again',
      )
    })

    it('says it has not been applied to anything, when it has not', async () => {
      const { choose, inDialog } = await open([verdict({ hits: 0, last_hit_at: null })])

      await choose(0, 'remove')

      expect(inDialog('confirm-message')?.textContent).toContain(
        'It has not been applied to a signal yet.',
      )
    })

    it('says signal, not signals, for one', async () => {
      const { choose, inDialog } = await open([verdict({ hits: 1 })])

      await choose(0, 'remove')

      expect(inDialog('confirm-message')?.textContent).toContain(
        '1 signal it was applied to is judged again',
      )
    })

    it('takes it back once it is confirmed, and says so', async () => {
      const { choose, remove, inDialog, rows, text, confirming } = await open()
      await choose(1, 'remove')

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith(1, 'a-security-token')
      expect(rows()).toHaveLength(1)
      expect(text('verdicts-notice')).toBe('Taken back: 93.184.216.34.')
      expect(confirming()).toBe(false)
    })

    it('does nothing if the question is cancelled', async () => {
      const { choose, remove, inDialog, rows, confirming } = await open()
      await choose(1, 'remove')

      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(remove).not.toHaveBeenCalled()
      expect(rows()).toHaveLength(2)
      expect(confirming()).toBe(false)
    })

    it('says why it could not be taken back, and keeps it listed', async () => {
      const { choose, remove, inDialog, rows, text } = await open()
      remove.mockRejectedValue(offline())
      await choose(1, 'remove')

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('verdicts-failure')).toContain("Can't reach AresGate.")
      expect(rows()).toHaveLength(2)
    })

    it('forgets the last answer when another is asked for', async () => {
      const { choose, remove, inDialog, find } = await open()
      remove.mockRejectedValueOnce(offline())
      await choose(1, 'remove')
      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()
      expect(find('verdicts-failure').exists()).toBe(true)

      await choose(0, 'change')

      expect(find('verdicts-failure').exists()).toBe(false)
    })
  })
})
