<script setup lang="ts">
import { Columns3 } from '@lucide/vue'

import { COLUMNS, DEFAULT_COLUMNS, type ColumnKey, type TimeMode } from '@/logs'

/**
 * A menu for how the table looks: which columns it has, and whether the time is the exact time
 * or how long ago. The time and the summary are always there, since a row without them says
 * nothing. What is chosen is remembered by this browser (`src/logs.ts`).
 */
const props = defineProps<{
  columns: readonly ColumnKey[]
  time: TimeMode
}>()
const emit = defineEmits<{
  'update:columns': [columns: ColumnKey[]]
  'update:time': [time: TimeMode]
}>()

/** The columns with one turned on or off, in the table's own order. */
function toggle(key: ColumnKey, on: boolean | null) {
  emit(
    'update:columns',
    COLUMNS.filter((column) =>
      column.key === key ? on === true : props.columns.includes(column.key),
    ).map((column) => column.key),
  )
}

function pickTime(time: TimeMode | null) {
  if (time) emit('update:time', time)
}
</script>

<template>
  <v-menu :close-on-content-click="false" location="bottom end">
    <template #activator="{ props: activator }">
      <v-btn v-bind="activator" variant="text" :prepend-icon="Columns3" data-test="log-view">
        View
      </v-btn>
    </template>
    <v-card class="log-view pa-4" data-test="log-view-panel">
      <v-radio-group
        :model-value="time"
        label="Show time as"
        density="compact"
        hide-details
        data-test="log-view-time"
        @update:model-value="pickTime"
      >
        <v-radio label="The exact time" value="exact" data-test="time-exact" />
        <v-radio label="How long ago" value="relative" data-test="time-relative" />
      </v-radio-group>

      <fieldset class="log-view__columns">
        <legend class="text-body-large">Columns</legend>
        <v-checkbox
          v-for="column in COLUMNS"
          :key="column.key"
          :model-value="columns.includes(column.key)"
          :label="column.label"
          :disabled="column.fixed"
          density="compact"
          hide-details
          :data-test="`column-${column.key}`"
          @update:model-value="(on) => toggle(column.key, on)"
        />
      </fieldset>

      <v-btn
        variant="text"
        size="small"
        class="mt-2"
        data-test="columns-reset"
        @click="emit('update:columns', [...DEFAULT_COLUMNS])"
      >
        Use the usual columns
      </v-btn>
    </v-card>
  </v-menu>
</template>

<style scoped>
.log-view {
  min-width: 15rem;
}

.log-view__columns {
  margin: 0.75rem 0 0;
  padding: 0;
  border: 0;
}

.log-view__columns legend {
  margin-bottom: 0.25rem;
}
</style>
