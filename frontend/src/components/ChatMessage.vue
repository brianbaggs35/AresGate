<script setup lang="ts">
import { Eye, Link2, RotateCcw, Search } from '@lucide/vue'
import { computed } from 'vue'

import type { ChatCite, ChatMessage } from '@/api/aiChat'
import { blocks, citeRoute } from '@/chat'
import AssistantMark from '@/components/AssistantMark.vue'
import ChatActions from '@/components/ChatActions.vue'
import ChatText from '@/components/ChatText.vue'
import { formatAgo } from '@/format'

/**
 * One thing said in the chat: the owner's question, or the assistant's answer. An answer says what
 * it looked at and what it is based on (with links), and has a button to read exactly what the
 * provider was sent. One that could not be made says why and can be asked again.
 */
const props = defineProps<{
  message: ChatMessage
  /** Whether a failed answer can be asked again now: it is the last one and nothing is under way. */
  canRetry?: boolean
}>()
const emit = defineEmits<{ retry: []; 'show-call': [id: number]; opened: [] }>()

const fromOwner = computed(() => props.message.role === 'user')
const parts = computed(() => blocks(props.message.text))
/** What is cited that has a page to go to. */
const links = computed(() =>
  props.message.cites.flatMap((cite: ChatCite) => {
    const to = citeRoute(cite)
    return to ? [{ cite, to }] : []
  }),
)

function callLabel(index: number): string {
  const total = props.message.call_ids.length
  return total === 1 ? 'See what was sent' : `See what was sent (${index + 1} of ${total})`
}
</script>

<template>
  <article
    v-if="fromOwner"
    class="message message--owner"
    aria-label="You asked"
    data-test="message-owner"
  >
    <p class="text-body-large" data-test="message-text">{{ message.text }}</p>
  </article>

  <article v-else class="message message--assistant" aria-label="The assistant answered">
    <AssistantMark :size="32" class="message__mark" />
    <div class="message__content">
      <header class="message__head text-label-large">
        <span>Assistant</span>
        <span class="text-medium-emphasis" data-test="message-time">{{
          formatAgo(message.created_at)
        }}</span>
      </header>

      <div v-if="!message.ok" class="message__failed">
        <v-alert type="warning" variant="tonal" data-test="message-failed">
          {{ message.text }}
          <RouterLink :to="{ name: 'settings-ai' }" data-test="message-settings">
            Open the AI settings
          </RouterLink>
        </v-alert>
        <v-btn
          v-if="canRetry"
          variant="tonal"
          :prepend-icon="RotateCcw"
          data-test="message-retry"
          @click="emit('retry')"
        >
          Ask again
        </v-btn>
      </div>

      <div v-else class="message__body" data-test="message-text">
        <template v-for="(block, index) in parts" :key="index">
          <ul v-if="'items' in block" class="text-body-large">
            <li v-for="item in block.items" :key="item"><ChatText :text="item" /></li>
          </ul>
          <p v-else class="text-body-large"><ChatText :text="block.paragraph" /></p>
        </template>
      </div>

      <ChatActions
        v-if="message.ok && message.actions.length"
        :actions="message.actions"
        @opened="emit('opened')"
      />

      <section
        v-if="message.ok && message.lookups.length"
        class="message__row"
        aria-label="What it looked at"
        data-test="message-lookups"
      >
        <span class="message__label text-label-medium text-medium-emphasis">
          <v-icon :icon="Search" size="14" aria-hidden="true" />
          Looked at
        </span>
        <v-chip
          v-for="(lookup, index) in message.lookups"
          :key="index"
          size="small"
          variant="outlined"
          data-test="message-lookup"
        >
          {{ lookup.summary }}
        </v-chip>
      </section>

      <section
        v-if="message.ok && links.length"
        class="message__row"
        aria-label="What it is based on"
        data-test="message-cites"
      >
        <span class="message__label text-label-medium text-medium-emphasis">
          <v-icon :icon="Link2" size="14" aria-hidden="true" />
          Based on
        </span>
        <v-chip
          v-for="{ cite, to } in links"
          :key="`${cite.kind}-${cite.key}`"
          size="small"
          variant="tonal"
          color="primary"
          :to="to"
          data-test="message-cite"
        >
          {{ cite.label }}
        </v-chip>
      </section>

      <footer v-if="message.call_ids.length" class="message__row">
        <v-btn
          v-for="(id, index) in message.call_ids"
          :key="id"
          variant="text"
          size="small"
          :prepend-icon="Eye"
          data-test="message-call"
          @click="emit('show-call', id)"
        >
          {{ callLabel(index) }}
        </v-btn>
      </footer>
    </div>
  </article>
</template>

<style scoped>
.message {
  max-width: min(100%, 46rem);
  animation: message-in 200ms ease-out;
}

.message p,
.message ul {
  margin: 0;
}

.message ul {
  padding-inline-start: 1.25rem;
}

/* What the owner wrote: to the right, tinted, with the corner it came from squared off. */
.message--owner {
  align-self: flex-end;
  padding: 0.75rem 1rem;
  border-radius: 1.25rem 1.25rem 0.375rem 1.25rem;
  background: rgb(var(--v-theme-primary), 0.16);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* What the assistant answered: the mark to the left, and the answer beside it with room to read. */
.message--assistant {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-self: flex-start;
  gap: 0.75rem;
  width: 100%;
  overflow-wrap: anywhere;
}

.message__mark {
  margin-top: 0.125rem;
}

.message__content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  border-radius: 0.375rem 1.25rem 1.25rem 1.25rem;
  background: rgb(var(--v-theme-surface));
}

.message__head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.message__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  line-height: 1.6;
}

.message__failed {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.message__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.message__label {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

@keyframes message-in {
  from {
    opacity: 0;
    transform: translateY(0.375rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .message {
    animation: none;
  }
}
</style>
