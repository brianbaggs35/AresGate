<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed } from 'vue'

import type { ChatLookup } from '@/api/aiChat'
import { blocks } from '@/chat'
import AssistantMark from '@/components/AssistantMark.vue'
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
    <AssistantMark :size="32" busy class="writing__mark" />
    <div class="writing__content">
      <header class="writing__head text-label-large">
        <span>Assistant</span>
      </header>

      <section
        v-if="looked.length"
        class="writing__row"
        aria-label="What it has looked at"
        data-test="writing-lookups"
      >
        <span class="writing__label text-label-medium text-medium-emphasis">
          <v-icon :icon="Search" size="14" aria-hidden="true" />
          Looked at
        </span>
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
        <span class="writing__dots" aria-hidden="true"><i /><i /><i /></span>
        Looking into it. This can take a minute.
      </output>
    </div>
  </article>
</template>

<style scoped>
.writing {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.75rem;
  width: 100%;
  max-width: min(100%, 46rem);
  overflow-wrap: anywhere;
}

.writing__mark {
  margin-top: 0.125rem;
}

.writing__content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.6));
  border-radius: 0.375rem 1.25rem 1.25rem 1.25rem;
  background: rgb(var(--v-theme-surface));
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

.writing__label {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.writing__busy {
  gap: 0.75rem;
}

.writing__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  line-height: 1.6;
}

/* Three dots that rise in turn, as it is done by someone typing. */
.writing__dots {
  display: inline-flex;
  gap: 0.25rem;
}

.writing__dots i {
  width: 0.4375rem;
  height: 0.4375rem;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  animation: writing-rise 1.2s ease-in-out infinite;
}

.writing__dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.writing__dots i:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes writing-rise {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  30% {
    opacity: 1;
    transform: translateY(-0.25rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .writing__dots i {
    animation: none;
  }
}
</style>
