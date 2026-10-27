<script setup lang="ts">
import type { LogEvent } from '@/api/logs'
import { formatAgo, formatTimestamp } from '@/format'
import { routeOf } from '@/logs'
import { SEVERITY } from '@/severity'

/**
 * The events as cards, the newest first, for a screen too narrow to read a table across: what
 * it says, how serious it is, who reported it and when, and where it went. A card opens the
 * event in the drawer.
 */
defineProps<{
  events: readonly LogEvent[]
  /** The cursor of the event that is open, if one is. */
  selected: string | null
  /** The moment "how long ago" is counted from. */
  now: number
}>()
const emit = defineEmits<{ open: [event: LogEvent] }>()

const accent = (event: LogEvent) => `rgb(var(--v-theme-${SEVERITY[event.severity].color}))`
</script>

<template>
  <ul class="log-cards" data-test="log-cards">
    <li v-for="event in events" :key="event.id">
      <button
        type="button"
        class="log-card"
        :class="{ 'log-card--on': event.cursor === selected }"
        :style="{ '--accent': accent(event) }"
        :aria-current="event.cursor === selected ? 'true' : undefined"
        data-test="log-card"
        @click="emit('open', event)"
      >
        <span class="log-card__top text-body-medium">
          <span class="log-card__severity">
            <v-icon :icon="SEVERITY[event.severity].icon" size="16" aria-hidden="true" />
            {{ SEVERITY[event.severity].label }}
          </span>
          <span class="text-medium-emphasis" data-test="log-card-source"
            >{{ event.source_name }} · {{ event.kind }}</span
          >
          <time
            :datetime="event.at"
            :title="formatTimestamp(event.at)"
            class="log-card__when text-medium-emphasis"
            >{{ formatAgo(event.at, now) }}</time
          >
        </span>
        <span class="log-card__summary text-body-large">{{ event.summary }}</span>
        <span
          v-if="routeOf(event)"
          class="log-card__route text-body-medium text-medium-emphasis"
          data-test="log-card-route"
          >{{ routeOf(event) }}</span
        >
      </button>
    </li>
  </ul>
</template>

<style scoped>
.log-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr));
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.log-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  min-height: 44px;
  padding: 0.75rem 1rem 0.75rem 1.25rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  text-align: start;
  cursor: pointer;
}

/* The bar on the left says how serious it is at a glance, and the word says it too. */
.log-card::before {
  content: '';
  position: absolute;
  inset-block: 0.5rem;
  inset-inline-start: 0.375rem;
  width: 3px;
  border-radius: 3px;
  background: var(--accent);
}

.log-card:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.log-card:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.log-card--on {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.log-card__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.log-card__severity {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-weight: 600;
}

.log-card__severity .v-icon {
  color: var(--accent);
}

.log-card__when {
  margin-inline-start: auto;
}

.log-card__summary {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.log-card__route {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  overflow-wrap: anywhere;
}
</style>
