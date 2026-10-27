<script setup lang="ts">
import { computed } from 'vue'

import type { Facets } from '@/api/incidents'
import { hasTerm } from '@/search'
import { SEVERITIES, SEVERITY, type Severity } from '@/severity'
import { formatCount } from '@/format'

/**
 * What the incidents found are made of: how many at each severity, and how many each integration
 * reported part of. Each is a button that adds that term to the search, or takes it out if it is
 * there, so the search can be narrowed without typing. A choice nothing is left to match is not
 * offered, unless it is the one that made the list so short.
 */
const props = defineProps<{
  facets: Facets
  /** The search that is applied, to tell which choices are on. */
  search: string
}>()
const emit = defineEmits<{ toggle: [term: string] }>()

interface Choice {
  term: string
  label: string
  count: number
  on: boolean
  /** A theme color, for the severities. */
  color?: string
  icon?: (typeof SEVERITY)[Severity]['icon']
}

const severities = computed<Choice[]>(() =>
  SEVERITIES.slice()
    .reverse()
    .map((level) => {
      const term = `severity:${level}`
      const { label, color, icon } = SEVERITY[level]
      return {
        term,
        label,
        count: props.facets.severity[level],
        on: hasTerm(props.search, term),
        color,
        icon,
      }
    })
    .filter(({ count, on }) => count > 0 || on),
)

const sources = computed<Choice[]>(() =>
  props.facets.sources.map(({ key, name, count }) => {
    const term = `source:${key}`
    return { term, label: name, count, on: hasTerm(props.search, term) }
  }),
)

const groups = computed(() =>
  [
    { name: 'Severity', choices: severities.value },
    { name: 'Reported by', choices: sources.value },
  ].filter(({ choices }) => choices.length > 0),
)
</script>

<template>
  <div v-if="groups.length" class="facets" data-test="facets">
    <div
      v-for="group in groups"
      :key="group.name"
      class="facets__group"
      role="group"
      :aria-label="group.name"
    >
      <span class="facets__name text-label-large text-medium-emphasis" aria-hidden="true">{{
        group.name
      }}</span>
      <button
        v-for="choice in group.choices"
        :key="choice.term"
        type="button"
        class="facet"
        :class="{ 'facet--on': choice.on }"
        :style="choice.color ? { '--facet': `var(--v-theme-${choice.color})` } : undefined"
        :aria-pressed="choice.on"
        :data-test="`facet-${choice.term}`"
        @click="emit('toggle', choice.term)"
      >
        <v-icon
          v-if="choice.icon"
          :icon="choice.icon"
          size="16"
          class="facet__icon"
          aria-hidden="true"
        />
        <span>{{ choice.label }}</span>
        <span class="facet__count tabular-nums">{{ formatCount(choice.count) }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.facets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.5rem;
}

.facets__group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.facets__name {
  flex: none;
}

.facet {
  --facet: var(--v-theme-primary);

  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.375rem;
  min-height: 32px;
  padding: 0 0.75rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 999px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
  cursor: pointer;
}

.facet:hover {
  background: rgba(var(--facet), 0.08);
}

.facet:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.facet--on {
  border-color: rgb(var(--facet));
  background: rgba(var(--facet), 0.16);
}

.facet__icon {
  color: rgb(var(--facet));
}

.facet__count {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

/* Two rows of choices don't fit across a phone, so each scrolls sideways under a fade. */
@media (max-width: 599.98px) {
  .facets {
    flex-direction: column;
    gap: 0.5rem;
  }

  /* `contain` keeps the width of the choices from widening the page: they scroll, not push. */
  .facets__group {
    contain: inline-size;
    margin-inline: -16px;
    padding-inline: 16px;
    overflow-x: auto;
    scrollbar-width: none;
    mask-image: linear-gradient(to right, #000 calc(100% - 2rem), transparent);
  }

  .facets__group > :last-child {
    margin-inline-end: 1.5rem;
  }

  .facet {
    min-height: 44px;
  }
}
</style>
