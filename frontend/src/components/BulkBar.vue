<script setup lang="ts">
import { ChevronDown, X } from '@lucide/vue'
import { useDisplay } from 'vuetify'

import type { IncidentStatus } from '@/api/incidents'
import { VERDICTS, type VerdictKind } from '@/api/verdicts'
import { STATUS_STEPS, incidentsOf } from '@/bulk'
import { formatCount } from '@/format'
import { VERDICT } from '@/verdicts'

/**
 * The row above a list of incidents that changes many at once. With none picked it is the box that
 * picks every incident on the page, and says there is more to do; with some picked it says how many
 * and holds the changes: a status, or a verdict on what they are about. It stays under the top
 * bar as the list is scrolled, so it is there for the last incident of a long page too. Whoever
 * shows it decides what a change asks, and makes it.
 */
const props = defineProps<{
  /** How many are picked, and how many incidents match all told (more than the page shows). */
  count: number
  total: number
  /** How many are on the page, and whether every one of them is picked. */
  shown: number
  whole: boolean
  /** Every incident that matches is picked, not only the ones on the page. */
  everything: boolean
  busy?: boolean
}>()
const emit = defineEmits<{
  'toggle-page': []
  'pick-everything': []
  clear: []
  status: [IncidentStatus]
  verdict: [VerdictKind]
}>()

const { xs: phone } = useDisplay()

/** Offered once the page is picked and there is more that matches than the page shows. */
const offer = () => props.whole && !props.everything && props.total > props.shown
</script>

<template>
  <section
    class="bulk"
    :class="{ 'bulk--on': count > 0 }"
    aria-label="Change many incidents at once"
    data-test="bulk"
  >
    <label class="bulk__page">
      <input
        type="checkbox"
        class="bulk__box"
        :checked="whole"
        :indeterminate="count > 0 && !whole"
        aria-label="Select every incident on this page"
        data-test="bulk-page"
        @change="emit('toggle-page')"
      />
    </label>

    <p
      v-if="count === 0"
      class="bulk__hint text-body-medium text-medium-emphasis"
      data-test="bulk-hint"
    >
      Select incidents to change them together
    </p>
    <template v-else>
      <output class="bulk__count text-title-medium" data-test="bulk-count">
        {{ formatCount(count) }} selected
      </output>

      <fieldset class="bulk__actions">
        <legend class="bulk__legend">What to change</legend>
        <v-menu>
          <template #activator="{ props: menu }">
            <v-btn
              v-bind="menu"
              variant="tonal"
              density="comfortable"
              :stacked="phone"
              :append-icon="phone ? undefined : ChevronDown"
              :prepend-icon="phone ? ChevronDown : undefined"
              :disabled="busy"
              class="bulk__action"
              data-test="bulk-status"
            >
              Status
            </v-btn>
          </template>
          <v-list>
            <v-list-item
              v-for="step in STATUS_STEPS"
              :key="step.status"
              :prepend-icon="step.icon"
              :title="step.label"
              :data-test="`bulk-status-${step.status}`"
              @click="emit('status', step.status)"
            />
          </v-list>
        </v-menu>
        <v-btn
          v-for="kind in VERDICTS"
          :key="kind"
          variant="tonal"
          density="comfortable"
          :stacked="phone"
          :color="VERDICT[kind].color"
          :prepend-icon="VERDICT[kind].icon"
          :disabled="busy"
          class="bulk__action"
          :data-test="`bulk-${kind}`"
          @click="emit('verdict', kind)"
        >
          {{ VERDICT[kind].label }}
        </v-btn>
      </fieldset>

      <v-btn
        variant="text"
        density="comfortable"
        :prepend-icon="X"
        class="bulk__clear"
        data-test="bulk-clear"
        @click="emit('clear')"
      >
        Clear
      </v-btn>
    </template>

    <p v-if="offer()" class="bulk__more text-body-medium" data-test="bulk-offer">
      All {{ formatCount(shown) }} on this page are selected.
      <v-btn
        variant="text"
        density="comfortable"
        data-test="bulk-everything"
        @click="emit('pick-everything')"
      >
        Select all {{ incidentsOf(total) }} that match
      </v-btn>
    </p>
    <p v-else-if="everything" class="bulk__more text-body-medium" data-test="bulk-all">
      All {{ incidentsOf(total) }} that match are selected.
    </p>
  </section>
</template>

<style scoped>
.bulk {
  position: sticky;
  top: calc(var(--v-layout-top, 0px) + 0.5rem);
  z-index: 5;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.25rem 0.75rem;
  min-height: 52px;
  padding: 0.25rem 0.75rem 0.25rem 0.5rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface));
}

.bulk--on {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
}

.bulk__page {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  cursor: pointer;
}

.bulk__box {
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
  cursor: pointer;
}

.bulk__box:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}

.bulk__hint,
.bulk__count,
.bulk__more {
  margin: 0;
}

.bulk__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.bulk__hint {
  grid-column: 2 / -1;
}

.bulk__more {
  grid-column: 1 / -1;
  padding-inline-start: 0.5rem;
}

/* On a phone the changes take a row of their own, each a button with its icon over its name. */
.bulk__actions {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.bulk__clear,
.bulk__more :deep(.v-btn) {
  min-height: 2.75rem;
}

/* Beside the count, so that on a phone the bar is two rows, not three. */
.bulk__clear {
  grid-column: 3;
  grid-row: 1;
}

.bulk__action {
  min-width: 0;
  height: auto;
  min-height: 2.75rem;
  padding-block: 0.5rem;
}

.bulk__action :deep(.v-btn__content) {
  white-space: normal;
  line-height: 1.25;
  text-align: center;
}

@media (min-width: 720px) {
  .bulk {
    grid-template-columns: auto minmax(0, 1fr) auto auto;
  }

  .bulk__actions {
    grid-column: 3;
    grid-row: 1;
    display: flex;
  }

  .bulk__clear {
    grid-column: 4;
    grid-row: 1;
  }
}
</style>
