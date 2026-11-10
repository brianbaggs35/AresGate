<script setup lang="ts">
import { ChevronDown, Copy } from '@lucide/vue'
import { computed, ref } from 'vue'

import type { Occurrence } from '@/api/incidents'
import EvidenceDetails from '@/components/EvidenceDetails.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { agreedBy, hasDetail, reportsOf, worthListing } from '@/evidence'
import { formatAgo, formatCount } from '@/format'

/**
 * The alerts of an incident that happened again and again, or that more than one program had
 * something to say about, as one line each with how many times: a scanner that sent the same
 * probe four hundred times is one alert that happened four hundred times, and not four hundred
 * alerts. Where another program reported the same alert it is that alert, seen twice, and counts
 * once; the line says which programs saw it, and what each of them said of it can be opened.
 */
const props = defineProps<{ occurrences: readonly Occurrence[] }>()

/** Only those that happened more than once, were reported by two programs or have more to say. */
const repeated = computed(() => props.occurrences.filter(worthListing))
const MOST = 8
const shown = computed(() =>
  repeated.value.slice(0, MOST).map((item, index) => ({
    item,
    index,
    // What each program said, for the programs that said any.
    reports: reportsOf(item).filter(({ evidence }) => hasDetail(evidence)),
  })),
)

/** Which are opened: the first that has something to open, until a person chooses. */
const chosen = ref<Record<number, boolean>>({})
const first = computed(() => shown.value.find(({ reports }) => reports.length > 0)?.index)
function isOpen(index: number): boolean {
  return chosen.value[index] ?? index === first.value
}
function toggle(index: number) {
  chosen.value = { ...chosen.value, [index]: !isOpen(index) }
}
</script>

<template>
  <ul class="occurrences" data-test="occurrences">
    <li
      v-for="{ item, index, reports } in shown"
      :key="index"
      class="occurrences__item"
      data-test="occurrence"
    >
      <SeverityChip :severity="item.signal.severity" />
      <div class="occurrences__text">
        <p class="text-body-large" data-test="occurrence-summary">{{ item.signal.summary }}</p>
        <p class="text-body-medium text-medium-emphasis">
          <b class="tabular-nums" data-test="occurrence-count">{{ formatCount(item.count) }}</b>
          {{ item.count === 1 ? 'time' : 'times' }} from {{ item.signal.source_name }}, the last
          <time :datetime="item.last_at">{{ formatAgo(item.last_at) }}</time
          >.
          <span v-if="item.duplicates > 0" data-test="occurrence-duplicates">
            <v-icon :icon="Copy" size="16" aria-hidden="true" />
            {{ formatCount(item.duplicates) }} also reported by {{ agreedBy(item) }}, counted once.
          </span>
        </p>
        <template v-if="reports.length">
          <v-btn
            variant="text"
            size="small"
            class="occurrences__toggle"
            :append-icon="ChevronDown"
            :aria-expanded="isOpen(index)"
            :aria-controls="`occurrence-${index.toString()}`"
            :class="{ 'occurrences__toggle--open': isOpen(index) }"
            data-test="occurrence-toggle"
            @click="toggle(index)"
          >
            {{ isOpen(index) ? 'Hide' : 'Show' }} what
            {{ reports.length === 1 ? 'the program' : 'each program' }} said
          </v-btn>
          <div
            v-show="isOpen(index)"
            :id="`occurrence-${index.toString()}`"
            class="occurrences__reports"
            data-test="occurrence-reports"
          >
            <section
              v-for="report in reports"
              :key="report.source"
              class="occurrences__report"
              data-test="occurrence-report"
            >
              <h3 class="text-title-medium">{{ report.name }}</h3>
              <EvidenceDetails v-if="report.evidence" :evidence="report.evidence" />
            </section>
          </div>
        </template>
      </div>
    </li>
    <li
      v-if="repeated.length > shown.length"
      class="text-body-medium text-medium-emphasis"
      data-test="occurrences-more"
    >
      And {{ formatCount(repeated.length - shown.length) }} more that repeated.
    </li>
  </ul>
</template>

<style scoped>
.occurrences {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.occurrences__item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.occurrences__text {
  flex: 1;
  min-width: 0;
}

.occurrences__text p {
  margin: 0;
  overflow-wrap: anywhere;
}

.occurrences__toggle {
  margin: 0.25rem 0 0 -0.75rem;
}

.occurrences__toggle :deep(.v-btn__append) {
  transition: transform 150ms;
}

.occurrences__toggle--open :deep(.v-btn__append) {
  transform: rotate(180deg);
}

.occurrences__reports {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 0.5rem;
}

/* What each program said sits on its own, a rule down the side telling the programs apart. */
.occurrences__report {
  padding-left: 0.875rem;
  border-left: 3px solid rgba(var(--v-theme-primary), 0.5);
}

.occurrences__report h3 {
  margin: 0 0 0.5rem;
}

@media (prefers-reduced-motion: reduce) {
  .occurrences__toggle :deep(.v-btn__append) {
    transition: none;
  }
}
</style>
