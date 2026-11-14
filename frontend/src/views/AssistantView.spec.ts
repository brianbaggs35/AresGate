import type { VueWrapper } from '@vue/test-utils'
import { VBottomSheet } from 'vuetify/components'

import * as aiApi from '@/api/ai'
import * as chatApi from '@/api/aiChat'
import { ApiError } from '@/api/client'
import AiCallDialog from '@/components/AiCallDialog.vue'
import { STARTERS } from '@/chat'
import { ai as aiSettings } from '@/test/ai'
import { answer, conversation, question, summary } from '@/test/aiChat'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AssistantView from '@/views/AssistantView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const missing = () => new ApiError(404, 'There is no such conversation.', 'not_found')

/** A wide screen, so the list of conversations is beside the chat. */
const WIDE = 1280

interface Setup {
  route?: string
  width?: number
  conversations?: chatApi.ConversationSummary[] | Error
  opened?: chatApi.Conversation | Error
  ai?: { enabled: boolean; provider: string | null } | Error
}

async function open(setup: Setup = {}) {
  const list = vi.spyOn(chatApi, 'fetchConversations')
  const one = vi.spyOn(chatApi, 'fetchConversation')
  const conversations = setup.conversations ?? [summary()]
  if (conversations instanceof Error) list.mockRejectedValue(conversations)
  else list.mockResolvedValue(conversations)
  const opened = setup.opened ?? conversation()
  if (opened instanceof Error) one.mockRejectedValue(opened)
  else one.mockResolvedValue(opened)
  const ai = setup.ai ?? { enabled: true, provider: 'anthropic' }
  const fetchAi = vi.spyOn(aiApi, 'fetchAi')
  if (ai instanceof Error) fetchAi.mockRejectedValue(ai)
  else fetchAi.mockResolvedValue(aiSettings(ai))
  vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
  const mounted = await mountWithPlugins(AssistantView, {
    signedIn: 'admin',
    withApp: true,
    width: setup.width ?? WIDE,
    route: setup.route ?? '/assistant/5',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, list, one, find, text }
}

async function type(wrapper: VueWrapper, words: string) {
  await wrapper.find('[data-test="chat-input"] textarea').setValue(words)
}

describe('AssistantView', () => {
  describe('a conversation', () => {
    it('shows what was said, with the answer saying what it is based on', async () => {
      const { wrapper, one, find } = await open()

      expect(one).toHaveBeenCalledWith(5)
      const thread = find('chat-thread')
      expect(thread.attributes('role')).toBe('log')
      expect(wrapper.findAll('[data-test="message-owner"]')).toHaveLength(1)
      expect(thread.text()).toContain('What needs my attention right now?')
      expect(thread.text()).toContain('Start with incident 3')
      expect(find('message-cite').attributes('href')).toBe('/incidents/3')
      expect(find('chat-empty').exists()).toBe(false)
    })

    it('lists the conversations beside it, with the open one marked', async () => {
      const { wrapper } = await open({
        conversations: [summary({ id: 5 }), summary({ id: 6, title: 'Another' })],
      })

      const links = wrapper.findAll('[data-test="conversation-link"]')
      expect(links).toHaveLength(2)
      expect(links[0]?.attributes('aria-current')).toBe('page')
      expect(links[1]?.attributes('aria-current')).toBeUndefined()
      expect(wrapper.find('[data-test="conversations-open"]').exists()).toBe(false)
    })

    it('opens another when one is chosen', async () => {
      const { wrapper, one, router } = await open({
        conversations: [summary({ id: 5 }), summary({ id: 6, title: 'Another' })],
      })
      one.mockResolvedValue(
        conversation({ id: 6, title: 'Another', messages: [question({ text: 'Another one' })] }),
      )

      await router.push('/assistant/6')
      await flushPromises()

      expect(one).toHaveBeenLastCalledWith(6)
      expect(wrapper.find('[data-test="chat-thread"]').text()).toContain('Another one')
    })

    it('says when it is not there, and offers no retry', async () => {
      const { find, text } = await open({ opened: missing() })

      expect(text('chat-error')).toContain('There is no such conversation.')
      expect(find('retry').exists()).toBe(false)
      expect(find('chat-form').exists()).toBe(false)
    })

    it('says when it could not be had, and asks again', async () => {
      const { find, text, one } = await open({ opened: offline() })
      expect(text('chat-error')).toContain("Can't reach AresGate.")
      one.mockResolvedValue(conversation())

      await find('retry').trigger('click')
      await flushPromises()

      expect(find('chat-error').exists()).toBe(false)
      expect(find('chat-thread').exists()).toBe(true)
    })

    it('says when the list could not be had', async () => {
      const { text } = await open({ conversations: offline() })

      expect(text('chat-error')).toContain("Can't reach AresGate.")
    })

    it('drops the answer to a conversation that was left before it came', async () => {
      const { wrapper, one, router } = await open({
        conversations: [summary({ id: 5 }), summary({ id: 6 })],
      })
      let late: (found: chatApi.Conversation) => void = () => undefined
      one.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            late = resolve
          }),
      )
      await router.push('/assistant/6')
      await router.push('/assistant')
      await flushPromises()

      late(conversation({ id: 6, messages: [question({ text: 'Too late' })] }))
      await flushPromises()

      expect(wrapper.find('[data-test="chat-thread"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="chat-empty"]').exists()).toBe(true)
    })
  })

  describe('what is on screen when answers come late', () => {
    it('drops the failure of a conversation that was left before it came', async () => {
      const { wrapper, one, router } = await open({
        conversations: [summary({ id: 5 }), summary({ id: 6 })],
      })
      let late: (error: Error) => void = () => undefined
      one.mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            late = reject
          }),
      )
      await router.push('/assistant/6')
      await router.push('/assistant')
      await flushPromises()

      late(offline())
      await flushPromises()

      expect(wrapper.find('[data-test="chat-error"]').exists()).toBe(false)
    })

    it('scrolls smoothly to the answer for everyone else', async () => {
      const { wrapper } = await open({ route: '/assistant', conversations: [] })
      vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList)
      const jump = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
      vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
      await type(wrapper, 'Anything?')

      await wrapper.find('[data-test="chat-form"]').trigger('submit')
      await flushPromises()

      expect(jump).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }))
    })

    it('scrolls without animation for someone who asked for less movement', async () => {
      const { wrapper } = await open({ route: '/assistant', conversations: [] })
      const calm = vi
        .spyOn(window, 'matchMedia')
        .mockReturnValue({ matches: true } as MediaQueryList)
      const jump = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
      vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
      await type(wrapper, 'Anything?')

      await wrapper.find('[data-test="chat-form"]').trigger('submit')
      await flushPromises()

      expect(calm).toHaveBeenCalledWith('(prefers-reduced-motion: reduce)')
      expect(jump).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'auto' }))
    })
  })

  describe('a new conversation', () => {
    it('starts with things to try, and puts the one picked in the box', async () => {
      const { wrapper, find } = await open({ route: '/assistant', conversations: [] })

      expect(find('chat-empty').exists()).toBe(true)
      const starters = wrapper.findAll('[data-test="chat-starter"]')
      expect(starters.map((button) => button.text())).toEqual([...STARTERS])

      await starters[1]?.trigger('click')

      const box = wrapper.find('[data-test="chat-input"] textarea').element as HTMLTextAreaElement
      expect(box.value).toBe(STARTERS[1])
    })

    it('starts with the question a button on another page asked', async () => {
      const { wrapper } = await open({ route: '/assistant?about=incident:9' })

      const box = wrapper.find('[data-test="chat-input"] textarea').element as HTMLTextAreaElement
      expect(box.value).toBe('What should I know about incident 9, and what should I do about it?')
    })

    it('starts with nothing in the box for a question it does not understand', async () => {
      const { wrapper } = await open({ route: '/assistant?about=whatever' })

      const box = wrapper.find('[data-test="chat-input"] textarea').element as HTMLTextAreaElement
      expect(box.value).toBe('')
    })

    it('says there is nothing to answer when AI is off', async () => {
      const { find } = await open({
        route: '/assistant',
        ai: { enabled: false, provider: null },
      })

      expect(find('chat-off').text()).toContain('AI is off')
      expect(find('chat-off-settings').attributes('href')).toBe('/settings/ai')
    })

    it('says so when no provider is chosen even though AI is on', async () => {
      const { find } = await open({ route: '/assistant', ai: { enabled: true, provider: null } })

      expect(find('chat-off').exists()).toBe(true)
    })

    it('says nothing about it when it cannot find out', async () => {
      const { find } = await open({ route: '/assistant', ai: offline() })

      expect(find('chat-off').exists()).toBe(false)
    })

    it('does not warn when AI is ready', async () => {
      const { find } = await open({ route: '/assistant' })

      expect(find('chat-off').exists()).toBe(false)
    })
  })

  describe('asking', () => {
    it('sends a question, shows it at once and then the answer, and moves to the conversation', async () => {
      const { wrapper, find, router } = await open({ route: '/assistant', conversations: [] })
      let finish: (found: chatApi.Conversation) => void = () => undefined
      const start = vi.spyOn(chatApi, 'askAndFollow').mockImplementation(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }),
      )
      await type(wrapper, '  What needs me?  ')

      await find('chat-form').trigger('submit')
      await flushPromises()

      expect(start).toHaveBeenCalledWith(
        null,
        'What needs me?',
        'a-security-token',
        null,
        expect.any(Function),
      )
      expect(find('chat-pending').text()).toBe('What needs me?')
      expect(find('chat-writing').exists()).toBe(true)
      expect(find('chat-empty').exists()).toBe(false)
      const sendButton = find('chat-send').element as HTMLButtonElement
      expect(sendButton.disabled).toBe(true)

      finish(conversation())
      await flushPromises()

      expect(find('chat-pending').exists()).toBe(false)
      expect(find('chat-writing').exists()).toBe(false)
      await vi.waitFor(() => {
        expect(router.currentRoute.value.fullPath).toBe('/assistant/5')
      })
      expect(find('chat-thread').text()).toContain('Start with incident 3')
      const box = wrapper.find('[data-test="chat-input"] textarea').element as HTMLTextAreaElement
      expect(box.value).toBe('')
    })

    it('shows what the answer has looked at and written as it comes, and then the answer', async () => {
      const { wrapper, find } = await open({ route: '/assistant', conversations: [] })
      let finish: (found: chatApi.Conversation) => void = () => undefined
      let follow: (event: chatApi.AnswerEvent) => void = () => undefined
      vi.spyOn(chatApi, 'askAndFollow').mockImplementation((_id, _text, _token, _page, onEvent) => {
        follow = onEvent
        return new Promise((resolve) => {
          finish = resolve
        })
      })
      await type(wrapper, 'What needs me?')
      await find('chat-form').trigger('submit')
      await flushPromises()
      expect(find('chat-writing').text()).toContain('Looking into it')

      follow({ kind: 'looked', lookup: { tool: 'open_incidents', summary: '2 open incidents' } })
      follow({ kind: 'wrote', text: 'Start with ' })
      await flushPromises()
      expect(find('chat-writing').text()).toContain('2 open incidents')
      expect(find('chat-writing').text()).toContain('Start with')
      expect(find('chat-writing').text()).not.toContain('Looking into it')

      follow({ kind: 'wrote', text: 'incident 3.' })
      await flushPromises()
      expect(find('chat-writing').text()).toContain('Start with incident 3.')

      finish(conversation())
      await flushPromises()
      expect(find('chat-writing').exists()).toBe(false)
      expect(find('chat-thread').text()).toContain('Start with incident 3')
    })

    it('asks the list again so the new conversation is in it', async () => {
      const { wrapper, find, list } = await open({ route: '/assistant', conversations: [] })
      vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
      list.mockResolvedValue([summary()])
      await type(wrapper, 'Anything?')

      await find('chat-form').trigger('submit')
      await flushPromises()

      expect(wrapper.findAll('[data-test="conversation"]')).toHaveLength(1)
    })

    it('asks in the conversation that is open', async () => {
      const { wrapper, find, router } = await open()
      const more = conversation({
        messages: [
          ...conversation().messages,
          question({ id: 3, text: 'And now?' }),
          answer({ id: 4 }),
        ],
      })
      const ask = vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(more)
      await type(wrapper, 'And now?')

      await find('chat-form').trigger('submit')
      await flushPromises()

      expect(ask).toHaveBeenCalledWith(
        5,
        'And now?',
        'a-security-token',
        null,
        expect.any(Function),
      )
      expect(wrapper.findAll('[data-test="message-owner"]')).toHaveLength(2)
      expect(router.currentRoute.value.fullPath).toBe('/assistant/5')
    })

    it('sends on Enter, and breaks the line on Shift+Enter', async () => {
      const { wrapper } = await open({ route: '/assistant', conversations: [] })
      const start = vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
      await type(wrapper, 'Hello')
      const box = wrapper.find('[data-test="chat-input"] textarea')

      await box.trigger('keydown', { key: 'Enter', shiftKey: true })
      expect(start).not.toHaveBeenCalled()
      await box.trigger('keydown', { key: 'Enter', isComposing: true })
      expect(start).not.toHaveBeenCalled()

      await box.trigger('keydown', { key: 'Enter' })
      await flushPromises()

      expect(start).toHaveBeenCalledTimes(1)
    })

    it('sends nothing for an empty question or one that is too long', async () => {
      const { wrapper, find } = await open({ route: '/assistant', conversations: [] })
      const start = vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())

      await type(wrapper, '   ')
      await find('chat-form').trigger('submit')
      expect((find('chat-send').element as HTMLButtonElement).disabled).toBe(true)

      await type(wrapper, 'x'.repeat(2001))
      await find('chat-form').trigger('submit')

      expect(start).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('Keep it under 2000 characters.')
      expect((find('chat-send').element as HTMLButtonElement).disabled).toBe(true)
    })

    it('says what went wrong and keeps the question in the box', async () => {
      const { wrapper, find, text } = await open({ route: '/assistant', conversations: [] })
      vi.spyOn(chatApi, 'askAndFollow').mockRejectedValue(offline())
      await type(wrapper, 'Anything?')

      await find('chat-form').trigger('submit')
      await flushPromises()

      expect(text('chat-failure')).toContain("Can't reach AresGate.")
      expect(find('chat-writing').exists()).toBe(false)
      expect(find('chat-pending').exists()).toBe(false)
      const box = wrapper.find('[data-test="chat-input"] textarea').element as HTMLTextAreaElement
      expect(box.value).toBe('Anything?')
    })

    it('shows the reason in the thread when the AI could not answer, and asks again on request', async () => {
      const failed = conversation({
        messages: [
          question(),
          answer({ ok: false, text: 'AI is turned off.', lookups: [], cites: [], call_ids: [] }),
        ],
      })
      const { wrapper, find, text } = await open({ opened: failed })
      expect(text('message-failed')).toContain('AI is turned off.')
      const again = vi.spyOn(chatApi, 'retryConversation').mockResolvedValue(conversation())

      await find('message-retry').trigger('click')
      await flushPromises()

      expect(again).toHaveBeenCalledWith(5, 'a-security-token')
      expect(wrapper.find('[data-test="message-failed"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="chat-thread"]').text()).toContain('Start with incident 3')
    })

    it('does nothing to retry when the last answer did not fail', async () => {
      const { find } = await open()

      expect(find('message-retry').exists()).toBe(false)
    })
  })

  describe('what was sent', () => {
    it('opens the request that made an answer', async () => {
      const { wrapper } = await open()

      await wrapper.findAll('[data-test="message-call"]')[1]?.trigger('click')
      await flushPromises()

      const dialog = wrapper.findComponent(AiCallDialog)
      expect(dialog.props('callId')).toBe(12)
      expect(dialog.props('modelValue')).toBe(true)

      dialog.vm.$emit('update:modelValue', false)
      await flushPromises()

      expect(wrapper.findComponent(AiCallDialog).props('modelValue')).toBe(false)
    })
  })

  describe('deleting', () => {
    it('asks first and then deletes the conversation that is open and goes back to a new one', async () => {
      const { wrapper, find, list, router } = await open()
      const remove = vi.spyOn(chatApi, 'deleteConversation').mockResolvedValue(undefined)
      list.mockResolvedValue([])

      await find('conversation-delete').trigger('click')
      await flushPromises()
      const confirm = document.body.querySelector('[data-test="confirm-dialog"]')
      expect(confirm?.textContent).toContain('What needs my attention right now?')
      expect(remove).not.toHaveBeenCalled()
      ;(confirm?.querySelector('[data-test="confirm-accept"]') as HTMLElement).click()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith(5, 'a-security-token')
      await vi.waitFor(() => {
        expect(router.currentRoute.value.fullPath).toBe('/assistant')
      })
      expect(wrapper.find('[data-test="chat-empty"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="conversations-empty"]').exists()).toBe(true)
    })

    it('stays where it is when another conversation is deleted', async () => {
      const { wrapper, router } = await open({
        conversations: [summary({ id: 5 }), summary({ id: 6, title: 'Another' })],
      })
      const remove = vi.spyOn(chatApi, 'deleteConversation').mockResolvedValue(undefined)

      await wrapper.findAll('[data-test="conversation-delete"]')[1]?.trigger('click')
      await flushPromises()
      document.body
        .querySelector<HTMLElement>('[data-test="confirm-dialog"] [data-test="confirm-accept"]')
        ?.click()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith(6, 'a-security-token')
      expect(router.currentRoute.value.fullPath).toBe('/assistant/5')
    })

    it('is not done when cancelled', async () => {
      const { find } = await open()
      const remove = vi.spyOn(chatApi, 'deleteConversation').mockResolvedValue(undefined)

      await find('conversation-delete').trigger('click')
      await flushPromises()
      document.body
        .querySelector<HTMLElement>('[data-test="confirm-dialog"] [data-test="confirm-cancel"]')
        ?.click()
      await flushPromises()

      expect(remove).not.toHaveBeenCalled()
      expect(
        document.body.querySelector('.v-overlay--active [data-test="confirm-dialog"]'),
      ).toBeNull()
    })

    it('says what went wrong', async () => {
      const { find, text } = await open()
      vi.spyOn(chatApi, 'deleteConversation').mockRejectedValue(offline())

      await find('conversation-delete').trigger('click')
      await flushPromises()
      document.body
        .querySelector<HTMLElement>('[data-test="confirm-dialog"] [data-test="confirm-accept"]')
        ?.click()
      await flushPromises()

      expect(text('chat-failure')).toContain("Can't reach AresGate.")
    })
  })

  describe('on a phone', () => {
    it('keeps the conversations behind a button', async () => {
      const { wrapper, find } = await open({ width: 400, route: '/assistant' })

      expect(wrapper.find('aside').exists()).toBe(false)
      expect(find('conversations-open').text()).toContain('Conversations (1)')

      await find('conversations-open').trigger('click')
      await flushPromises()

      const sheet = document.body.querySelector('[data-test="conversations-sheet"]')
      expect(sheet?.textContent).toContain('What needs my attention right now?')
    })

    it('deletes from the list in the sheet, and the sheet can be closed', async () => {
      const { wrapper, find } = await open({ width: 400 })
      vi.spyOn(chatApi, 'deleteConversation').mockResolvedValue(undefined)
      await find('conversations-open').trigger('click')
      await flushPromises()

      document.body.querySelector<HTMLElement>('[data-test="conversation-delete"]')?.click()
      await flushPromises()

      expect(document.body.querySelector('[data-test="confirm-dialog"]')?.textContent).toContain(
        'What needs my attention right now?',
      )
      wrapper.findComponent(VBottomSheet).vm.$emit('update:modelValue', false)
      await flushPromises()
      expect(
        document.body.querySelector('.v-overlay--active [data-test="conversations-sheet"]'),
      ).toBeNull()
    })

    it('puts the list away when a conversation is chosen', async () => {
      const { find, router } = await open({
        width: 400,
        conversations: [summary({ id: 5 }), summary({ id: 6, title: 'Another' })],
      })
      await find('conversations-open').trigger('click')
      await flushPromises()
      vi.spyOn(chatApi, 'fetchConversation').mockResolvedValue(conversation({ id: 6 }))

      await router.push('/assistant/6')
      await flushPromises()

      expect(
        document.body.querySelector('.v-overlay--active [data-test="conversations-sheet"]'),
      ).toBeNull()
    })
  })
})
