import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchAi } from '@/api/ai'
import { askAndFollow, retryConversation, type Conversation, type PageContext } from '@/api/aiChat'
import { errorMessage } from '@/api/client'
import { MAX_QUESTION } from '@/chat'
import { useAnswerProgress } from '@/chatProgress'
import { useSessionStore } from '@/stores/session'

/**
 * The assistant's panel, which opens over any page: whether it is open, and the conversation in it.
 * The conversation is one of the ones the Assistant page lists, so it can be carried on there. The
 * page it is asked from is handed to each question, so it can answer about what is on screen.
 */
export const useAssistantStore = defineStore('assistant', () => {
  const session = useSessionStore()
  /** What the answer has looked at and written so far, while it is made. */
  const { looked, writing, reset: clearProgress, follow } = useAnswerProgress()

  const open = ref(false)
  const current = ref<Conversation | null>(null)
  const draft = ref('')
  /** Something is being answered; the question that was just sent is shown at once. */
  const sending = ref(false)
  const pending = ref<string | null>(null)
  const failure = ref<string | null>(null)
  /** Whether an AI provider is set up and on; unknown until it has been asked. */
  const ready = ref<boolean | null>(null)

  const tooLong = computed(() => draft.value.length > MAX_QUESTION)
  const canSend = computed(() => draft.value.trim() !== '' && !tooLong.value && !sending.value)
  /** The last answer, if it failed and nothing is under way: the one that can be asked again. */
  const retryable = computed(() => {
    const last = current.value?.messages.at(-1)
    return last?.role === 'assistant' && !last.ok && !sending.value ? last.id : null
  })

  async function checkAi() {
    try {
      const ai = await session.call(fetchAi)
      ready.value = ai.enabled && ai.provider !== null
    } catch {
      // Asking will say why if it can't be done.
    }
  }

  function show() {
    open.value = true
    if (ready.value === null) void checkAi()
  }

  function hide() {
    open.value = false
  }

  function toggle() {
    if (open.value) hide()
    else show()
  }

  /** Begins a new conversation: the one that was open stays in the list on the Assistant page. */
  function begin() {
    current.value = null
    draft.value = ''
    failure.value = null
  }

  async function answer(
    request: (token: string) => Promise<Conversation>,
    sent: string | null,
  ): Promise<void> {
    sending.value = true
    pending.value = sent
    failure.value = null
    clearProgress()
    try {
      current.value = await session.change(request)
      if (sent !== null) draft.value = ''
    } catch (error) {
      // The question stays in the box, to send again or change.
      failure.value = errorMessage(error)
    } finally {
      sending.value = false
      pending.value = null
      clearProgress()
    }
  }

  /** Asks what is in the box, from the page the owner is on. */
  async function send(page: PageContext | null): Promise<void> {
    if (!canSend.value) return
    const text = draft.value.trim()
    const open = current.value
    await answer((token) => askAndFollow(open?.id ?? null, text, token, page, follow), text)
  }

  /** Asks again after a failed answer, which only the button on the last one can do. */
  async function retry(): Promise<void> {
    const open = current.value as Conversation
    await answer((token) => retryConversation(open.id, token), null)
  }

  /** Forgets everything on sign-out, so the next person to sign in does not see it. */
  function reset() {
    open.value = false
    current.value = null
    draft.value = ''
    pending.value = null
    failure.value = null
    ready.value = null
    clearProgress()
  }

  return {
    open,
    current,
    draft,
    sending,
    pending,
    looked,
    writing,
    failure,
    ready,
    tooLong,
    canSend,
    retryable,
    show,
    hide,
    toggle,
    begin,
    send,
    retry,
    reset,
  }
})
