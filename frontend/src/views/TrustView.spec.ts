import { ApiError } from '@/api/client'
import * as trustApi from '@/api/trust'
import type { Suggestion, TrustList } from '@/api/trust'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import TrustDialog from '@/components/TrustDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { suggestion, trustList, trustRule } from '@/test/trust'
import TrustView from '@/views/TrustView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(
  answer: TrustList | Error = trustList(),
  suggestions: Suggestion[] | Error = [],
) {
  const fetchIt = vi.spyOn(trustApi, 'fetchTrust')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const ideas = vi.spyOn(trustApi, 'fetchSuggestions')
  if (suggestions instanceof Error) ideas.mockRejectedValue(suggestions)
  else ideas.mockResolvedValue(suggestions)
  const revoke = vi.spyOn(trustApi, 'revokeTrust').mockResolvedValue(undefined)
  const post = vi.spyOn(trustApi, 'trust').mockResolvedValue(trustRule({ id: 9 }))
  const revokeMany = vi
    .spyOn(trustApi, 'revokeManyTrust')
    .mockResolvedValue({ done: 2, skipped: 0 })
  const trustMany = vi
    .spyOn(trustApi, 'trustSuggestions')
    .mockResolvedValue({ done: 2, skipped: 0 })
  const mounted = await mountWithPlugins(TrustView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const rows = () => mounted.wrapper.findAll('[data-test="trust-row"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLButtonElement>(`[data-test="${selector}"]`)
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  const adding = () => mounted.wrapper.findComponent(TrustDialog).props('modelValue')
  return {
    ...mounted,
    fetchIt,
    ideas,
    revoke,
    post,
    revokeMany,
    trustMany,
    find,
    text,
    rows,
    inDialog,
    confirming,
    adding,
  }
}

describe('TrustView', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(trustApi, 'fetchTrust').mockReturnValue(new Promise(() => {}))
      vi.spyOn(trustApi, 'fetchSuggestions').mockResolvedValue([])
      const { wrapper } = await mountWithPlugins(TrustView, { signedIn: 'admin' })

      expect(wrapper.find('[data-test="trust-loading"]').exists()).toBe(true)
    })

    it('says in a banner what trust is and that it holds for every program', async () => {
      const { text } = await open()

      expect(text('trust-info')).toContain('every signal that matches it')
      expect(text('trust-info')).toContain('OPNsense, Wazuh, ntopng and CrowdSec')
    })

    it('shows how many are trusted, how much, and what they have kept quiet', async () => {
      const { text } = await open()

      expect(text('trust-tiles')).toContain('Trusted')
      expect(text('trust-tiles')).toContain('2')
      expect(text('trust-tiles')).toContain('Kept quiet')
    })

    it('lists each decision', async () => {
      const { rows } = await open()

      expect(rows()).toHaveLength(2)
      expect(rows()[0]?.find('[data-test="trust-about"]').text()).toBe(
        'What 192.168.1.30 sends to 52.0.0.0/8',
      )
      expect(rows()[1]?.find('[data-test="trust-level"]').text()).toBe('Low priority')
    })

    it('says nothing is trusted yet, and where to look for what to trust', async () => {
      const { find } = await open(trustList({ items: [], safe: 0, low_priority: 0, applied: 0 }))

      expect(find('no-trust').text()).toContain("You haven't trusted anything yet")
      expect(find('see-incidents').attributes('href')).toBe('/incidents')
      expect(find('trust-list').exists()).toBe(false)
      expect(find('trust-search').exists()).toBe(false)
    })

    it('says so when it cannot be loaded, and loads once it can', async () => {
      const { find, fetchIt, rows } = await open(offline())
      expect(find('trust-error').exists()).toBe(true)

      fetchIt.mockResolvedValue(trustList())
      await find('trust-error').find('button').trigger('click')
      await flushPromises()

      expect(rows()).toHaveLength(2)
    })

    it('asks again by the button', async () => {
      const { find, fetchIt, rows } = await open()
      fetchIt.mockResolvedValue(trustList({ items: [trustRule({ id: 5 })] }))

      await find('refresh-trust').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(rows()).toHaveLength(1)
    })
  })

  describe('searching', () => {
    it('shows what matches the words, in what it says, its note or its level', async () => {
      const { find, rows } = await open()

      await find('trust-search').find('input').setValue('camera')
      expect(rows()).toHaveLength(1)

      await find('trust-search').find('input').setValue('low priority')
      expect(rows()).toHaveLength(1)
      expect(rows()[0]?.find('[data-test="trust-about"]').text()).toContain('52.1.2.3')
    })

    it('says nothing matches, and shows all again when it is cleared', async () => {
      const { find, rows } = await open()

      await find('trust-search').find('input').setValue('zzz')
      expect(find('trust-none-found').exists()).toBe(true)
      expect(rows()).toHaveLength(0)

      await find('trust-search').find('input').setValue('')
      expect(rows()).toHaveLength(2)
    })

    it('does not offer a search for a single decision', async () => {
      const { find } = await open(trustList({ items: [trustRule()] }))

      expect(find('trust-search').exists()).toBe(false)
    })
  })

  describe('the AI suggestions', () => {
    it('offers what the AI is sure is nothing, with its reason', async () => {
      const { find, text } = await open(trustList(), [suggestion()])

      expect(find('suggestions-card').exists()).toBe(true)
      expect(text('suggestion')).toContain('A vendor’s own scanner')
      expect(text('suggestion')).toContain('93.184.216.34, 90% sure it is safe.')
      expect(text('suggestion')).toContain('It scans on a schedule.')
    })

    it('says low priority for a suggestion that is only that, and copes with no reason', async () => {
      const { text } = await open(trustList(), [
        suggestion({ verdict: 'low_priority', reason: null }),
      ])

      expect(text('suggestion')).toContain('sure it is low priority.')
    })

    it('leaves the card out when there is nothing to suggest', async () => {
      const { find } = await open()

      expect(find('suggestions-card').exists()).toBe(false)
    })

    it('stands without them when they cannot be read', async () => {
      const { find, rows } = await open(trustList(), offline())

      expect(find('suggestions-card').exists()).toBe(false)
      expect(rows()).toHaveLength(2)
    })

    it('lets the owner look first', async () => {
      const { find } = await open(trustList(), [suggestion({ incident_id: 9 })])

      expect(find('suggestion-open').attributes('href')).toBe('/incidents/9')
    })

    it('trusts the address once the owner says so, and says it, using the reason as the note', async () => {
      const { find, post, fetchIt, text } = await open(trustList(), [suggestion()])

      await find('suggestion-trust').trigger('click')
      await flushPromises()
      await flushPromises()

      expect(post).toHaveBeenCalledWith(
        { address: '93.184.216.34', verdict: 'not_suspicious', note: 'It scans on a schedule.' },
        'a-security-token',
      )
      expect(text('trust-notice')).toBe('Trusted everything about 93.184.216.34.')
      expect(fetchIt).toHaveBeenCalledTimes(2)
    })

    it('uses the headline as the note where there is no reason', async () => {
      const { find, post } = await open(trustList(), [suggestion({ reason: null })])

      await find('suggestion-trust').trigger('click')
      await flushPromises()

      expect(post).toHaveBeenCalledWith(
        expect.objectContaining({ note: 'A vendor’s own scanner' }),
        'a-security-token',
      )
    })

    it('says why it could not be trusted', async () => {
      const { find, post, text } = await open(trustList(), [suggestion()])
      post.mockRejectedValue(offline())

      await find('suggestion-trust').trigger('click')
      await flushPromises()

      expect(text('trust-failure')).toContain("Can't reach AresGate.")
    })
  })

  describe('trusting something that is not on the screen', () => {
    it('opens the form, and says what was trusted once it is saved', async () => {
      const { find, adding, inDialog, text, fetchIt } = await open()

      await find('add-trust').trigger('click')
      await flushPromises()
      expect(adding()).toBe(true)

      const field = inDialog('field-address')!.querySelector('input')!
      field.value = '52.1.2.3'
      field.dispatchEvent(new Event('input'))
      await flushPromises()
      inDialog('trust-save')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('trust-notice')).toBe('Trusted: Everything about 52.1.2.3.')
      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(adding()).toBe(false)
    })
  })

  describe('taking one back', () => {
    const choose = async (wrapper: Awaited<ReturnType<typeof open>>['wrapper'], index: number) => {
      await wrapper.findAll('[data-test="trust-revoke"]')[index]?.trigger('click')
      await flushPromises()
    }

    it('asks first, saying what it was about and how many alerts are judged again', async () => {
      const { wrapper, confirming, inDialog } = await open(
        trustList({ items: [trustRule({ hits: 12 })] }),
      )

      await choose(wrapper, 0)

      expect(confirming()).toBe(true)
      expect(inDialog('confirm-message')?.textContent).toContain('Everything about 52.1.2.3')
      expect(inDialog('confirm-message')?.textContent).toContain(
        '12 alerts it kept quiet are judged again',
      )
    })

    it('says alert, not alerts, for one', async () => {
      const { wrapper, inDialog } = await open(trustList({ items: [trustRule({ hits: 1 })] }))

      await choose(wrapper, 0)

      expect(inDialog('confirm-message')?.textContent).toContain(
        '1 alert it kept quiet is judged again',
      )
    })

    it('says it has not been applied to anything, when it has not', async () => {
      const { wrapper, inDialog } = await open(trustList({ items: [trustRule({ hits: 0 })] }))

      await choose(wrapper, 0)

      expect(inDialog('confirm-message')?.textContent).toContain(
        'It has not been applied to an alert yet.',
      )
    })

    it('takes it back once confirmed, and says so', async () => {
      const { wrapper, revoke, fetchIt, inDialog, text, confirming } = await open()
      fetchIt.mockResolvedValue(trustList({ items: [trustRule({ id: 1 })] }))
      await choose(wrapper, 0)

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(revoke).toHaveBeenCalledWith(2, 'a-security-token')
      expect(text('trust-notice')).toBe('Taken back: What 192.168.1.30 sends to 52.0.0.0/8.')
      expect(wrapper.findAll('[data-test="trust-row"]')).toHaveLength(1)
      expect(confirming()).toBe(false)
    })

    it('does nothing if the question is cancelled', async () => {
      const { wrapper, revoke, inDialog, rows, confirming } = await open()
      await choose(wrapper, 0)

      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(revoke).not.toHaveBeenCalled()
      expect(rows()).toHaveLength(2)
      expect(confirming()).toBe(false)
    })

    it('says why it could not be taken back, and keeps it listed', async () => {
      const { wrapper, revoke, inDialog, rows, text } = await open()
      revoke.mockRejectedValue(offline())
      await choose(wrapper, 0)

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('trust-failure')).toContain("Can't reach AresGate.")
      expect(rows()).toHaveLength(2)
    })

    it('forgets the last answer when another is asked for', async () => {
      const { wrapper, revoke, inDialog, find } = await open()
      revoke.mockRejectedValueOnce(offline())
      await choose(wrapper, 0)
      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()
      expect(find('trust-failure').exists()).toBe(true)

      await choose(wrapper, 1)

      expect(find('trust-failure').exists()).toBe(false)
    })
  })

  describe('taking many back', () => {
    const pick = async (wrapper: Awaited<ReturnType<typeof open>>['wrapper'], ...at: number[]) => {
      const rows = wrapper.findAll('[data-test="trust-row"]')
      for (const index of at) await rows[index]?.find('[data-test="row-select"]').trigger('click')
    }

    it('offers no picking for a single decision', async () => {
      const { find, rows } = await open(trustList({ items: [trustRule()] }))

      expect(find('select-bar').exists()).toBe(false)
      expect(rows()[0]?.find('[data-test="row-select"]').exists()).toBe(false)
    })

    it('says what picking is for, and has the actions once something is picked', async () => {
      const { wrapper, find, text } = await open()
      expect(text('select-hint')).toBe('Select decisions to change them together')
      expect(find('trust-take-back-many').exists()).toBe(false)

      await pick(wrapper, 0)

      expect(text('select-count')).toBe('1 decision selected')
      expect(find('trust-take-back-many').exists()).toBe(true)
    })

    it('picks every decision with the box above them, and lets them all go', async () => {
      const { wrapper, find, text } = await open()

      await find('select-all').trigger('change')
      expect(text('select-count')).toBe('2 decisions selected')
      expect(
        wrapper
          .findAll('[data-test="trust-row"]')
          .every((row) => row.classes('trust-row--selected')),
      ).toBe(true)

      await find('select-clear').trigger('click')
      expect(text('select-hint')).toContain('Select decisions')
    })

    it('forgets a decision that the search leaves out', async () => {
      const { wrapper, find, text } = await open()
      await pick(wrapper, 0, 1)

      await find('trust-search').find('input').setValue('camera')

      expect(text('select-count')).toBe('1 decision selected')
    })

    it('asks first, then takes back what is picked, and says how many', async () => {
      const { wrapper, find, revokeMany, fetchIt, inDialog, text } = await open()
      await pick(wrapper, 0, 1)

      await find('trust-take-back-many').trigger('click')
      expect(inDialog('confirm-title')!.textContent).toBe('Take back 2 decisions?')
      fetchIt.mockResolvedValue(trustList({ items: [] }))
      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(revokeMany).toHaveBeenCalledWith([2, 1], 'a-security-token')
      expect(text('trust-notice')).toBe('Taken back: 2 decisions.')
      expect(find('no-trust').exists()).toBe(true)
    })

    it('says one decision in the singular, and what had gone already', async () => {
      const { wrapper, find, revokeMany, inDialog, text } = await open()
      revokeMany.mockResolvedValue({ done: 1, skipped: 1 })
      await pick(wrapper, 0)

      await find('trust-take-back-many').trigger('click')
      expect(inDialog('confirm-title')!.textContent).toBe('Take back 1 decision?')
      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('trust-notice')).toBe('Taken back: 1 decision. 1 decision had already gone.')
    })

    it('does nothing when the question is cancelled', async () => {
      const { wrapper, find, revokeMany, inDialog, text } = await open()
      await pick(wrapper, 0, 1)

      await find('trust-take-back-many').trigger('click')
      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(revokeMany).not.toHaveBeenCalled()
      expect(text('select-count')).toBe('2 decisions selected')
    })

    it('says why it could not, and keeps what was picked', async () => {
      const { wrapper, find, revokeMany, inDialog, text } = await open()
      revokeMany.mockRejectedValue(offline())
      await pick(wrapper, 0, 1)

      await find('trust-take-back-many').trigger('click')
      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('trust-failure')).toContain("Can't reach AresGate.")
      expect(text('select-count')).toBe('2 decisions selected')
    })
  })

  describe('trusting many suggestions', () => {
    const two = [
      suggestion({ incident_id: 9 }),
      suggestion({ incident_id: 11, subject: '52.1.2.9' }),
    ]

    const pickBoth = async (find: Awaited<ReturnType<typeof open>>['find']) => {
      await find('suggestions-card').find('[data-test="select-all"]').trigger('change')
    }

    it('offers no picking for a single suggestion', async () => {
      const { find } = await open(trustList(), [suggestion()])

      expect(find('suggestions-card').find('[data-test="select-bar"]').exists()).toBe(false)
      expect(find('suggestions-card').find('[data-test="row-select"]').exists()).toBe(false)
    })

    it('trusts what is picked as the AI read each', async () => {
      const { find, trustMany, fetchIt, text } = await open(trustList(), two)
      await pickBoth(find)

      await find('suggestions-trust-many').trigger('click')
      await flushPromises()
      await flushPromises()

      expect(trustMany).toHaveBeenCalledWith([9, 11], 'a-security-token', undefined)
      expect(text('trust-notice')).toBe('Trusted: 2 decisions.')
      expect(fetchIt).toHaveBeenCalledTimes(2)
    })

    it('trusts one picked suggestion as low priority, and says what was no longer suggested', async () => {
      const { wrapper, find, trustMany, text } = await open(trustList(), two)
      trustMany.mockResolvedValue({ done: 1, skipped: 1 })
      await wrapper.find('[data-test="suggestion"] [data-test="row-select"]').trigger('click')

      await find('suggestions-trust-low').trigger('click')
      await flushPromises()
      await flushPromises()

      expect(trustMany).toHaveBeenCalledWith([9], 'a-security-token', 'low_priority')
      expect(text('trust-notice')).toBe('Trusted: 1 decision. 1 no longer suggested.')
    })

    it('lets them all go', async () => {
      const { find } = await open(trustList(), two)
      await pickBoth(find)

      await find('suggestions-card').find('[data-test="select-clear"]').trigger('click')

      expect(find('suggestions-card').find('[data-test="select-hint"]').exists()).toBe(true)
    })

    it('says why it could not, and keeps what was picked', async () => {
      const { find, trustMany, text } = await open(trustList(), two)
      trustMany.mockRejectedValue(offline())
      await pickBoth(find)

      await find('suggestions-trust-many').trigger('click')
      await flushPromises()

      expect(text('trust-failure')).toContain("Can't reach AresGate.")
      expect(find('suggestions-card').find('[data-test="select-count"]').text()).toBe(
        '2 suggestions selected',
      )
    })
  })
})
