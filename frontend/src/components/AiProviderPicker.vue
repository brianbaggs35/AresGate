<script setup lang="ts">
import { Check } from '@lucide/vue'

import type { AiProvider } from '@/api/ai'

/**
 * Where the AI should run, one choice of the providers as a set of cards: the one chosen has its
 * settings under the cards. Which of them AresGate is asking is said on its card. They are radio
 * buttons underneath, so the arrow keys move between them and a screen reader hears one group.
 */
defineProps<{
  providers: readonly AiProvider[]
  /** The provider AresGate asks, while AI is on. */
  asking: string | null
}>()
const chosen = defineModel<string | null>({ required: true })
</script>

<template>
  <fieldset class="picker" data-test="provider-picker">
    <legend class="picker__legend text-title-medium">Where should the AI run?</legend>
    <div class="picker__grid">
      <label
        v-for="provider in providers"
        :key="provider.key"
        class="picker__option"
        :class="{ 'picker__option--chosen': chosen === provider.key }"
        :data-test="`pick-${provider.key}`"
      >
        <input
          v-model="chosen"
          type="radio"
          name="ai-provider"
          class="picker__input"
          :value="provider.key"
        />
        <span class="picker__mark" aria-hidden="true">
          <Check v-if="chosen === provider.key" :size="16" :stroke-width="3" />
        </span>
        <span class="picker__text">
          <span class="picker__name text-title-medium">{{ provider.label }}</span>
          <span class="picker__summary text-body-medium text-medium-emphasis">{{
            provider.summary
          }}</span>
          <v-chip
            v-if="asking === provider.key"
            size="small"
            color="success"
            variant="tonal"
            class="picker__asking"
            data-test="pick-asking"
          >
            In use
          </v-chip>
        </span>
      </label>
    </div>
  </fieldset>
</template>

<style scoped>
.picker {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.picker__legend {
  padding: 0;
  margin-bottom: 0.75rem;
}

.picker__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
}

.picker__option {
  position: relative;
  display: grid;
  grid-template-columns: 1.5rem minmax(0, 1fr);
  align-items: start;
  gap: 0 0.875rem;
  padding: 1rem;
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  cursor: pointer;
  transition:
    border-color 120ms,
    background-color 120ms;
}

.picker__option:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.picker__option--chosen {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

/* The real radio button covers the card, so a click anywhere chooses it and it can be focused. */
.picker__input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.picker__option:has(.picker__input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.picker__mark {
  display: grid;
  place-items: center;
  width: 1.5rem;
  height: 1.5rem;
  margin-top: 0.1rem;
  border: 2px solid rgba(var(--v-theme-on-surface), 0.6);
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary));
}

.picker__option--chosen .picker__mark {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary));
}

.picker__text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.picker__asking {
  align-self: flex-start;
  margin-top: 0.25rem;
}

@media (min-width: 720px) {
  .picker__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
