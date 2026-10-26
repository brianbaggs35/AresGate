<script setup lang="ts">
import { CircleCheck, Eye, Plug, Siren } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import type { Posture, PostureState } from '@/dashboard'

/**
 * The first thing on the dashboard, in a sentence: whether anything needs attention. It is
 * never only a color, since each state has its own icon and its own words. Screen readers hear
 * a change politely, because the page asks again every half minute.
 */
defineProps<{
  posture: Posture
  /** Where to go from here, for the states that have somewhere to go. */
  action?: { label: string; to: RouteLocationRaw }
}>()

const LOOKS: Readonly<
  Record<PostureState, { color: string; icon: NonNullable<IconProps['icon']> }>
> = {
  attention: { color: 'error', icon: Siren },
  watch: { color: 'warning', icon: Eye },
  calm: { color: 'success', icon: CircleCheck },
  setup: { color: 'info', icon: Plug },
}
</script>

<template>
  <section
    class="security-banner"
    :style="{ '--banner': `var(--v-theme-${LOOKS[posture.state].color})` }"
    :data-state="posture.state"
    data-test="posture"
  >
    <v-icon
      :icon="LOOKS[posture.state].icon"
      :color="LOOKS[posture.state].color"
      size="32"
      aria-hidden="true"
    />
    <output class="security-banner__text">
      <span class="d-block text-title-large" data-test="posture-title">{{ posture.title }}</span>
      <span class="d-block text-body-large" data-test="posture-detail">{{ posture.detail }}</span>
    </output>
    <v-btn
      v-if="action"
      class="security-banner__action"
      variant="tonal"
      :color="LOOKS[posture.state].color"
      :to="action.to"
      data-test="posture-action"
    >
      {{ action.label }}
    </v-btn>
  </section>
</template>

<style scoped>
/* The icon beside the words, and the button under them: on a phone it lines up with the words
 * rather than floating at the left edge. */
.security-banner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 0.75rem 1rem;
  padding: 1rem 1.25rem;
  border-radius: 12px;
  border-inline-start: 4px solid rgb(var(--banner));
  background: rgba(var(--banner), 0.12);
}

.security-banner__text {
  display: block;
  min-width: 0;
}

.security-banner__action {
  grid-column: 2;
  justify-self: start;
}

.security-banner p {
  margin: 0;
}

/* With room, the button sits at the end of the row. */
@container (min-width: 640px) {
  .security-banner {
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
  }

  .security-banner__action {
    grid-column: 3;
  }
}
</style>
