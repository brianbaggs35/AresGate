import * as alertsApi from '@/api/alerts'
import { ApiError } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DestinationDialog from '@/components/DestinationDialog.vue'
import { destination, destinations, failing, working } from '@/test/alerts'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AlertsView from '@/views/AlertsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(answer: alertsApi.Destinations | Error = destinations([destination()])) {
  const fetchIt = vi.spyOn(alertsApi, 'fetchDestinations')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const add = vi.spyOn(alertsApi, 'addDestination')
  const change = vi.spyOn(alertsApi, 'changeDestination')
  const remove = vi.spyOn(alertsApi, 'removeDestination').mockResolvedValue(undefined)
  const test = vi.spyOn(alertsApi, 'testDestination')
  const mounted = await mountWithPlugins(AlertsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const cards = () => mounted.wrapper.findAll('[data-test="destination"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const editing = () => mounted.wrapper.findComponent(DestinationDialog).props('modelValue')
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  const press = async (card: number, name: string) => {
    await cards()[card]?.find(`[data-test="destination-${name}"]`).trigger('click')
    await flushPromises()
  }
  const write = async (field: 'dialog-name' | 'dialog-url', value: string) => {
    const input = inDialog(field)!.querySelector('input')!
    input.value = value
    input.dispatchEvent(new Event('input'))
    await flushPromises()
  }
  const save = async () => {
    inDialog('dialog-save')!.click()
    await flushPromises()
  }
  return {
    ...mounted,
    fetchIt,
    add,
    change,
    remove,
    test,
    find,
    text,
    cards,
    inDialog,
    editing,
    confirming,
    press,
    write,
    save,
  }
}

const ADDRESS = 'https://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnopqrstuvwxyz'

describe('AlertsView', () => {
  describe('looking at them', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(alertsApi, 'fetchDestinations').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(AlertsView, { signedIn: 'admin' })

      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
    })

    it('lists each destination', async () => {
      const { cards, text } = await open(
        destinations([destination(), working({ id: 2, name: 'Phone' })]),
      )

      expect(cards()).toHaveLength(2)
      expect(cards()[1]?.find('[data-test="destination-name"]').text()).toBe('Phone')
      expect(text('page-heading')).toBe('Alerts')
    })

    it('says none are set up, and offers to add one', async () => {
      const { text, find, editing } = await open(destinations([]))

      expect(text('no-destinations')).toContain('No alerts are set up')
      expect(find('destination-list').exists()).toBe(false)
      await find('empty-add').trigger('click')
      await flushPromises()
      expect(editing()).toBe(true)
    })

    it('says why it could not load, and tries again', async () => {
      const { text, find, fetchIt } = await open(offline())

      expect(text('alerts-error')).toContain("Can't reach AresGate.")
      fetchIt.mockResolvedValue(destinations([destination()]))
      await find('alerts-retry').trigger('click')
      await flushPromises()
      expect(find('destination-list').exists()).toBe(true)
    })

    it('stops offering to add one at the most it keeps', async () => {
      const { find, text } = await open(destinations([destination()], { max_destinations: 1 }))

      expect(find('destination-add').attributes('disabled')).toBeDefined()
      expect(text('alerts-full')).toContain('You have 1 destinations')
    })
  })

  describe('adding one', () => {
    it('keeps it and suggests a test', async () => {
      const { add, find, text, cards, write, save, editing } = await open(destinations([]))
      add.mockResolvedValue(destination({ id: 7, name: 'Security' }))

      await find('destination-add').trigger('click')
      await flushPromises()
      await write('dialog-name', 'Security')
      await write('dialog-url', ADDRESS)
      await save()

      expect(add).toHaveBeenCalledWith({ name: 'Security', url: ADDRESS }, 'a-security-token')
      expect(editing()).toBe(false)
      expect(cards()).toHaveLength(1)
      expect(text('alerts-notice')).toBe(
        'Added Security. Send a test message to check it reaches the channel.',
      )
    })

    it('adds nothing when the dialog is closed again', async () => {
      const { add, find, inDialog, editing, cards } = await open(destinations([]))

      await find('destination-add').trigger('click')
      await flushPromises()
      expect(editing()).toBe(true)
      inDialog('dialog-cancel')!.click()
      await flushPromises()

      expect(editing()).toBe(false)
      expect(add).not.toHaveBeenCalled()
      expect(cards()).toHaveLength(0)
    })

    it('shows what was wrong with a field and stays open', async () => {
      const { add, find, inDialog, editing, write, save } = await open(destinations([]))
      add.mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['url'], message: "That isn't a Discord address." },
        ]),
      )

      await find('destination-add').trigger('click')
      await flushPromises()
      await write('dialog-name', 'Security')
      await write('dialog-url', 'https://example.com')
      await save()

      expect(editing()).toBe(true)
      expect(inDialog('dialog-url')!.textContent).toContain("That isn't a Discord address.")
    })

    it('shows a failure that is not about a field in the dialog', async () => {
      const { add, find, inDialog, write, save } = await open(destinations([]))
      add.mockRejectedValue(offline())

      await find('destination-add').trigger('click')
      await flushPromises()
      await write('dialog-name', 'Security')
      await write('dialog-url', ADDRESS)
      await save()

      expect(inDialog('dialog-failure')!.textContent).toContain("Can't reach AresGate.")
    })
  })

  describe('changing one', () => {
    it('renames it and replaces its address', async () => {
      const { change, press, write, save, cards, text } = await open()
      change.mockResolvedValue(destination({ name: 'Phone' }))

      await press(0, 'edit')
      await write('dialog-name', 'Phone')
      await write('dialog-url', ADDRESS)
      await save()

      expect(change).toHaveBeenCalledWith(1, { name: 'Phone', url: ADDRESS }, 'a-security-token')
      expect(cards()[0]?.find('[data-test="destination-name"]').text()).toBe('Phone')
      expect(text('alerts-notice')).toBe('Saved Phone.')
    })

    it('keeps the address when none is typed', async () => {
      const { change, press, save } = await open()
      change.mockResolvedValue(destination())

      await press(0, 'edit')
      await save()

      expect(change).toHaveBeenCalledWith(1, { name: 'Security channel' }, 'a-security-token')
    })

    it('turns it off and on again', async () => {
      const { change, cards, text } = await open()
      change.mockResolvedValueOnce(destination({ enabled: false }))
      const toggle = () => cards()[0]!.find('[data-test="destination-enabled"] input')

      await toggle().setValue(false)
      await flushPromises()
      expect(change).toHaveBeenLastCalledWith(1, { enabled: false }, 'a-security-token')
      expect(text('alerts-notice')).toBe('Security channel will not be sent anything.')

      change.mockResolvedValueOnce(destination({ enabled: true }))
      await toggle().setValue(true)
      await flushPromises()
      expect(text('alerts-notice')).toBe('Security channel will be sent alerts.')
    })

    it('changes only the one that was asked for', async () => {
      const { change, cards } = await open(
        destinations([destination(), destination({ id: 2, name: 'Family' })]),
      )
      change.mockResolvedValueOnce(destination({ id: 2, name: 'Family', enabled: false }))

      await cards()[1]!.find('[data-test="destination-enabled"] input').setValue(false)
      await flushPromises()

      expect(cards()[0]!.text()).toContain('Security channel')
      expect(cards()[1]!.text()).toContain('Family')
      const checked = (card: number) =>
        cards()[card]!.find<HTMLInputElement>('[data-test="destination-enabled"] input').element
          .checked
      expect(checked(0)).toBe(true)
      expect(checked(1)).toBe(false)
    })

    it('says why it could not be turned off', async () => {
      const { change, cards, text } = await open()
      change.mockRejectedValue(offline())

      await cards()[0]!.find('[data-test="destination-enabled"] input').setValue(false)
      await flushPromises()

      expect(text('alerts-failure')).toContain("Can't reach AresGate.")
    })
  })

  describe('testing one', () => {
    it('sends a message and says it was sent', async () => {
      const { test, press, text, cards } = await open()
      test.mockResolvedValue({
        ok: true,
        message: 'The test message was sent.',
        destination: working(),
      })

      await press(0, 'test')

      expect(test).toHaveBeenCalledWith(1, 'a-security-token')
      expect(text('alerts-notice')).toBe(
        'Test message sent to Security channel. Look for it in the channel.',
      )
      expect(cards()[0]?.find('[data-test="status"]').text()).toBe('Connected')
    })

    it('shows on the card why it did not get through', async () => {
      const { test, press, cards, find } = await open()
      test.mockResolvedValue({ ok: false, message: 'No.', destination: failing() })

      await press(0, 'test')

      expect(find('alerts-notice').exists()).toBe(false)
      expect(cards()[0]?.find('[data-test="destination-error"]').text()).toContain(
        "Discord doesn't accept this webhook",
      )
      expect(find('alerts-failure').exists()).toBe(false)
    })

    it('says why it could not be sent at all', async () => {
      const { test, press, text } = await open()
      test.mockRejectedValue(offline())

      await press(0, 'test')

      expect(text('alerts-failure')).toContain("Can't reach AresGate.")
    })
  })

  describe('removing one', () => {
    it('asks first, says what happens, and forgets it', async () => {
      const { remove, press, confirming, inDialog, text, cards } = await open(
        destinations([destination(), destination({ id: 2, name: 'Phone' })]),
      )

      await press(0, 'remove')
      expect(confirming()).toBe(true)
      expect(inDialog('confirm-message')!.textContent).toContain('forgets its webhook address')
      inDialog('confirm-accept')!.click()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith(1, 'a-security-token')
      expect(confirming()).toBe(false)
      expect(cards()).toHaveLength(1)
      expect(text('alerts-notice')).toBe('Removed Security channel.')
    })

    it('says why it could not be removed', async () => {
      const { remove, press, inDialog, text, cards } = await open()
      remove.mockRejectedValue(offline())

      await press(0, 'remove')
      inDialog('confirm-accept')!.click()
      await flushPromises()

      expect(text('alerts-failure')).toContain("Can't reach AresGate.")
      expect(cards()).toHaveLength(1)
    })

    it('keeps it when the question is cancelled', async () => {
      const { remove, press, inDialog, confirming } = await open()

      await press(0, 'remove')
      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(confirming()).toBe(false)
      expect(remove).not.toHaveBeenCalled()
    })
  })
})
