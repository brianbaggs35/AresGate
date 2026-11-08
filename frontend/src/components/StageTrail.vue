<script setup lang="ts">
import { computed } from 'vue'

import type { Stage } from '@/api/incidents'
import { STAGE, STAGES_IN_ORDER } from '@/threats'

/**
 * How far an attack got along the way an attack goes: looking around, trying to get in, a sign
 * that it worked. The steps it reached are filled in and named; the others are faint, so a scan
 * that never went further reads as one step of three. It is a list of what happened, and says in
 * words which steps those were.
 */
const props = defineProps<{ stages: readonly Stage[] }>()

const reached = computed(() => new Set(props.stages))
const spoken = computed(() =>
  props.stages.length === 0
    ? 'No sign that it went further than being seen.'
    : `Got as far as: ${props.stages.map((stage) => STAGE[stage].label.toLowerCase()).join(', ')}.`,
)
</script>

<template>
  <div class="trail" data-test="stage-trail">
    <ol class="trail__steps" aria-label="How far it got">
      <li
        v-for="stage in STAGES_IN_ORDER"
        :key="stage"
        class="trail__step"
        :class="{ 'trail__step--reached': reached.has(stage) }"
        :title="STAGE[stage].meaning"
        :data-test="`stage-${stage}`"
        :data-reached="reached.has(stage)"
      >
        <v-icon :icon="STAGE[stage].icon" size="18" aria-hidden="true" />
        <span class="text-label-large">{{ STAGE[stage].label }}</span>
      </li>
    </ol>
    <p class="sr-only" data-test="stage-spoken">{{ spoken }}</p>
  </div>
</template>

<style scoped>
.trail__steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.trail__step {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border: thin dashed rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 999px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.trail__step--reached {
  border-style: solid;
  border-color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.1);
  color: rgb(var(--v-theme-on-surface));
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
