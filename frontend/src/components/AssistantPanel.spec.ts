import * as chatApi from '@/api/aiChat'
import { ApiError } from '@/api/client'
import AiCallDialog from '@/components/AiCallDialog.vue'
import AssistantPanel from '@/components/AssistantPanel.vue'
import { useAssistantStore } from '@/stores/assistant'
import { action, answer, conversation, question } from '@/test/aiChat'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(route = '/', width = 1280) {
  const mounted = await mountWithPlugins(AssistantPanel, {
    signedIn: 'admin',
    withApp: true,
    width,
    route,
  })
  await mounted.router.isReady()
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, assistant: useAssistantStore() }
}

describe('AssistantPanel', () => {
  it('invites a question, with ones to try that fit the page', async () => {
    const { wrapper, find } = await open('/incidents/4')
    expect(find('panel-empty').exists()).toBe(true)
    expect(find('panel-context').text()).toContain('incident 4')
    const starters = wrapper.findAll('[data-test="panel-starter"]')
    expect(starters[0]?.text()).toContain('this incident')
  })

  it('says nothing of the page on the Assistant page, which is the conversation', async () => {
    const { find } = await open('/assistant')
    expect(find('panel-context').exists()).toBe(false)
  })

  it('puts a starter in the box', async () => {
    const { wrapper, assistant } = await open('/incidents/4')
    await wrapper.find('[data-test="panel-starter"]').trigger('click')
    expect(assistant.draft).toContain('this incident')
  })

  it('asks the question from the page it is on, and shows it at once', async () => {
    let release: (value: chatApi.Conversation) => void = () => undefined
    const start = vi.spyOn(chatApi, 'askAndFollow').mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }),
    )
    const { wrapper, find } = await open('/incidents/4')
    await wrapper.find('[data-test="panel-input"] textarea').setValue('Is this bad?')
    await find('panel-form').trigger('submit')
    await flushPromises()

    expect(start).toHaveBeenCalledWith(
      null,
      'Is this bad?',
      'a-security-token',
      { kind: 'incident', id: 4 },
      expect.any(Function),
    )
    expect(find('panel-pending').text()).toBe('Is this bad?')
    expect(find('panel-writing').exists()).toBe(true)

    release(conversation())
    await flushPromises()
    expect(find('panel-writing').exists()).toBe(false)
    expect(wrapper.findAll('article').length).toBeGreaterThan(1)
  })

  it('shows what the answer has looked at and written as it comes', async () => {
    let follow: (event: chatApi.AnswerEvent) => void = () => undefined
    vi.spyOn(chatApi, 'askAndFollow').mockImplementation((_id, _text, _token, _page, onEvent) => {
      follow = onEvent
      return new Promise(() => undefined)
    })
    const { wrapper, find } = await open()
    await wrapper.find('[data-test="panel-input"] textarea').setValue('Hello')
    await find('panel-form').trigger('submit')
    await flushPromises()

    follow({ kind: 'looked', lookup: { tool: 'open_incidents', summary: '2 open incidents' } })
    follow({ kind: 'wrote', text: 'Start with incident 3.' })
    await flushPromises()
    expect(find('panel-writing').text()).toContain('2 open incidents')
    expect(find('panel-writing').text()).toContain('Start with incident 3.')

    follow({ kind: 'dropped' })
    await flushPromises()
    expect(find('panel-writing').text()).not.toContain('Start with')
  })

  it('sends with Enter and not with Shift+Enter or while an input method is composing', async () => {
    const start = vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
    const { wrapper } = await open()
    const input = wrapper.find('[data-test="panel-input"] textarea')
    await input.setValue('Hello')

    await input.trigger('keydown', { key: 'Enter', shiftKey: true })
    await input.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(start).not.toHaveBeenCalled()

    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(start).toHaveBeenCalledTimes(1)
  })

  it('will not send an empty question', async () => {
    const { find } = await open()
    expect(find('panel-send').attributes('disabled')).toBeDefined()
  })

  it('says when the question is too long', async () => {
    const { wrapper, assistant } = await open()
    assistant.draft = 'x'.repeat(5000)
    await flushPromises()
    expect(wrapper.text()).toContain('Keep it under')
  })

  it('shows the failure, and keeps the question', async () => {
    vi.spyOn(chatApi, 'askAndFollow').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { wrapper, find, assistant } = await open()
    await wrapper.find('[data-test="panel-input"] textarea').setValue('Hello')
    await find('panel-form').trigger('submit')
    await flushPromises()
    expect(find('panel-failure').text()).toBe("Can't reach AresGate.")
    expect(assistant.draft).toBe('Hello')
  })

  it('says when there is no AI to ask', async () => {
    const { find, assistant } = await open()
    expect(find('panel-off').exists()).toBe(false)
    assistant.ready = false
    await flushPromises()
    expect(find('panel-off').exists()).toBe(true)
  })

  it('shows the conversation, with what it suggests, and asks a failed answer again', async () => {
    const retried = vi.spyOn(chatApi, 'retryConversation').mockResolvedValue(conversation())
    const { wrapper, find, assistant } = await open()
    assistant.current = conversation({
      messages: [
        question(),
        answer({ actions: [action()] }),
        answer({ id: 3, ok: false, text: 'It failed.' }),
      ],
    })
    await flushPromises()
    expect(find('panel-empty').exists()).toBe(false)
    expect(wrapper.find('[data-test="message-actions"]').exists()).toBe(true)

    await wrapper.find('[data-test="message-retry"]').trigger('click')
    await flushPromises()
    expect(retried).toHaveBeenCalled()
  })

  it('shows what was sent to the provider', async () => {
    const { wrapper, assistant } = await open()
    assistant.current = conversation()
    await flushPromises()
    await wrapper.find('[data-test="message-call"]').trigger('click')
    const dialog = wrapper.findComponent(AiCallDialog)
    expect(dialog.props('callId')).toBe(11)
    expect(dialog.props('modelValue')).toBe(true)
    dialog.vm.$emit('update:modelValue', false)
    await flushPromises()
    expect(wrapper.findComponent(AiCallDialog).props('modelValue')).toBe(false)
  })

  it('starts a new conversation, and closes', async () => {
    const { find, assistant } = await open()
    assistant.open = true
    assistant.current = conversation()
    await find('panel-new').trigger('click')
    expect(assistant.current).toBeNull()
    await find('panel-close').trigger('click')
    expect(assistant.open).toBe(false)
  })

  it('goes to the Assistant page, to the conversation if there is one', async () => {
    const { find, assistant } = await open()
    expect(find('panel-full').attributes('href')).toBe('/assistant')
    assistant.current = conversation()
    await flushPromises()
    expect(find('panel-full').attributes('href')).toBe('/assistant/5')
    assistant.open = true
    await find('panel-full').trigger('click')
    expect(assistant.open).toBe(false)
  })

  it('puts the box in focus when it opens', async () => {
    const { assistant, wrapper } = await open()
    assistant.open = true
    await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('puts itself away when what it suggested is opened, on a phone only', async () => {
    const phone = await open('/', 400)
    phone.assistant.open = true
    phone.assistant.current = conversation({ messages: [answer({ actions: [action()] })] })
    await flushPromises()
    vi.spyOn(phone.router, 'push').mockResolvedValue(undefined)
    await phone.wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(phone.assistant.open).toBe(false)

    const wide = await open('/', 1280)
    wide.assistant.open = true
    wide.assistant.current = conversation({ messages: [answer({ actions: [action()] })] })
    await flushPromises()
    vi.spyOn(wide.router, 'push').mockResolvedValue(undefined)
    await wide.wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(wide.assistant.open).toBe(true)
  })
})
