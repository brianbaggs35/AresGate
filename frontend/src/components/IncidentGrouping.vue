<script setup lang="ts">
import { Link2 } from '@lucide/vue'
import { computed, ref } from 'vue'

import { formatCount } from '@/format'
import { portLabel } from '@/incidents'

/**
 * Why the signals of an incident are one incident, a fact to a line, and under them the ports
 * they touched when there were several. A bot that comes back all afternoon is one actor; the
 * same bot another day is another incident, and the lines say which of that applied.
 */
const props = defineProps<{
  grouping: readonly string[]
  ports: readonly number[]
  /** Whether there were more ports than are kept. */
  capped: boolean
}>()

/** How many ports are listed before the rest are asked for: a sweep can touch a thousand. */
const PAGE = 24

const shown = ref(PAGE)
const listed = computed(() => props.ports.slice(0, shown.value))
const hidden = computed(() => Math.max(0, props.ports.length - shown.value))
</script>

<template>
  <div class="grouping" data-test="grouping">
    <ul class="grouping__list">
      <li v-for="line in grouping" :key="line" class="grouping__item" data-test="grouping-line">
        <v-icon :icon="Link2" size="18" class="grouping__icon" aria-hidden="true" />
        <span class="text-body-large">{{ line }}</span>
      </li>
    </ul>

    <template v-if="ports.length > 1">
      <h3 class="text-title-medium" data-test="ports-title">
        {{ capped ? 'The first' : 'The' }} {{ formatCount(ports.length) }} ports it touched
      </h3>
      <ul class="grouping__ports" data-test="ports">
        <li v-for="port in listed" :key="port">
          <v-chip size="small" variant="outlined" class="grouping__port" data-test="port">{{
            portLabel(port)
          }}</v-chip>
        </li>
      </ul>
      <v-btn
        v-if="hidden > 0"
        variant="outlined"
        class="grouping__more"
        data-test="ports-show-more"
        @click="shown += PAGE * 2"
      >
        Show {{ formatCount(Math.min(hidden, PAGE * 2)) }} more
      </v-btn>
    </template>
  </div>
</template>

<style scoped>
.grouping__list,
.grouping__ports {
  list-style: none;
  margin: 0;
  padding: 0;
}

.grouping__item {
  display: grid;
  grid-template-columns: 1.125rem minmax(0, 1fr);
  gap: 0 0.75rem;
  padding: 0.5rem 0;
}

.grouping__item + .grouping__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.grouping__icon {
  margin-top: 0.2rem;
  color: rgb(var(--v-theme-primary));
}

.grouping h3 {
  margin: 1rem 0 0.5rem;
}

.grouping__ports {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.grouping__port {
  font-variant-numeric: tabular-nums;
}

.grouping__more {
  margin-top: 0.75rem;
}
</style>
