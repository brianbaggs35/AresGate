<script setup lang="ts">
import { ArrowUp, Eye, Maximize2, Sparkles, SquarePen, X } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

import { MAX_QUESTION } from '@/chat'
import AiCallDialog from '@/components/AiCallDialog.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import { looking, pageOf, startersFor } from '@/pageContext'
import { useAssistantStore } from '@/stores/assistant'

/**
 * The assistant, in a panel that opens over any page: a side drawer on a desktop, a sheet on a
 * phone. What is on the page (the incident, the device, the search of the logs) is handed to every
 * question, so "this" means what you are looking at. It is the same conversation the Assistant page
 * lists and the same assistant: it only reads, and what it suggests you do comes as buttons that
 * you press.
 */
const assistant = useAssistantStore()
const route = useRoute()
const { xs: phone } = useDisplay()

const page = computed(() => pageOf(route))
const seeing = computed(() => looking(page.value))
const starters = computed(() => startersFor(page.value))
const messages = computed(() => assistant.current?.messages ?? [])
const showing = ref<number | null>(null)
const callOpen = ref(false)
const thread = ref<HTMLElement | null>(null)
const box = ref<{ focus: () => void } | null>(null)

function scrollToEnd() {
  void nextTick(() => {
    const element = thread.value
    if (element) element.scrollTop = element.scrollHeight
  })
}

// The newest word is in view, and the box is ready to type in when the panel opens.
watch(() => [messages.value.length, assistant.pending, assistant.sending], scrollToEnd)
watch(
  () => assistant.open,
  (open) => {
    if (open) void nextTick(() => box.value?.focus())
  },
)

function send() {
  void assistant.send(page.value)
}

/** Enter sends; Shift+Enter starts a new line, and Enter that confirms an input method is left
 * alone. */
function onEnter(event: KeyboardEvent) {
  if (event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

function pick(question: string) {
  assistant.draft = question
  box.value?.focus()
}

function showCall(call: number) {
  showing.value = call
  callOpen.value = true
}

/** A phone's sheet is in the way of the page it was asked to open. */
function opened() {
  if (phone.value) assistant.hide()
}

defineExpose({ send })
</script>

<template>
  <section class="panel" aria-label="Assistant" data-test="assistant-panel">
    <header class="panel__head">
      <v-icon :icon="Sparkles" aria-hidden="true" />
      <h2 class="panel__title text-title-medium">Assistant</h2>
      <v-btn
        :icon="SquarePen"
        variant="text"
        size="small"
        aria-label="New conversation"
        data-test="panel-new"
        @click="assistant.begin()"
      />
      <v-btn
        :icon="Maximize2"
        variant="text"
        size="small"
        aria-label="Open the Assistant page"
        :to="
          assistant.current
            ? { name: 'assistant-chat', params: { id: assistant.current.id } }
            : { name: 'assistant' }
        "
        data-test="panel-full"
        @click="assistant.hide()"
      />
      <v-btn
        :icon="X"
        variant="text"
        size="small"
        aria-label="Close the assistant"
        data-test="panel-close"
        @click="assistant.hide()"
      />
    </header>

    <p v-if="seeing" class="panel__looking text-body-medium" data-test="panel-context">
      <v-icon :icon="Eye" size="16" aria-hidden="true" />
      {{ seeing }}
    </p>

    <div
      ref="thread"
      class="panel__thread"
      role="log"
      aria-label="Conversation"
      data-test="panel-thread"
    >
      <v-alert v-if="assistant.ready === false" type="info" variant="tonal" data-test="panel-off">
        AI is off or has no provider yet, so there is nothing to answer.
        <RouterLink :to="{ name: 'settings-ai' }" @click="assistant.hide()">
          Set it up under Settings > AI
        </RouterLink>
      </v-alert>

      <div v-if="messages.length === 0 && assistant.pending === null" class="panel__empty">
        <p class="text-body-large" data-test="panel-empty">
          Ask about what you are looking at, or about your network. It only reads, and says what it
          looked at.
        </p>
        <v-btn
          v-for="starter in starters"
          :key="starter"
          variant="outlined"
          size="small"
          class="panel__starter"
          data-test="panel-starter"
          @click="pick(starter)"
        >
          {{ starter }}
        </v-btn>
      </div>

      <template v-else>
        <ChatMessage
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :can-retry="message.id === assistant.retryable"
          @retry="assistant.retry()"
          @show-call="showCall"
          @opened="opened"
        />
        <article v-if="assistant.pending !== null" class="panel__pending" data-test="panel-pending">
          <p class="text-body-large">{{ assistant.pending }}</p>
        </article>
        <output v-if="assistant.sending" class="panel__busy text-body-large" data-test="panel-busy">
          <v-progress-circular indeterminate size="20" width="2" aria-hidden="true" />
          Looking into it. This can take a minute.
        </output>
      </template>

      <v-alert
        v-if="assistant.failure"
        type="error"
        variant="tonal"
        role="alert"
        data-test="panel-failure"
      >
        {{ assistant.failure }}
      </v-alert>
    </div>

    <form class="panel__box" data-test="panel-form" @submit.prevent="send">
      <v-textarea
        ref="box"
        v-model="assistant.draft"
        label="Ask the assistant"
        rows="1"
        max-rows="5"
        auto-grow
        hide-details="auto"
        :error-messages="
          assistant.tooLong ? `Keep it under ${MAX_QUESTION} characters.` : undefined
        "
        :disabled="assistant.sending"
        data-test="panel-input"
        @keydown.enter="onEnter"
      />
      <v-btn
        type="submit"
        color="primary"
        icon
        :disabled="!assistant.canSend"
        :loading="assistant.sending"
        aria-label="Send"
        data-test="panel-send"
      >
        <v-icon :icon="ArrowUp" />
      </v-btn>
    </form>

    <AiCallDialog v-model="callOpen" :call-id="showing" />
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.panel__head {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 0.75rem 0.5rem 1rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.panel__title {
  flex: 1;
  margin: 0 0 0 0.25rem;
}

.panel__looking {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0;
  padding: 0.5rem 1rem 0;
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.panel__thread {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 0.875rem;
  min-height: 0;
  padding: 1rem;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.panel__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.panel__empty p {
  margin: 0 0 0.25rem;
}

.panel__starter {
  max-width: 100%;
  height: auto;
  min-height: 2rem;
  padding-block: 0.375rem;
  text-align: start;
  white-space: normal;
}

.panel__pending {
  align-self: flex-end;
  max-width: 100%;
  padding: 0.75rem 1rem;
  border-radius: 1rem;
  background: rgb(var(--v-theme-primary), 0.14);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.panel__pending p {
  margin: 0;
}

.panel__busy {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* The box to type in stays below the conversation, clear of a phone's home bar and, with the
   sheet sized by the visible screen, above its keyboard. */
.panel__box {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 0.75rem 1rem calc(0.75rem + env(safe-area-inset-bottom));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}
</style>
