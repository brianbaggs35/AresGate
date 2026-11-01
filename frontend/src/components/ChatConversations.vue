<script setup lang="ts">
import { Trash2 } from '@lucide/vue'

import type { ConversationSummary } from '@/api/aiChat'
import { formatAgo } from '@/format'

/**
 * The conversations that were had, the latest first, each a link to open it and a button to
 * delete it. The one that is open is marked.
 */
defineProps<{ conversations: ConversationSummary[]; current: number | null }>()
const emit = defineEmits<{ delete: [conversation: ConversationSummary] }>()
</script>

<template>
  <nav aria-label="Conversations" data-test="conversations">
    <p
      v-if="conversations.length === 0"
      class="text-body-medium text-medium-emphasis"
      data-test="conversations-empty"
    >
      Nothing asked yet. Your conversations are kept here until you delete them.
    </p>
    <ul v-else class="conversations">
      <li
        v-for="conversation in conversations"
        :key="conversation.id"
        class="conversations__item"
        :class="{ 'conversations__item--current': conversation.id === current }"
        data-test="conversation"
      >
        <RouterLink
          :to="{ name: 'assistant-chat', params: { id: conversation.id } }"
          :aria-current="conversation.id === current ? 'page' : undefined"
          class="conversations__link"
          data-test="conversation-link"
        >
          <span class="text-label-large conversations__title">{{ conversation.title }}</span>
          <span class="text-body-small text-medium-emphasis">
            {{ formatAgo(conversation.updated_at) }}
          </span>
        </RouterLink>
        <v-btn
          icon
          variant="text"
          size="small"
          :aria-label="`Delete the conversation ${conversation.title}`"
          data-test="conversation-delete"
          @click="emit('delete', conversation)"
        >
          <v-icon :icon="Trash2" size="18" />
        </v-btn>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.conversations {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.conversations__item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  border-radius: 0.75rem;
}

.conversations__item--current {
  background: rgb(var(--v-theme-primary), 0.14);
}

.conversations__link {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  color: inherit;
  text-decoration: none;
}

.conversations__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
