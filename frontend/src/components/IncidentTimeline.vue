<script setup lang="ts">
import { Ban } from '@lucide/vue'
import { computed, ref } from 'vue'

import type { Signal } from '@/api/incidents'
import SeverityChip from '@/components/SeverityChip.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { formatCount } from '@/format'
import { flowOf } from '@/incidents'
import { SEVERITY } from '@/severity'
import { isMuting } from '@/verdicts'

/**
 * What happened, oldest first, whichever program saw it: when, who reported it, how serious they
 * thought it was, what they said and the traffic it was about. A line down the side joins them.
 */
const props = defineProps<{
  signals: readonly Signal[]
  /** How many signals the incident has, which is more than are listed once it has a great many. */
  total: number
}>()

/** How many signals are listed before the rest are asked for: an incident can have a thousand. */
const PAGE = 25

const day = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const clock = new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' })

const shown = ref(PAGE)

/** The signals with the day they happened on, said only where it changes from the one before. */
const rows = computed(() =>
  props.signals.slice(0, shown.value).map((signal, index) => {
    const when = new Date(signal.occurred_at)
    const before = props.signals[index - 1]
    const newDay = !before || new Date(before.occurred_at).toDateString() !== when.toDateString()
    return {
      signal,
      day: newDay ? day.format(when) : null,
      time: clock.format(when),
      flow: flowOf(signal),
      // A ban is the one kind that isn't an alert: say so.
      ban: signal.kind === 'decision',
      // One the owner called not suspicious or low priority is listed, but doesn't count.
      quiet: signal.verdict !== null && isMuting(signal.verdict),
      // What the program called it, when that isn't just what it said.
      name: signal.signature && signal.signature !== signal.summary ? signal.signature : null,
    }
  }),
)
const hidden = computed(() => Math.max(0, props.signals.length - shown.value))
const unlisted = computed(() => props.total - props.signals.length)
</script>

<template>
  <div data-test="timeline">
    <ol class="timeline">
      <li
        v-for="(row, index) in rows"
        :key="index"
        class="timeline__item"
        :class="{ 'timeline__item--quiet': row.quiet }"
        :style="{
          '--signal-color': `rgb(var(--v-theme-${SEVERITY[row.signal.severity].color}))`,
        }"
        data-test="signal"
      >
        <p v-if="row.day" class="timeline__day text-label-large" data-test="signal-day">
          {{ row.day }}
        </p>
        <div class="timeline__row">
          <time
            class="timeline__time text-body-medium text-medium-emphasis tabular-nums"
            :datetime="row.signal.occurred_at"
            data-test="signal-time"
            >{{ row.time }}</time
          >
          <span class="timeline__dot" aria-hidden="true" />
          <div class="timeline__body">
            <div class="timeline__chips">
              <v-chip size="small" variant="outlined" data-test="signal-source">{{
                row.signal.source_name
              }}</v-chip>
              <SeverityChip :severity="row.signal.severity" size="small" />
              <VerdictChip v-if="row.signal.verdict" :verdict="row.signal.verdict" size="small" />
              <v-chip
                v-if="row.ban"
                size="small"
                variant="tonal"
                :prepend-icon="Ban"
                data-test="signal-ban"
                >Ban</v-chip
              >
            </div>
            <p class="text-body-large" data-test="signal-summary">{{ row.signal.summary }}</p>
            <p
              v-if="row.name"
              class="text-body-medium text-medium-emphasis"
              data-test="signal-name"
            >
              {{ row.name }}
            </p>
            <p v-if="row.flow" class="timeline__flow text-body-medium" data-test="signal-flow">
              {{ row.flow }}
            </p>
          </div>
        </div>
      </li>
    </ol>
    <div v-if="hidden > 0" class="timeline__more">
      <v-btn variant="outlined" data-test="timeline-show-more" @click="shown += PAGE">
        Show {{ formatCount(Math.min(hidden, PAGE)) }} more
      </v-btn>
    </div>
    <p v-if="unlisted > 0" class="text-body-medium text-medium-emphasis" data-test="timeline-more">
      Only the first {{ formatCount(signals.length) }} of its {{ formatCount(total) }} signals are
      kept. The rest are counted, but not listed.
    </p>
  </div>
</template>

<style scoped>
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline__day {
  margin: 1rem 0 0.25rem;
  padding-inline-start: 0.25rem;
  color: rgb(var(--v-theme-primary));
}

.timeline__item:first-child .timeline__day {
  margin-top: 0;
}

.timeline__row {
  display: grid;
  grid-template-columns: 5.5rem 0.75rem minmax(0, 1fr);
  gap: 0 0.75rem;
  position: relative;
}

/* The line runs through the dots of all the signals, from one to the next. */
.timeline__row::before {
  content: '';
  position: absolute;
  inset-block: 0;
  inset-inline-start: calc(5.5rem + 0.75rem + 0.375rem - 1px);
  width: 2px;
  background: rgb(var(--v-border-color), var(--v-border-opacity));
}

.timeline__dot {
  position: relative;
  z-index: 1;
  width: 0.75rem;
  height: 0.75rem;
  margin-top: 0.4rem;
  border-radius: 50%;
  background: var(--signal-color);
  box-shadow: 0 0 0 3px rgb(var(--v-theme-surface));
}

.timeline__time {
  padding-top: 0.25rem;
  text-align: end;
}

.timeline__body {
  min-width: 0;
  padding-bottom: 1.25rem;
}

.timeline__body p {
  margin: 0.25rem 0 0;
  overflow-wrap: anywhere;
}

.timeline__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.timeline__more {
  display: flex;
  justify-content: center;
  margin: 0.5rem 0 1rem;
}

/* A signal that doesn't count is drawn as a hollow dot, so it reads as less than the rest in
 * words and in shape, not only in color. */
.timeline__item--quiet .timeline__dot {
  background: rgb(var(--v-theme-surface));
  border: 2px solid rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.timeline__flow {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* On a phone the time sits above the words rather than taking a column from them. */
@media (max-width: 599px) {
  .timeline__row {
    grid-template-columns: 0.75rem minmax(0, 1fr);
  }

  .timeline__row::before {
    inset-inline-start: calc(0.375rem - 1px);
  }

  .timeline__time {
    grid-column: 2;
    grid-row: 1;
    padding-top: 0;
    text-align: start;
  }

  .timeline__dot {
    grid-column: 1;
    grid-row: 1 / span 2;
  }

  .timeline__body {
    grid-column: 2;
    grid-row: 2;
  }
}
</style>
