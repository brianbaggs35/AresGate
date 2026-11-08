<script setup lang="ts">
import { computed } from 'vue'

import type { Funnel } from '@/api/threats'
import { formatCount } from '@/format'
import { funnelSentence, funnelSteps, LANE } from '@/threats'

/**
 * From what the programs reported to what needs a person: every report, each alert once, the
 * incidents they come to, and where those stand. The bars go by the number of digits, because
 * seventy thousand reports and four threats cannot share a scale, and every one carries its
 * number, so no figure is read off a bar.
 */
const props = defineProps<{
  funnel: Funnel
  /** The window in words that fit "in ...": "the last 24 hours". */
  window: string
}>()

const steps = computed(() => funnelSteps(props.funnel))
const sentence = computed(() => funnelSentence(props.funnel, props.window))
const color = (key: string) =>
  key === 'threat' || key === 'suspect' || key === 'background'
    ? `rgb(var(--v-theme-${LANE[key].color}))`
    : 'rgb(var(--v-theme-primary))'
</script>

<template>
  <div data-test="funnel">
    <p class="funnel__sentence text-title-medium" data-test="funnel-sentence">{{ sentence }}</p>
    <ol class="funnel">
      <li
        v-for="step in steps"
        :key="step.key"
        class="funnel__step"
        :data-test="`funnel-${step.key}`"
      >
        <div class="funnel__head">
          <span class="text-label-large">{{ step.label }}</span>
          <b class="text-title-large tabular-nums" data-test="funnel-count">{{
            formatCount(step.count)
          }}</b>
        </div>
        <div class="funnel__track" aria-hidden="true">
          <div
            class="funnel__bar"
            :style="{ width: `${step.width}%`, background: color(step.key) }"
          />
        </div>
        <p class="funnel__detail text-body-medium text-medium-emphasis">{{ step.detail }}</p>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.funnel__sentence {
  margin: 0 0 1rem;
}

.funnel {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem 2rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (min-width: 720px) {
  .funnel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.funnel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}

.funnel__track {
  height: 8px;
  margin-block: 0.25rem 0.5rem;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  overflow: hidden;
}

.funnel__bar {
  height: 100%;
  border-radius: 999px;
  transition: width 420ms cubic-bezier(0.2, 0.7, 0.2, 1);
}

.funnel__detail {
  margin: 0;
}

@media (prefers-reduced-motion: reduce) {
  .funnel__bar {
    transition: none;
  }
}
</style>
