<script setup lang="ts">
import { computed } from 'vue'

import { share } from '@/evidence'
import { formatCount } from '@/format'

/**
 * A short list of things and how many alerts each was said of, as bars drawn against the
 * commonest, so which is which is seen before it is read. The number is always written too.
 */
const props = defineProps<{
  items: readonly { label: string; hint?: string; count: number }[]
}>()

const most = computed(() => Math.max(0, ...props.items.map(({ count }) => count)))
</script>

<template>
  <ul class="bars" data-test="counted-bars">
    <li v-for="item in items" :key="`${item.label}-${item.hint ?? ''}`" class="bars__item">
      <div class="bars__text">
        <span class="text-body-large bars__label" data-test="bar-label">{{ item.label }}</span>
        <span v-if="item.hint" class="text-body-medium text-medium-emphasis">{{ item.hint }}</span>
      </div>
      <span class="text-body-large tabular-nums" data-test="bar-count">
        {{ formatCount(item.count) }}
      </span>
      <span class="bars__track" aria-hidden="true">
        <span class="bars__fill" :style="{ width: `${share(item.count, most).toString()}%` }" />
      </span>
    </li>
  </ul>
</template>

<style scoped>
.bars {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.bars__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.25rem 0.75rem;
  align-items: baseline;
}

.bars__text {
  display: flex;
  flex-wrap: wrap;
  gap: 0 0.5rem;
  min-width: 0;
}

.bars__label {
  overflow-wrap: anywhere;
}

.bars__track {
  grid-column: 1 / -1;
  height: 0.375rem;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.bars__fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
}
</style>
