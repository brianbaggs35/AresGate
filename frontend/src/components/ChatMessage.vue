<script setup lang="ts">
import { Eye, RotateCcw, Sparkles } from '@lucide/vue'
import { computed } from 'vue'

import type { ChatCite, ChatMessage } from '@/api/aiChat'
import { blocks, citeRoute } from '@/chat'
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
    <header class="message__head text-label-large">
      <v-icon :icon="Sparkles" size="18" aria-hidden="true" />
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
      <span class="text-label-medium text-medium-emphasis">Looked at</span>
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
      <span class="text-label-medium text-medium-emphasis">Based on</span>
      <v-chip
        v-for="{ cite, to } in links"
        :key="`${cite.kind}-${cite.key}`"
        size="small"
        variant="tonal"
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
  </article>
</template>

<style scoped>
.message {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: min(100%, 46rem);
  padding: 0.875rem 1rem;
  border-radius: 1rem;
}

.message p,
.message ul {
  margin: 0;
}

.message ul {
  padding-inline-start: 1.25rem;
}

/* What the owner wrote: to the right, tinted. */
.message--owner {
  align-self: flex-end;
  background: rgb(var(--v-theme-primary), 0.14);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* What the assistant answered: to the left, on a surface of its own. */
.message--assistant {
  align-self: flex-start;
  width: 100%;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  background: rgb(var(--v-theme-surface));
  overflow-wrap: anywhere;
}

.message__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.message__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
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
</style>
