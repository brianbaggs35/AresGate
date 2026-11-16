<script setup lang="ts">
import { computed } from 'vue'

import type { HourState } from '@/api/trends'
import { HOUR_STATES, stripSummary } from '@/trends'

/**
 * How the last hours of one integration went, a cell for each, oldest first: working, a problem,
 * or no calls. A cell is never only a color: a problem is tall and striped, working is solid, and
 * no calls is an outline. The words under it say the same, so it reads as a sentence too.
 */
const props = defineProps<{ states: readonly HourState[]; name: string }>()

const summary = computed(() => stripSummary(props.states))
</script>

<template>
  <div class="strip" data-test="health-strip">
    <div class="strip__cells" role="img" :aria-label="`${name}. ${summary}`">
      <span
        v-for="(state, index) in states"
        :key="index"
        class="strip__cell"
        :class="`strip__cell--${state}`"
        :title="HOUR_STATES[state]"
        :data-state="state"
        data-test="health-cell"
      />
    </div>
    <p class="text-body-small text-medium-emphasis strip__words" data-test="health-summary">
      {{ summary }}
    </p>
  </div>
</template>

<style scoped>
.strip {
  margin-block-start: 0.5rem;
}

.strip__cells {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  block-size: 20px;
}

.strip__cell {
  display: block;
  flex: 1 1 0;
  min-inline-size: 3px;
  max-inline-size: 14px;
  border-radius: 2px;
}

.strip__cell--ok {
  block-size: 14px;
  background: rgb(var(--v-theme-success));
}

.strip__cell--problem {
  block-size: 20px;
  background: repeating-linear-gradient(
    135deg,
    rgb(var(--v-theme-error)) 0 3px,
    rgb(var(--v-theme-surface)) 3px 5px
  );
  outline: 1px solid rgb(var(--v-theme-error));
}

.strip__cell--none {
  block-size: 6px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.6);
}

.strip__words {
  margin: 0.25rem 0 0;
}

@media (forced-colors: active) {
  .strip__cell--ok {
    background: Highlight;
  }

  .strip__cell--problem {
    background: Mark;
  }
}
</style>
