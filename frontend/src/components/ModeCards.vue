<script setup lang="ts">
import { Bell, SlidersHorizontal, Siren } from '@lucide/vue'
import { useId } from 'vue'
import type { IconProps } from 'vuetify'

type Icon = NonNullable<IconProps['icon']>

/** What a channel is for: `threats`, only the real attacks going on now; `serious`, everything
 * medium or worse that AresGate is sure of; `custom`, whatever the owner chooses. */
export type Purpose = 'threats' | 'serious' | 'custom'

const PURPOSES: readonly {
  key: Purpose
  title: string
  text: string
  icon: Icon
  recommended?: boolean
}[] = [
  {
    key: 'threats',
    title: 'Real attacks only',
    text: 'A message means something real is happening: an attack going on now, with the reason. Scans and noise stay on the Threats page.',
    icon: Siren,
    recommended: true,
  },
  {
    key: 'serious',
    title: 'Everything serious',
    text: 'Medium severity or worse, when AresGate is at least 65% sure. More messages, including scans that are only looking around.',
    icon: Bell,
  },
  {
    key: 'custom',
    title: 'Custom',
    text: 'Choose how serious, how sure, which programs and which kinds of activity.',
    icon: SlidersHorizontal,
  },
]

/**
 * Three big cards, of which one is chosen, for what a Discord channel is for. A choice here sets
 * the rules under it at once; Custom is the way to the rest of them. They are real radio buttons
 * (so the arrow keys move between them and a screen reader says which is chosen), drawn as cards.
 */
const model = defineModel<Purpose>({ required: true })

const name = useId()
</script>

<template>
  <fieldset class="purposes" data-test="purposes">
    <legend class="text-title-medium purposes__legend">What is this channel for?</legend>
    <div class="purposes__cards">
      <label
        v-for="item in PURPOSES"
        :key="item.key"
        :class="['purpose', { 'purpose--chosen': model === item.key }]"
        :data-test="`purpose-${item.key}`"
      >
        <input v-model="model" type="radio" :name="name" :value="item.key" class="purpose__input" />
        <v-icon :icon="item.icon" size="24" class="purpose__icon" aria-hidden="true" />
        <span class="purpose__title text-title-small">
          {{ item.title }}
          <v-chip
            v-if="item.recommended"
            size="x-small"
            color="primary"
            variant="tonal"
            class="purpose__chip"
            >Recommended</v-chip
          >
        </span>
        <span class="purpose__text text-body-medium">{{ item.text }}</span>
      </label>
    </div>
  </fieldset>
</template>

<style scoped>
.purposes {
  min-width: 0;
  padding: 0;
  border: 0;
}

.purposes__legend {
  margin-bottom: 0.75rem;
  padding: 0;
}

.purposes__cards {
  display: grid;
  gap: 0.75rem;
}

.purpose {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 0.75rem;
  row-gap: 0.25rem;
  padding: 0.875rem 1rem;
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background-color 0.15s;
}

.purpose:hover {
  border-color: rgb(var(--v-theme-primary));
}

.purpose--chosen {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
}

.purpose:focus-within {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* The radio is there for the keyboard and screen readers; the card is what is seen. */
.purpose__input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.purpose__icon {
  grid-row: 1 / span 2;
  align-self: start;
  margin-top: 0.125rem;
  color: rgb(var(--v-theme-primary));
}

.purpose__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.purpose__text {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

@media (prefers-reduced-motion: reduce) {
  .purpose {
    transition: none;
  }
}
</style>
