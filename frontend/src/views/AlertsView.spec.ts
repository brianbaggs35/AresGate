import * as alertsApi from '@/api/alerts'
import { ApiError } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DestinationDialog from '@/components/DestinationDialog.vue'
import MailServerDialog from '@/components/MailServerDialog.vue'
import RulesDialog from '@/components/RulesDialog.vue'
import {
  deliveries,
  destination,
  destinations,
  emailDestination,
  failing,
  mailServer,
  noMailServer,
  preview,
  rules,
  sample,
  working,
} from '@/test/alerts'
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
  const saveMail = vi.spyOn(alertsApi, 'saveMailServer')
  const removeMail = vi.spyOn(alertsApi, 'removeMailServer').mockResolvedValue(undefined)
  const test = vi.spyOn(alertsApi, 'testDestination')
  const sendIt = vi.spyOn(alertsApi, 'sendSample')
  vi.spyOn(alertsApi, 'fetchSample').mockResolvedValue(sample())
  const changeIt = vi.spyOn(alertsApi, 'changeRules')
  const previewIt = vi.spyOn(alertsApi, 'previewRules').mockResolvedValue(preview())
  const log = vi.spyOn(alertsApi, 'fetchDeliveries').mockResolvedValue(deliveries())
  const mounted = await mountWithPlugins(AlertsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const cards = () => mounted.wrapper.findAll('[data-test="destination"]')
  const inDialog = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const editing = () => mounted.wrapper.findComponent(DestinationDialog).props('modelValue')
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  const ruling = () => mounted.wrapper.findComponent(RulesDialog)
  const press = async (card: number, name: string) => {
    await cards()[card]?.find(`[data-test="destination-${name}"]`).trigger('click')
    await flushPromises()
  }
  const write = async (field: 'dialog-name' | 'dialog-url' | 'dialog-recipient', value: string) => {
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
    saveMail,
    removeMail,
    sendIt,
    test,
    changeIt,
    previewIt,
    log,
    find,
    text,
    cards,
    inDialog,
    editing,
    confirming,
    ruling,
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

    it('shows what was sent below the destinations, once there is one', async () => {
      const { find, log } = await open()

      expect(find('delivery-log').exists()).toBe(true)
      expect(log).toHaveBeenCalledOnce()
    })

    it('says none are set up, and offers to add one', async () => {
      const { text, find, editing, log } = await open(destinations([]))

      expect(find('delivery-log').exists()).toBe(false)
      expect(log).not.toHaveBeenCalled()
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

      expect(add).toHaveBeenCalledWith(
        { kind: 'discord', name: 'Security', url: ADDRESS },
        'a-security-token',
      )
      expect(editing()).toBe(false)
      expect(cards()).toHaveLength(1)
      expect(text('alerts-notice')).toBe(
        'Added Security. Send a test message to check it reaches the channel.',
      )
    })

    it('keeps an email destination and says where to look for the test', async () => {
      const { add, find, text, cards, write, save, inDialog } = await open(destinations([]))
      add.mockResolvedValue(emailDestination({ id: 8 }))

      await find('destination-add').trigger('click')
      await flushPromises()
      inDialog('dialog-kind-email')!.click()
      await flushPromises()
      await write('dialog-name', 'Inbox')
      await write('dialog-recipient', 'me@example.org')
      await save()

      expect(add).toHaveBeenCalledWith(
        { kind: 'email', name: 'Inbox', recipient: 'me@example.org' },
        'a-security-token',
      )
      expect(cards()).toHaveLength(1)
      expect(text('alerts-notice')).toBe(
        'Added Inbox. Send a test message to check it reaches the inbox of me@example.org.',
      )
    })

    it('names the destination when an email one comes back with no address', async () => {
      const { add, find, text, write, save, inDialog } = await open(destinations([]))
      add.mockResolvedValue(emailDestination({ recipient: null }))

      await find('destination-add').trigger('click')
      await flushPromises()
      inDialog('dialog-kind-email')!.click()
      await flushPromises()
      await write('dialog-name', 'Inbox')
      await write('dialog-recipient', 'me@example.org')
      await save()

      expect(text('alerts-notice')).toContain('reaches the inbox of Inbox.')
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

    it('sends a new email address of an email destination, and no webhook', async () => {
      const { change, press, write, save, cards } = await open(
        destinations([emailDestination()], { smtp: mailServer() }),
      )
      change.mockResolvedValue(emailDestination({ recipient: 'you@example.org' }))

      await press(0, 'edit')
      await write('dialog-recipient', 'you@example.org')
      await save()

      expect(change).toHaveBeenCalledWith(
        2,
        { name: 'Inbox', recipient: 'you@example.org' },
        'a-security-token',
      )
      expect(cards()[0]!.text()).toContain('you@example.org')
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

    it('says to look in the inbox for an email destination', async () => {
      const { test, press, text } = await open(destinations([emailDestination()]))
      test.mockResolvedValue({
        ok: true,
        message: 'The test message was sent.',
        destination: working({ id: 2, kind: 'email', name: 'Inbox', recipient: 'me@example.org' }),
      })

      await press(0, 'test')

      expect(text('alerts-notice')).toBe(
        'Test message sent to Inbox. Look for it in the inbox of me@example.org.',
      )
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

  describe('sending a sample alert', () => {
    it('sends one and says it was sent', async () => {
      const { sendIt, press, text, cards } = await open()
      sendIt.mockResolvedValue({
        ok: true,
        message: 'The sample alert was sent.',
        destination: working(),
      })

      await press(0, 'sample')

      expect(sendIt).toHaveBeenCalledWith(1, 'a-security-token')
      expect(text('alerts-notice')).toBe(
        'A sample alert was sent to Security channel. Look for it in the channel.',
      )
      expect(cards()[0]?.find('[data-test="status"]').text()).toBe('Connected')
    })

    it('waits for the answer, with the card’s buttons held', async () => {
      const { sendIt, press, cards } = await open()
      let answer: (value: alertsApi.DestinationTest) => void = () => undefined
      sendIt.mockReturnValue(new Promise((resolve) => (answer = resolve)))

      await press(0, 'sample')

      const card = cards()[0]!
      expect(card.find('[data-test="destination-sample"]').classes()).toContain('v-btn--loading')
      expect(card.find('[data-test="destination-test"]').attributes('disabled')).toBeDefined()
      answer({ ok: true, message: '', destination: working() })
      await flushPromises()
      expect(card.find('[data-test="destination-sample"]').classes()).not.toContain(
        'v-btn--loading',
      )
    })

    it('shows on the card why it did not get through', async () => {
      const { sendIt, press, cards, find } = await open()
      sendIt.mockResolvedValue({ ok: false, message: 'No.', destination: failing() })

      await press(0, 'sample')

      expect(find('alerts-notice').exists()).toBe(false)
      expect(cards()[0]?.find('[data-test="destination-error"]').text()).toContain(
        "Discord doesn't accept this webhook",
      )
    })

    it('says why it could not be sent at all', async () => {
      const { sendIt, press, text } = await open()
      sendIt.mockRejectedValue(offline())

      await press(0, 'sample')

      expect(text('alerts-failure')).toContain("Can't reach AresGate.")
    })
  })

  describe('setting what one is told', () => {
    it('opens the rules of the one that was asked for', async () => {
      const { press, ruling } = await open(
        destinations([destination(), destination({ id: 2, name: 'Phone' })]),
      )

      expect(ruling().exists()).toBe(false)
      await press(1, 'rules-edit')

      expect(ruling().props('modelValue')).toBe(true)
      expect(ruling().props('destination')).toMatchObject({ id: 2, name: 'Phone' })
    })

    it('shows what they would have done the first time they are opened', async () => {
      const { press, previewIt, inDialog } = await open()

      await press(0, 'rules-edit')

      expect(previewIt).toHaveBeenCalledTimes(1)
      expect(previewIt).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ min_severity: 2 }),
        'a-security-token',
      )
      expect(inDialog('preview-summary')!.textContent).toContain('would have sent 2 messages')
    })

    it('keeps them, and says so', async () => {
      const { changeIt, press, ruling, text, cards } = await open()
      const chosen = rules({ max_per_hour: 3 })
      changeIt.mockResolvedValue(destination({ rules: chosen }))

      await press(0, 'rules-edit')
      ruling().vm.$emit('save', chosen)
      await flushPromises()

      expect(changeIt).toHaveBeenCalledWith(1, chosen, 'a-security-token')
      expect(ruling().props('modelValue')).toBe(false)
      expect(text('alerts-notice')).toBe('Saved what Security channel is told.')
      expect(cards()[0]?.find('[data-test="destination-rules"]').text()).toContain('3')
    })

    it('shows what was wrong with a rule and stays open', async () => {
      const { changeIt, press, ruling, find } = await open()
      changeIt.mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['quiet_from'], message: 'Quiet hours need a start.' },
        ]),
      )

      await press(0, 'rules-edit')
      ruling().vm.$emit('save', rules({ max_per_hour: 3 }))
      await flushPromises()

      expect(ruling().props('modelValue')).toBe(true)
      expect(ruling().props('problems')).toEqual({ quiet_from: 'Quiet hours need a start.' })
      expect(find('alerts-notice').exists()).toBe(false)
    })

    it('shows a failure that is not about a rule in the sheet', async () => {
      const { changeIt, press, ruling } = await open()
      changeIt.mockRejectedValue(offline())

      await press(0, 'rules-edit')
      ruling().vm.$emit('save', rules({ max_per_hour: 3 }))
      await flushPromises()

      expect(ruling().props('modelValue')).toBe(true)
      expect(ruling().props('failure')).toBe("Can't reach AresGate.")
    })

    it('forgets an earlier failure when the sheet is opened again', async () => {
      const { changeIt, press, ruling } = await open()
      changeIt.mockRejectedValue(offline())
      await press(0, 'rules-edit')
      ruling().vm.$emit('save', rules({ max_per_hour: 3 }))
      await flushPromises()
      ruling().vm.$emit('update:modelValue', false)
      await flushPromises()

      await press(0, 'rules-edit')

      expect(ruling().props('failure')).toBeNull()
      expect(ruling().props('problems')).toEqual({})
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

    it('says an email destination leaves the mail server as it is', async () => {
      const { press, inDialog } = await open(destinations([emailDestination()]))

      await press(0, 'remove')

      expect(inDialog('confirm-message')!.textContent).toContain(
        'sends nothing more to me@example.org',
      )
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

  describe('the mail server', () => {
    const openMail = async (answer = destinations([], { smtp: noMailServer() })) => {
      const view = await open(answer)
      const field = async (name: string, value: string) => {
        const input = view.inDialog(name)!.querySelector('input')!
        input.value = value
        input.dispatchEvent(new Event('input'))
        await flushPromises()
      }
      const pressMail = async (name: string) => {
        await view.find(name).trigger('click')
        await flushPromises()
      }
      const saveIt = async () => {
        view.inDialog('mail-save')!.click()
        await flushPromises()
      }
      return { ...view, field, pressMail, saveIt }
    }

    it('says none is set up, and offers to set one up', async () => {
      const { find, text } = await openMail()

      expect(text('mail-none')).toContain('No mail server is set up')
      expect(find('mail-edit').text()).toBe('Set up the mail server')
      expect(find('mail-remove').exists()).toBe(false)
    })

    it('shows it once the destinations have loaded, and not before', async () => {
      vi.spyOn(alertsApi, 'fetchDestinations').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(AlertsView, { signedIn: 'admin' })

      expect(wrapper.find('[data-test="mail-section"]').exists()).toBe(false)
    })

    it('saves the settings, loads the destinations again and says so', async () => {
      const view = await openMail()
      const { saveMail, fetchIt, pressMail, field, saveIt, text } = view
      saveMail.mockResolvedValue(mailServer())
      fetchIt.mockResolvedValue(
        destinations([emailDestination()], { smtp: mailServer({ host: 'smtp.example.com' }) }),
      )

      await pressMail('mail-edit')
      await field('mail-host', 'smtp.example.com')
      await field('mail-sender', 'alerts@example.com')
      await saveIt()

      expect(saveMail).toHaveBeenCalledWith(
        {
          host: 'smtp.example.com',
          port: 587,
          security: 'starttls',
          username: null,
          sender: 'alerts@example.com',
        },
        'a-security-token',
      )
      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(text('alerts-notice')).toContain('Saved the mail server.')
      expect(text('mail-name')).toBe('smtp.example.com:587')
      expect(view.wrapper.findComponent(MailServerDialog).props('modelValue')).toBe(false)
    })

    it('shows what was wrong with a field and stays open', async () => {
      const { saveMail, pressMail, field, saveIt, inDialog } = await openMail()
      saveMail.mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['host'], message: "That isn't a server name." },
        ]),
      )

      await pressMail('mail-edit')
      await field('mail-host', 'not a host')
      await field('mail-sender', 'alerts@example.com')
      await saveIt()

      expect(inDialog('mail-host')!.textContent).toContain("That isn't a server name.")
    })

    it('shows a failure that is not about a field in the dialog', async () => {
      const { saveMail, pressMail, field, saveIt, inDialog } = await openMail()
      saveMail.mockRejectedValue(offline())

      await pressMail('mail-edit')
      await field('mail-host', 'smtp.example.com')
      await field('mail-sender', 'alerts@example.com')
      await saveIt()

      expect(inDialog('mail-failure')!.textContent).toContain("Can't reach AresGate.")
    })

    it('forgets an earlier failure when it is opened again', async () => {
      const { saveMail, pressMail, field, saveIt, inDialog } = await openMail()
      saveMail.mockRejectedValue(offline())
      await pressMail('mail-edit')
      await field('mail-host', 'smtp.example.com')
      await field('mail-sender', 'alerts@example.com')
      await saveIt()
      inDialog('mail-cancel')!.click()
      await flushPromises()

      await pressMail('mail-edit')

      expect(inDialog('mail-failure')).toBeNull()
    })

    it('asks before removing it, and loads the destinations again', async () => {
      const { removeMail, fetchIt, pressMail, inDialog, text } = await openMail(
        destinations([emailDestination()], { smtp: mailServer() }),
      )

      await pressMail('mail-remove')
      expect(inDialog('confirm-message')!.textContent).toContain('forgets the mail server')
      fetchIt.mockResolvedValue(destinations([emailDestination({ status: 'not_connected' })]))
      inDialog('confirm-accept')!.click()
      await flushPromises()

      expect(removeMail).toHaveBeenCalledWith('a-security-token')
      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(text('alerts-notice')).toContain('Removed the mail server.')
      expect(text('mail-none')).toContain('No mail server is set up')
    })

    it('keeps it when the question is cancelled', async () => {
      const { removeMail, pressMail, inDialog, text } = await openMail(
        destinations([], { smtp: mailServer() }),
      )

      await pressMail('mail-remove')
      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(removeMail).not.toHaveBeenCalled()
      expect(text('mail-name')).toBe('smtp.example.com:587')
    })

    it('says why it could not be removed', async () => {
      const { removeMail, pressMail, inDialog, text } = await openMail(
        destinations([], { smtp: mailServer() }),
      )
      removeMail.mockRejectedValue(offline())

      await pressMail('mail-remove')
      inDialog('confirm-accept')!.click()
      await flushPromises()

      expect(text('alerts-failure')).toContain("Can't reach AresGate.")
    })

    it('tells the destination dialog whether the mail server is set up', async () => {
      const { find, inDialog } = await openMail(destinations([], { smtp: mailServer() }))

      await find('destination-add').trigger('click')
      await flushPromises()
      inDialog('dialog-kind-email')!.click()
      await flushPromises()

      expect(inDialog('dialog-mail-not-ready')).toBeNull()
    })
  })
})
