<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { LogEvent } from '@/api/logs'
import { formatAgo, formatClock, formatTimestamp } from '@/format'
import { COLUMNS, endpoint, tableRows, type ColumnKey, type TimeMode } from '@/logs'
import { SEVERITY } from '@/severity'

/**
 * The events as a dense table, the newest first, for a screen wide enough to read across: one
 * line each, the columns the person chose, a heading that stays under the app bar while the
 * rows scroll, and a heading for each day. An event opens in the drawer with a click anywhere on
 * its row, or with Enter on its summary, which the arrow keys move between.
 */
const props = defineProps<{
  events: readonly LogEvent[]
  columns: readonly ColumnKey[]
  time: TimeMode
  /** The cursor of the event that is open, if one is. */
  selected: string | null
  /** The moment "how long ago" is counted from. */
  now: number
}>()
const emit = defineEmits<{ open: [event: LogEvent] }>()

const body = ref<HTMLElement | null>(null)

const shown = computed(() => COLUMNS.filter(({ key }) => props.columns.includes(key)))
const rows = computed(() => tableRows(props.events, props.time === 'exact', props.now))

const accent = (event: LogEvent) => `rgb(var(--v-theme-${SEVERITY[event.severity].color}))`

/** The time as the column shows it, and the other way of saying it for the tooltip. */
function when(iso: string): { shown: string; other: string } {
  const exact = formatClock(iso)
  const ago = formatAgo(iso, props.now)
  return props.time === 'exact'
    ? { shown: exact, other: `${formatTimestamp(iso)} (${ago})` }
    : { shown: ago, other: formatTimestamp(iso) }
}

/** A click anywhere on a row opens it, unless it was the end of selecting some of its text. The
 * summary is a button for the keyboard; its Enter arrives here as a click. */
function onClick(event: MouseEvent) {
  const row = (event.target as Element).closest<HTMLElement>('tr[data-cursor]')
  if (!row || window.getSelection()?.isCollapsed === false) return
  const found = props.events.find(({ cursor }) => cursor === row.dataset.cursor)
  if (found) emit('open', found)
}

/** The arrow keys, Home and End move between the summaries, so the rows are quick to go down. */
function onKey(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (!target.matches('.log-table__open')) return
  const buttons = [...(body.value as HTMLElement).querySelectorAll<HTMLElement>('.log-table__open')]
  const index = buttons.indexOf(target)
  const next = {
    ArrowDown: index + 1,
    ArrowUp: index - 1,
    Home: 0,
    End: buttons.length - 1,
  }[event.key]
  if (next === undefined) return
  event.preventDefault()
  buttons[Math.min(Math.max(next, 0), buttons.length - 1)]?.focus()
}

onMounted(() => {
  body.value?.addEventListener('click', onClick)
  body.value?.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  body.value?.removeEventListener('click', onClick)
  body.value?.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="log-table" data-test="log-table">
    <table>
      <caption class="log-table__caption">
        Events, the newest first
      </caption>
      <thead>
        <tr>
          <th
            v-for="column in shown"
            :key="column.key"
            scope="col"
            class="text-label-large"
            :class="`log-table__${column.key}`"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody ref="body">
        <template v-for="row in rows" :key="row.type === 'day' ? row.key : row.event.id">
          <tr v-if="row.type === 'day'" class="log-table__day" data-test="log-day">
            <td :colspan="shown.length" class="text-label-large">{{ row.label }}</td>
          </tr>
          <tr
            v-else
            class="log-table__row"
            :class="{ 'log-table__row--on': row.event.cursor === selected }"
            :style="{ '--accent': accent(row.event) }"
            :data-cursor="row.event.cursor"
            data-test="log-row"
          >
            <td
              v-for="column in shown"
              :key="column.key"
              :class="`log-table__${column.key}`"
              :data-column="column.key"
            >
              <time
                v-if="column.key === 'time'"
                :datetime="row.event.at"
                :title="when(row.event.at).other"
                class="tabular-nums"
                >{{ when(row.event.at).shown }}</time
              >
              <span v-else-if="column.key === 'severity'" class="log-table__severity">
                <v-icon :icon="SEVERITY[row.event.severity].icon" size="16" aria-hidden="true" />
                {{ SEVERITY[row.event.severity].label }}
              </span>
              <template v-else-if="column.key === 'source'">{{ row.event.source_name }}</template>
              <span v-else-if="column.key === 'kind'" class="log-table__pill">{{
                row.event.kind
              }}</span>
              <template v-else-if="column.key === 'from'">{{
                endpoint(row.event.src_address, row.event.src_port)
              }}</template>
              <template v-else-if="column.key === 'to'">{{
                endpoint(row.event.dst_address, row.event.dst_port)
              }}</template>
              <template v-else-if="column.key === 'protocol'">{{ row.event.protocol }}</template>
              <template v-else-if="column.key === 'signature'">{{ row.event.signature }}</template>
              <template v-else-if="column.key === 'connection'">{{
                row.event.connection
              }}</template>
              <time
                v-else-if="column.key === 'received'"
                :datetime="row.event.received_at"
                :title="formatTimestamp(row.event.received_at)"
                class="tabular-nums"
                >{{ formatClock(row.event.received_at) }}</time
              >
              <button
                v-else
                type="button"
                class="log-table__open"
                :title="row.event.summary"
                :aria-current="row.event.cursor === selected ? 'true' : undefined"
                data-test="log-open"
              >
                {{ row.event.summary }}
              </button>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.log-table {
  /* `clip`, not `hidden`: the heading sticks to the window, so this must not scroll. */
  overflow: clip;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface));
}

.log-table table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.875rem;
}

.log-table__caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.log-table th {
  position: sticky;
  top: var(--v-layout-top, 0px);
  z-index: 2;
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant));
  background: rgb(var(--v-theme-surface));
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  text-align: start;
  white-space: nowrap;
}

.log-table td {
  padding: 0.4375rem 0.75rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  white-space: nowrap;
  vertical-align: middle;
}

.log-table tbody tr:last-child td {
  border-bottom: 0;
}

/* The row says how serious it is down its left edge, and the severity column says it in words. */
.log-table__row td:first-child {
  box-shadow: inset 3px 0 0 var(--accent);
}

.log-table__row {
  cursor: pointer;
}

.log-table__row:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.log-table__row--on,
.log-table__row--on:hover {
  background: rgba(var(--v-theme-primary), 0.1);
}

.log-table__row:has(.log-table__open:focus-visible) {
  background: rgba(var(--v-theme-on-surface), var(--v-focus-opacity));
}

.log-table__day td {
  padding-block: 0.5rem;
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant));
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.log-table__time {
  width: 1%;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.log-table__severity {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.log-table__severity .v-icon {
  color: var(--accent);
}

.log-table__pill {
  display: inline-block;
  padding: 0.0625rem 0.5rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 999px;
  font-size: 0.75rem;
}

.log-table__from,
.log-table__to {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
}

.log-table__signature {
  max-width: 16rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The summary takes what the others leave and is cut off with an ellipsis, so every row stays
 * one line tall; its full text is in the tooltip and the drawer. */
td.log-table__summary {
  width: 100%;
  max-width: 0;
  padding-block: 0;
}

.log-table__open {
  display: block;
  width: 100%;
  min-height: 2.25rem;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: start;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.log-table__open:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
  border-radius: 0.25rem;
}
</style>
