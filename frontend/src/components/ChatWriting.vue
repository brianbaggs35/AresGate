<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { computed } from 'vue'

import type { ChatLookup } from '@/api/aiChat'
import { blocks } from '@/chat'
import ChatText from '@/components/ChatText.vue'

/**
 * An answer while it is being made: what the assistant has looked at so far, and what it has
 * written, which grows as the provider writes it. It is not the answer yet: the one that is kept
 * replaces it when it has ended, with what it is based on and what it suggests.
 *
 * What is read out is left to the answer that replaces it, since a screen reader that spoke every
 * word as it came would be no use to anyone.
 */
const props = defineProps<{ looked: ChatLookup[]; text: string }>()

const parts = computed(() => blocks(props.text))
</script>

<template>
  <article class="writing" aria-label="The assistant is answering" aria-live="off" aria-busy="true">
    <header class="writing__head text-label-large">
      <v-icon :icon="Sparkles" size="18" aria-hidden="true" />
      <span>Assistant</span>
    </header>

    <section
      v-if="looked.length"
      class="writing__row"
      aria-label="What it has looked at"
      data-test="writing-lookups"
    >
      <span class="text-label-medium text-medium-emphasis">Looked at</span>
      <v-chip
        v-for="(lookup, index) in looked"
        :key="index"
        size="small"
        variant="outlined"
        data-test="writing-lookup"
      >
        {{ lookup.summary }}
      </v-chip>
    </section>

    <div v-if="text" class="writing__body" data-test="writing-text">
      <template v-for="(block, index) in parts" :key="index">
        <ul v-if="'items' in block" class="text-body-large">
          <li v-for="item in block.items" :key="item"><ChatText :text="item" /></li>
        </ul>
        <p v-else class="text-body-large"><ChatText :text="block.paragraph" /></p>
      </template>
    </div>
    <output v-else class="writing__busy text-body-large" data-test="writing-busy">
      <v-progress-circular indeterminate size="20" width="2" aria-hidden="true" />
      Looking into it. This can take a minute.
    </output>
  </article>
</template>

<style scoped>
.writing {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
  max-width: min(100%, 46rem);
  padding: 0.875rem 1rem;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  border-radius: 1rem;
  background: rgb(var(--v-theme-surface));
  overflow-wrap: anywhere;
}

.writing p,
.writing ul {
  margin: 0;
}

.writing ul {
  padding-inline-start: 1.25rem;
}

.writing__head,
.writing__row,
.writing__busy {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.writing__row {
  flex-wrap: wrap;
}

.writing__busy {
  gap: 0.75rem;
}

.writing__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
