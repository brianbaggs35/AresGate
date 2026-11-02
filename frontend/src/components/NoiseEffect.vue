<script setup lang="ts">
import { computed } from 'vue'

import type { Preview } from '@/api/noise'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount } from '@/format'
import { changeSentence, rowsOf } from '@/noiseFilters'

/**
 * What saving would change: the incidents that need you and the alerts that are set aside, now and
 * with the settings as they stand on the page. The server works it out by judging the incidents
 * that are going on as the settings would, and puts them back, so the figures are what saving does.
 */
const props = defineProps<{
  /** Null while it is being worked out, or when nothing is different from what is kept. */
  preview: Preview | null
  /** Whether the page differs from what is kept. */
  changed: boolean
  loading: boolean
  saving: boolean
  failure: string | null
  /** A word that the last save went through. */
  saved: boolean
}>()
defineEmits<{ save: []; discard: [] }>()

const rows = computed(() => (props.preview ? rowsOf(props.preview) : []))
const sentence = computed(() => (props.preview ? changeSentence(props.preview) : ''))
</script>

<template>
  <SectionCard
    title="What this changes"
    description="Worked out on the incidents that are going on now. Saving judges them again at once; incidents that are over keep what was said at the time."
    data-test="effect-card"
  >
    <v-progress-linear v-if="loading" indeterminate class="mb-4" aria-label="Working it out" />
    <p
      v-if="sentence"
      class="effect__sentence text-title-medium"
      role="status"
      data-test="effect-sentence"
    >
      {{ sentence }}
    </p>
    <table v-if="rows.length" class="effect__table" data-test="effect-table">
      <thead>
        <tr>
          <th scope="col"><span class="sr-only">What</span></th>
          <th scope="col" class="text-label-large">Now</th>
          <th scope="col" class="text-label-large">With these settings</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.key" :data-test="`effect-${row.key}`">
          <th scope="row" class="text-body-large">{{ row.label }}</th>
          <td class="text-title-medium" data-test="effect-now">{{ formatCount(row.now) }}</td>
          <td
            class="text-title-medium"
            :class="{ effect__changed: row.now !== row.after }"
            data-test="effect-after"
          >
            {{ formatCount(row.after) }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!sentence && !loading" class="text-body-large" data-test="effect-idle">
      {{
        changed ? "It couldn't be worked out." : 'Change something above to see what it would do.'
      }}
    </p>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      class="mt-4"
      role="alert"
      data-test="effect-failure"
    >
      {{ failure }}
    </v-alert>

    <div class="effect__actions">
      <v-btn
        color="primary"
        :disabled="!changed"
        :loading="saving"
        data-test="effect-save"
        @click="$emit('save')"
      >
        Save
      </v-btn>
      <v-btn
        variant="text"
        :disabled="!changed || saving"
        data-test="effect-discard"
        @click="$emit('discard')"
      >
        Discard changes
      </v-btn>
      <output v-if="saved" class="text-body-medium" data-test="effect-saved">
        Saved. The incidents that are going on were judged again.
      </output>
    </div>
  </SectionCard>
</template>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.effect__sentence {
  margin: 0 0 1rem;
}

.effect__table {
  width: 100%;
  border-collapse: collapse;
  text-align: right;
}

.effect__table th[scope='row'] {
  text-align: left;
  font-weight: 400;
}

.effect__table th,
.effect__table td {
  padding: 0.5rem 0.75rem;
}

.effect__table tbody tr + tr {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.effect__changed {
  color: rgb(var(--v-theme-primary));
}

.effect__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  margin-top: 1.25rem;
}
</style>
