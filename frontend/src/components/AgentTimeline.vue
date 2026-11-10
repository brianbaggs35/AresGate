<script setup lang="ts">
import type { Step } from '@/api/agents'
import { linesOf, nodeInfo } from '@/agents'
import { formatClock } from '@/format'

/**
 * What a run did, step by step, as it did it. A step that looked at something can be opened to
 * read what it saw, in the words the owner reads, not what a provider was sent (which the AI
 * usage page has). While the run is going, the last line says it is still at it.
 */
defineProps<{
  steps: readonly Step[]
  live: boolean
}>()

const summaryOf = (step: Step): string => {
  const summary = step.detail.summary
  return typeof summary === 'string' ? summary : ''
}
</script>

<template>
  <div class="timeline" data-test="agent-timeline">
    <ol v-if="steps.length || live" class="timeline__steps">
      <li v-for="step in steps" :key="step.seq" class="step" data-test="timeline-step">
        <span class="step__marker" :class="`step__marker--${step.node}`" aria-hidden="true">
          <v-icon :icon="nodeInfo(step.node).icon" size="16" />
        </span>
        <div class="step__body">
          <div class="step__head">
            <span class="text-body-large" data-test="step-title">{{ step.title }}</span>
            <span class="text-label-small text-medium-emphasis step__when">
              {{ nodeInfo(step.node).label }} ·
              <time :datetime="step.at">{{ formatClock(step.at) }}</time>
            </span>
          </div>
          <p
            v-if="summaryOf(step)"
            class="text-body-medium text-medium-emphasis step__summary"
            data-test="step-summary"
          >
            {{ summaryOf(step) }}
          </p>
          <details v-if="linesOf(step).length" class="step__more" data-test="step-more">
            <summary class="text-label-large">What it saw ({{ linesOf(step).length }})</summary>
            <ul class="step__lines text-body-medium">
              <li v-for="(line, at) in linesOf(step)" :key="at" data-test="step-line">
                {{ line }}
              </li>
            </ul>
          </details>
        </div>
      </li>
      <li v-if="live" class="step step--live" data-test="timeline-working">
        <span class="step__marker step__marker--live" aria-hidden="true">
          <span class="step__pulse" />
        </span>
        <span class="text-body-large text-medium-emphasis">Working on the next step…</span>
      </li>
    </ol>
    <p v-else class="text-body-large text-medium-emphasis" data-test="timeline-empty">
      No steps were kept for this run.
    </p>
  </div>
</template>

<style scoped>
.timeline__steps {
  position: relative;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  position: relative;
  display: flex;
  gap: 0.875rem;
  padding-bottom: 1.25rem;
}

.step:last-child {
  padding-bottom: 0;
}

.step:not(:last-child)::before {
  position: absolute;
  top: 1.75rem;
  bottom: 0;
  left: 0.875rem;
  width: 2px;
  background: rgba(var(--v-theme-on-surface), 0.12);
  content: '';
}

.step__marker {
  position: relative;
  z-index: 1;
  display: grid;
  flex: none;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
}

.step__marker--report {
  background: rgba(var(--v-theme-success), 0.16);
  color: rgb(var(--v-theme-success));
}

.step__marker--think {
  background: rgba(var(--v-theme-secondary), 0.16);
  color: rgb(var(--v-theme-secondary));
}

.step__pulse {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background: rgb(var(--v-theme-primary));
  animation: blink 1.2s ease-in-out infinite;
}

.step__body {
  flex: 1;
  min-width: 0;
}

.step__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.step__summary {
  margin: 0.25rem 0 0;
}

.step__more {
  margin-top: 0.5rem;
}

.step__more summary {
  cursor: pointer;
  color: rgb(var(--v-theme-primary));
}

.step__lines {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin: 0.5rem 0 0;
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-on-surface), 0.05);
  list-style: none;
  overflow-wrap: anywhere;
}

.step--live {
  align-items: center;
}

@keyframes blink {
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .step__pulse {
    animation: none;
  }
}
</style>
