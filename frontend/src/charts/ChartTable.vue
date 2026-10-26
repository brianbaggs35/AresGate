<script setup lang="ts">
import type { ChartTableData } from '@/charts/types'

/** A chart's numbers in a table: the same data for anyone who reads it better that way, with a
 * screen reader or a keyboard, or who wants the exact figures. The first column names each row. */
defineProps<{
  table: ChartTableData
  /** What the chart is called. */
  label: string
}>()
</script>

<template>
  <section
    class="chart-table"
    tabindex="0"
    :aria-label="`${label}, as a table`"
    data-test="chart-table"
  >
    <table class="text-body-medium">
      <thead>
        <tr>
          <th
            v-for="(column, index) in table.columns"
            :key="column"
            scope="col"
            :class="{ 'chart-table__number': index > 0 }"
          >
            {{ column }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in table.rows" :key="index" data-test="chart-table-row">
          <th scope="row">{{ row[0] }}</th>
          <td v-for="(cell, column) in row.slice(1)" :key="column" class="chart-table__number">
            {{ cell }}
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.chart-table {
  max-height: 20rem;
  overflow: auto;
  border-radius: 8px;
}

.chart-table:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 0.5rem 0.75rem;
  border-bottom: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  text-align: left;
  font-weight: 400;
}

thead th {
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-weight: 500;
}

tbody th {
  font-weight: 500;
}

.chart-table__number {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
