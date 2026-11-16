<script setup lang="ts">
import { ChevronDown, ChevronRight } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import type { Incident } from '@/api/incidents'
import DataTable from '@/components/DataTable.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import {
  COLUMNS,
  groupedByAddress,
  nextSort,
  sortedBy,
  type Section,
  type Sort,
} from '@/incident-table'
import { isAboutRule } from '@/incidents'
import { SEVERITY } from '@/severity'

/**
 * The incidents as a table: a row each, with the columns that can be sorted and, when asked,
 * the incidents about one address gathered under it. It is for reading many at once. Sorting
 * is of the incidents loaded so far, which the table says. A box on each row picks it, for a
 * change to many at once, and the title leads to the incident.
 */
const props = defineProps<{
  incidents: readonly Incident[]
  /** Whether the incidents about one address are gathered under it. */
  grouped: boolean
  /** Whether an incident is picked. */
  has: (id: number) => boolean
  /** How many more there are than are loaded, which sorting can't reach. */
  more: number
}>()
const emit = defineEmits<{
  /** A row was ticked or taken off: `range` when the shift key was held. */
  select: [id: number, range: boolean]
  /** A group was ticked or taken off as a whole. */
  'select-many': [ids: number[], on: boolean]
}>()

const sort = ref<Sort | null>(null)
/** The addresses whose groups are folded away. */
const folded = ref<ReadonlySet<string>>(new Set())

const ordered = computed(() => sortedBy(props.incidents, sort.value))
const sections = computed<Section[]>(() =>
  props.grouped
    ? groupedByAddress(ordered.value)
    : ordered.value.map((incident) => ({ kind: 'alone', incident })),
)

/** What the table says of itself under it, so a sort that leaves some out is not a surprise. */
const caption = computed(() => {
  const count = `${formatCount(props.incidents.length)} incidents`
  const sorted = sort.value ? ', in the order you chose' : ''
  const left =
    sort.value && props.more > 0
      ? `. Sorting covers only these: ${formatCount(props.more)} more are not loaded yet`
      : ''
  return `${count}${sorted}${left}`
})

function press(key: Sort['key']) {
  sort.value = nextSort(sort.value, key)
}

function ariaSort(key: Sort['key']): 'ascending' | 'descending' | 'none' {
  if (sort.value?.key !== key) return 'none'
  return sort.value.direction === 'asc' ? 'ascending' : 'descending'
}

function fold(subject: string) {
  const next = new Set(folded.value)
  if (next.has(subject)) next.delete(subject)
  else next.add(subject)
  folded.value = next
}

const about = (subject: string) => (isAboutRule(subject) ? 'A rule with no address' : subject)

function pickedIn(members: readonly Incident[]) {
  return members.filter(({ id }) => props.has(id)).length
}
</script>

<template>
  <v-card class="incident-table" data-test="incident-table">
    <DataTable label="Incidents" sticky-first>
      <table class="incident-table__table">
        <caption class="incident-table__caption text-body-medium text-medium-emphasis">
          {{
            caption
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col" class="incident-table__pick">
              <span class="sr-only">Select</span>
            </th>
            <th
              v-for="column in COLUMNS"
              :key="column.key"
              scope="col"
              :aria-sort="ariaSort(column.key)"
              :data-test="`column-${column.key}`"
            >
              <button
                type="button"
                class="incident-table__sort text-label-large"
                :data-test="`sort-${column.key}`"
                @click="press(column.key)"
              >
                {{ column.label }}
                <span aria-hidden="true" class="incident-table__arrow">{{
                  sort?.key === column.key ? (sort.direction === 'asc' ? '↑' : '↓') : ''
                }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <template
            v-for="section in sections"
            :key="section.kind === 'group' ? `group:${section.subject}` : section.incident.id"
          >
            <template v-if="section.kind === 'group'">
              <tr class="incident-table__group" data-test="incident-group">
                <td class="incident-table__pick">
                  <input
                    type="checkbox"
                    class="incident-table__box"
                    :checked="pickedIn(section.members) === section.members.length"
                    :indeterminate="
                      pickedIn(section.members) > 0 &&
                      pickedIn(section.members) < section.members.length
                    "
                    :aria-label="`Select all ${section.members.length} about ${about(section.subject)}`"
                    data-test="group-select"
                    @change="
                      emit(
                        'select-many',
                        section.members.map(({ id }) => id),
                        ($event.target as HTMLInputElement).checked,
                      )
                    "
                  />
                </td>
                <td :colspan="COLUMNS.length">
                  <button
                    type="button"
                    class="incident-table__fold text-title-small"
                    :aria-expanded="!folded.has(section.subject)"
                    data-test="group-fold"
                    @click="fold(section.subject)"
                  >
                    <v-icon
                      :icon="folded.has(section.subject) ? ChevronRight : ChevronDown"
                      size="18"
                      aria-hidden="true"
                    />
                    <span class="incident-table__subject">{{ about(section.subject) }}</span>
                    <span class="text-medium-emphasis" data-test="group-count">
                      {{ formatCount(section.members.length) }} incidents, worst
                      {{ SEVERITY[section.worst].label.toLowerCase() }}
                    </span>
                  </button>
                </td>
              </tr>
            </template>
            <template v-if="section.kind === 'group' ? !folded.has(section.subject) : true">
              <tr
                v-for="incident in section.kind === 'group' ? section.members : [section.incident]"
                :key="incident.id"
                class="incident-table__row"
                :class="{
                  'incident-table__row--selected': has(incident.id),
                  'incident-table__row--member': section.kind === 'group',
                }"
                data-test="incident-card"
              >
                <td class="incident-table__pick">
                  <input
                    type="checkbox"
                    class="incident-table__box"
                    :checked="has(incident.id)"
                    :aria-label="`Select: ${incident.title}`"
                    data-test="incident-select"
                    @click="emit('select', incident.id, ($event as MouseEvent).shiftKey)"
                  />
                </td>
                <td><SeverityChip :severity="incident.severity" /></td>
                <td class="incident-table__title">
                  <RouterLink
                    :to="{ name: 'incident', params: { id: incident.id } }"
                    class="text-title-small"
                    data-test="incident"
                  >
                    <span data-test="incident-title">{{ incident.title }}</span>
                  </RouterLink>
                </td>
                <td class="incident-table__subject" data-test="row-subject">
                  {{ about(incident.subject) }}
                </td>
                <td class="tabular-nums" data-test="row-confidence">
                  {{ incident.confidence }} of 100
                </td>
                <td>
                  <IncidentStatusChip v-if="incident.status !== 'open'" :status="incident.status" />
                  <span v-else class="text-medium-emphasis">Open</span>
                  <VerdictChip v-if="incident.verdict" :verdict="incident.verdict" size="small" />
                </td>
                <td>
                  <time
                    :datetime="incident.last_seen_at"
                    :title="formatDateTime(incident.last_seen_at)"
                    >{{ formatAgo(incident.last_seen_at) }}</time
                  >
                </td>
                <td class="tabular-nums" data-test="row-signals">
                  {{ formatCount(incident.signal_count) }}
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </DataTable>
  </v-card>
</template>

<style scoped>
.incident-table__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.incident-table__caption {
  padding: 0.75rem 1rem;
  text-align: start;
  caption-side: bottom;
}

.incident-table__table th,
.incident-table__table td {
  padding: 0.5rem 0.75rem;
  text-align: start;
  vertical-align: middle;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.incident-table__pick {
  width: 2.5rem;
}

.incident-table__box {
  width: 1.125rem;
  height: 1.125rem;
  accent-color: rgb(var(--v-theme-primary));
}

.incident-table__sort,
.incident-table__fold {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 2rem;
  padding: 0;
  color: inherit;
  background: none;
  border: 0;
  cursor: pointer;
}

.incident-table__sort:focus-visible,
.incident-table__fold:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.incident-table__arrow {
  display: inline-block;
  min-width: 1ch;
}

.incident-table__group {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.incident-table__title {
  min-width: 14rem;
}

.incident-table__subject {
  overflow-wrap: anywhere;
}

.incident-table__row--member td:nth-child(3) {
  padding-inline-start: 1.5rem;
}

.incident-table__row--selected {
  background: rgba(var(--v-theme-primary), 0.08);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

:root[data-density='compact'] .incident-table__table th,
:root[data-density='compact'] .incident-table__table td {
  padding-block: 0.25rem;
}
</style>
