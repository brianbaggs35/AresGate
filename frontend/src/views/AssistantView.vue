<script setup lang="ts">
import { ArrowUp, MessagesSquare, Sparkles, SquarePen } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

import { fetchAi } from '@/api/ai'
import {
  askAndFollow,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  retryConversation,
  type ChatMessage as Message,
  type Conversation,
  type ConversationSummary,
} from '@/api/aiChat'
import { ApiError, errorMessage } from '@/api/client'
import { MAX_QUESTION, questionAbout, STARTERS } from '@/chat'
import { useAnswerProgress } from '@/chatProgress'
import AiCallDialog from '@/components/AiCallDialog.vue'
import AppPage from '@/components/AppPage.vue'
import ChatConversations from '@/components/ChatConversations.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatWriting from '@/components/ChatWriting.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * The assistant: ask about the network in plain words and get an answer that says what it looked
 * at and what it is based on. It can only read. Conversations are kept until they are deleted, and
 * every answer has a button to read exactly what the provider was sent.
 */
const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const conversations = ref<ConversationSummary[]>([])
const current = ref<Conversation | null>(null)
const draft = ref('')
/** Something is being answered; the question that was just sent is shown at once, before the
 * answer comes. */
const sending = ref(false)
const pending = ref<string | null>(null)
/** What the answer has looked at and written so far, while it is made. */
const { looked, writing, reset: clearProgress, follow } = useAnswerProgress()
const failure = ref<string | null>(null)
const loadError = ref<string | null>(null)
const notFound = ref(false)
const loading = ref(false)
/** Whether an AI provider is set up and on; unknown until it has been asked. */
const ready = ref<boolean | null>(null)
const listOpen = ref(false)
const doomed = ref<ConversationSummary | null>(null)
const deleting = ref(false)
const showing = ref<number | null>(null)
const callOpen = ref(false)
const box = ref<{ focus: () => void } | null>(null)
/** Which load of a conversation is the newest, so the answer to an older one is dropped. */
let latest = 0

const id = computed(() => {
  const given = route.params.id
  return typeof given === 'string' ? Number(given) : null
})
const messages = computed<Message[]>(() => current.value?.messages ?? [])
const tooLong = computed(() => draft.value.length > MAX_QUESTION)
const canSend = computed(() => draft.value.trim() !== '' && !tooLong.value && !sending.value)
/** The last answer, if it failed and nothing is under way: the one that can be asked again. */
const retryable = computed(() => {
  const last = messages.value.at(-1)
  return last?.role === 'assistant' && !last.ok && !sending.value ? last.id : null
})
const confirming = computed({
  get: () => doomed.value !== null,
  // The dialog only ever says that it was closed.
  set: () => {
    doomed.value = null
  },
})

/** Scrolls to the newest word. An answer that is being written is followed at once, since a
 * smooth scroll would always be behind it. */
function scrollToEnd(instant = false) {
  void nextTick(() => {
    const calm = instant || window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: calm ? 'auto' : 'smooth',
    })
  })
}

async function refreshList() {
  try {
    conversations.value = await session.call(fetchConversations)
  } catch {
    // The list is as it was; the next change to it will try again.
  }
}

async function loadConversation(wanted: number) {
  const mine = ++latest
  try {
    const found = await session.call(() => fetchConversation(wanted))
    if (mine !== latest) return
    current.value = found
    loadError.value = null
    scrollToEnd()
  } catch (error) {
    if (mine !== latest) return
    current.value = null
    loadError.value = errorMessage(error)
    notFound.value = error instanceof ApiError && error.code === 'not_found'
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  notFound.value = false
  try {
    conversations.value = await session.call(fetchConversations)
    if (id.value !== null) await loadConversation(id.value)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function checkAi() {
  try {
    const ai = await session.call(fetchAi)
    ready.value = ai.enabled && ai.provider !== null
  } catch {
    // Asking will say why if it can't be done.
  }
}

onMounted(() => {
  const asked = questionAbout(typeof route.query.about === 'string' ? route.query.about : null)
  if (asked !== null && id.value === null) draft.value = asked
  void checkAi()
  void load()
})
onBeforeUnmount(() => {
  latest += 1
})

// The answer is followed as it is written.
watch(writing, () => {
  scrollToEnd(true)
})

// Another conversation was chosen (or a new one begun) from the list or the address.
watch(id, (wanted) => {
  failure.value = null
  loadError.value = null
  notFound.value = false
  listOpen.value = false
  if (wanted === null) {
    latest += 1
    current.value = null
  } else if (current.value?.id !== wanted) {
    void loadConversation(wanted)
  }
})

async function answer(request: (token: string) => Promise<Conversation>, sent: string | null) {
  sending.value = true
  pending.value = sent
  failure.value = null
  clearProgress()
  scrollToEnd()
  // The conversation this began, if it began one: its page is opened once the answer is shown.
  let began: number | null = null
  try {
    const result = await session.change(request)
    latest += 1
    if (current.value === null) began = result.id
    current.value = result
    if (sent !== null) draft.value = ''
    void refreshList()
  } catch (error) {
    // The question stays in the box, to send again or change.
    failure.value = errorMessage(error)
  } finally {
    sending.value = false
    pending.value = null
    clearProgress()
    scrollToEnd()
  }
  if (began !== null) await router.replace({ name: 'assistant-chat', params: { id: began } })
}

function send() {
  if (!canSend.value) return
  const text = draft.value.trim()
  const open = current.value
  void answer((token) => askAndFollow(open?.id ?? null, text, token, null, follow), text)
}

/** Asks again after a failed answer, which only the button on the last one can do. */
function retry() {
  const open = current.value as Conversation
  void answer((token) => retryConversation(open.id, token), null)
}

function pick(question: string) {
  draft.value = question
  box.value?.focus()
}

/** Enter sends; Shift+Enter starts a new line, and Enter that confirms an input method is left
 * alone. */
function onEnter(event: KeyboardEvent) {
  if (event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

async function remove() {
  // Only the dialog for a conversation that was picked can ask for this.
  const gone = doomed.value as ConversationSummary
  deleting.value = true
  try {
    await session.change((token) => deleteConversation(gone.id, token))
    doomed.value = null
    if (current.value?.id === gone.id) {
      current.value = null
      await router.replace({ name: 'assistant' })
    }
    await refreshList()
  } catch (error) {
    failure.value = errorMessage(error)
    doomed.value = null
  } finally {
    deleting.value = false
  }
}

function showCall(call: number) {
  showing.value = call
  callOpen.value = true
}
</script>

<template>
  <AppPage width="wide" class="assistant">
    <PageHeader
      title="Assistant"
      description="Ask about your network in plain words. It looks things up in what your integrations reported, says what it based the answer on, and can't change anything."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          :prepend-icon="SquarePen"
          :to="{ name: 'assistant' }"
          data-test="new-chat"
        >
          New conversation
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError !== null"
      :message="loadError"
      :can-retry="!notFound"
      :loading="loading"
      data-test="chat-error"
      @retry="load"
    />

    <div v-else class="assistant__layout">
      <aside v-if="mdAndUp" class="assistant__side" aria-label="Conversations">
        <SectionCard title="Conversations">
          <ChatConversations
            :conversations="conversations"
            :current="current?.id ?? null"
            @delete="doomed = $event"
          />
        </SectionCard>
      </aside>
      <v-btn
        v-else
        variant="tonal"
        :prepend-icon="MessagesSquare"
        class="assistant__list-button"
        data-test="conversations-open"
        @click="listOpen = true"
      >
        Conversations ({{ conversations.length }})
      </v-btn>

      <section class="assistant__main" aria-label="The conversation">
        <v-alert v-if="ready === false" type="info" variant="tonal" data-test="chat-off">
          AI is off or has no provider yet, so there is nothing to answer.
          <RouterLink :to="{ name: 'settings-ai' }" data-test="chat-off-settings">
            Set it up under Settings > AI
          </RouterLink>
        </v-alert>

        <EmptyState
          v-if="messages.length === 0 && pending === null"
          title="Ask about your network"
          description="Try one of these, or ask anything about your incidents, devices and integrations."
          :icon="Sparkles"
          data-test="chat-empty"
        >
          <div class="assistant__starters">
            <v-btn
              v-for="starter in STARTERS"
              :key="starter"
              variant="outlined"
              data-test="chat-starter"
              @click="pick(starter)"
            >
              {{ starter }}
            </v-btn>
          </div>
        </EmptyState>

        <div
          v-else
          class="assistant__thread"
          role="log"
          aria-label="Conversation"
          data-test="chat-thread"
        >
          <ChatMessage
            v-for="message in messages"
            :key="message.id"
            :message="message"
            :can-retry="message.id === retryable"
            @retry="retry"
            @show-call="showCall"
          />
          <article v-if="pending !== null" class="assistant__pending" data-test="chat-pending">
            <p class="text-body-large">{{ pending }}</p>
          </article>
          <ChatWriting v-if="sending" :looked="looked" :text="writing" data-test="chat-writing" />
        </div>

        <v-alert v-if="failure" type="error" variant="tonal" role="alert" data-test="chat-failure">
          {{ failure }}
        </v-alert>

        <form class="assistant__composer" data-test="chat-form" @submit.prevent="send">
          <v-textarea
            ref="box"
            v-model="draft"
            label="Ask about your network"
            rows="1"
            max-rows="6"
            auto-grow
            hide-details="auto"
            :error-messages="tooLong ? `Keep it under ${MAX_QUESTION} characters.` : undefined"
            :disabled="sending"
            data-test="chat-input"
            @keydown.enter="onEnter"
          />
          <v-btn
            type="submit"
            color="primary"
            icon
            :disabled="!canSend"
            :loading="sending"
            aria-label="Send"
            data-test="chat-send"
          >
            <v-icon :icon="ArrowUp" />
          </v-btn>
        </form>
        <p class="text-body-medium text-medium-emphasis" data-test="chat-note">
          The assistant only reads. Under every answer you can see exactly what your AI provider was
          sent. What it may see is set under
          <RouterLink :to="{ name: 'settings-ai' }">Settings > AI</RouterLink>.
        </p>
      </section>
    </div>

    <v-bottom-sheet v-model="listOpen" aria-label="Conversations">
      <v-card class="pa-4" data-test="conversations-sheet">
        <ChatConversations
          :conversations="conversations"
          :current="current?.id ?? null"
          @delete="doomed = $event"
        />
      </v-card>
    </v-bottom-sheet>

    <ConfirmDialog
      v-model="confirming"
      title="Delete this conversation?"
      confirm-label="Delete"
      destructive
      :busy="deleting"
      @confirm="remove"
    >
      "{{ doomed?.title }}" and everything said in it will be deleted. The requests to your AI
      provider stay in the usage record.
    </ConfirmDialog>

    <AiCallDialog v-model="callOpen" :call-id="showing" />
  </AppPage>
</template>

<style scoped>
.assistant__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}

@media (min-width: 960px) {
  .assistant__layout {
    grid-template-columns: 18rem minmax(0, 1fr);
    align-items: start;
  }

  .assistant__side {
    position: sticky;
    top: 1rem;
  }
}

.assistant__main {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.assistant__main p {
  margin: 0;
}

.assistant__list-button {
  align-self: flex-start;
}

.assistant__thread {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.assistant__pending {
  align-self: flex-end;
  max-width: min(100%, 46rem);
  padding: 0.875rem 1rem;
  border-radius: 1rem;
  background: rgb(var(--v-theme-primary), 0.14);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.assistant__pending p {
  margin: 0;
}

.assistant__starters {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

/* The box to type in stays at the bottom of the screen while the conversation scrolls above it. */
.assistant__composer {
  position: sticky;
  bottom: var(--v-layout-bottom, 0px);
  z-index: 1;
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 0.75rem 0;
  background: rgb(var(--v-theme-background));
}
</style>
