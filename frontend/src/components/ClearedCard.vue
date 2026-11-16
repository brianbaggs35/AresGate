<script setup lang="ts">
import { Bot, Check, Undo2 } from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { ClearedItem, ClearedVerdict } from '@/api/aiCleared'
import { formatAgo } from '@/format'
import { VERDICT } from '@/verdicts'

/**
 * One thing the AI cleared, or suggests clearing: what it was, why the AI thinks it is nothing,
 * how sure it is and what it looked at, with the means to confirm it (which makes it the owner's
 * word), take it back (the incident is judged again and the AI is told not to clear that match
 * again) or say the other verdict. It is picked with its box to change many at once.
 */
const props = defineProps<{
  item: ClearedItem
  selected: boolean
  busy: boolean
}>()
const emit = defineEmits<{
  select: [picked: boolean]
  confirm: []
  change: [verdict: ClearedVerdict]
  'take-back': []
}>()

const waiting = computed(() => props.item.kind === 'waiting')
const look = computed(() => VERDICT[props.item.verdict])
/** The verdict the AI did not give, offered as the way to say the other thing. */
const other = computed<ClearedVerdict>(() =>
  props.item.verdict === 'not_suspicious' ? 'low_priority' : 'not_suspicious',
)
const by = computed(() => {
  const named = props.item.model ? ` (${props.item.model})` : ''
  return `${props.item.provider ?? 'The AI'}${named}, ${formatAgo(props.item.at)}`
})
const evidence = computed(
  () =>
    props.item.story !== null || props.item.checks.length > 0 || props.item.observations.length > 0,
)
const label = computed(() => props.item.incident?.title ?? 'An incident that is gone')
</script>

<template>
  <v-card
    class="cleared pa-4 pa-sm-5"
    :class="{ 'cleared--picked': selected }"
    :data-kind="item.kind"
    data-test="cleared-card"
  >
    <div class="cleared__chips">
      <input
        type="checkbox"
        class="cleared__box"
        :checked="selected"
        :aria-label="`Select ${label}`"
        data-test="cleared-pick"
        @change="emit('select', ($event.target as HTMLInputElement).checked)"
      />
      <v-chip
        :color="waiting ? 'warning' : 'info'"
        :prepend-icon="Bot"
        variant="tonal"
        data-test="cleared-state"
      >
        {{ waiting ? 'Waiting for you' : 'Cleared by the AI' }}
      </v-chip>
      <v-chip
        :color="look.color"
        :prepend-icon="look.icon"
        :title="look.meaning"
        variant="outlined"
        data-test="cleared-verdict"
      >
        {{ look.label }}
      </v-chip>
      <v-chip v-if="item.confidence !== null" variant="outlined" data-test="cleared-confidence">
        {{ item.confidence }}% sure
      </v-chip>
    </div>

    <h3 class="text-title-medium cleared__title">
      <RouterLink
        v-if="item.incident"
        :to="{ name: 'incident', params: { id: item.incident.id } }"
        data-test="cleared-link"
      >
        {{ item.incident.title }}
      </RouterLink>
      <span v-else data-test="cleared-gone">{{ label }}</span>
    </h3>
    <p v-if="item.incident" class="text-body-medium text-medium-emphasis" data-test="cleared-about">
      {{ item.incident.subject }} · {{ item.incident.severity }} · {{ item.incident.status }}
    </p>

    <p v-if="item.reason" class="text-body-large" data-test="cleared-reason">
      <span class="text-label-large">Why: </span>{{ item.reason }}
    </p>
    <p class="text-body-medium text-medium-emphasis" data-test="cleared-by">{{ by }}</p>

    <details v-if="evidence" class="cleared__evidence" data-test="cleared-evidence">
      <summary class="text-label-large">What the AI looked at</summary>
      <p v-if="item.story" class="text-body-medium" data-test="cleared-story">{{ item.story }}</p>
      <template v-if="item.observations.length">
        <h4 class="text-label-large">It saw</h4>
        <ul data-test="cleared-observations">
          <li v-for="line in item.observations" :key="line">{{ line }}</li>
        </ul>
      </template>
      <template v-if="item.checks.length">
        <h4 class="text-label-large">It checked</h4>
        <ul data-test="cleared-checks">
          <li v-for="line in item.checks" :key="line">{{ line }}</li>
        </ul>
      </template>
    </details>

    <div class="cleared__actions">
      <v-btn
        color="primary"
        variant="flat"
        :prepend-icon="Check"
        :disabled="busy"
        data-test="cleared-confirm"
        @click="emit('confirm')"
      >
        {{ waiting ? 'Clear it' : 'Confirm' }}
      </v-btn>
      <v-btn
        variant="tonal"
        :disabled="busy"
        :title="VERDICT[other].meaning"
        data-test="cleared-other"
        @click="emit('change', other)"
      >
        {{ waiting ? 'Clear as' : 'Change to' }} {{ VERDICT[other].label.toLowerCase() }}
      </v-btn>
      <v-btn
        variant="text"
        :prepend-icon="Undo2"
        :disabled="busy"
        data-test="cleared-take-back"
        @click="emit('take-back')"
      >
        {{ waiting ? 'Not nothing' : 'Take back' }}
      </v-btn>
    </div>
  </v-card>
</template>

<style scoped>
.cleared {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-inline-start: 4px solid transparent;
}

.cleared[data-kind='waiting'] {
  border-inline-start-color: rgb(var(--v-theme-warning));
}

.cleared[data-kind='cleared'] {
  border-inline-start-color: rgb(var(--v-theme-info));
}

.cleared--picked {
  background: rgba(var(--v-theme-primary), 0.06);
}

.cleared__chips,
.cleared__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.cleared__box {
  width: 1.25rem;
  height: 1.25rem;
  accent-color: rgb(var(--v-theme-primary));
}

.cleared__title,
.cleared p,
.cleared h4 {
  margin: 0;
}

.cleared__evidence {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.cleared__evidence summary {
  cursor: pointer;
}

.cleared__evidence ul {
  margin: 0;
  padding-inline-start: 1.25rem;
}
</style>
