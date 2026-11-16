<script setup lang="ts">
import { Layers, LayoutList, Table2 } from '@lucide/vue'

import { useIncidentLayoutStore, type IncidentLayout } from '@/stores/incident-layout'

/**
 * The choice between the incidents as cards and as a table that can be sorted, and for the table,
 * whether the incidents about one address are gathered under it. Both are remembered in this
 * browser.
 */
const layout = useIncidentLayoutStore()
</script>

<template>
  <div class="layout-toggle">
    <v-btn-toggle
      :model-value="layout.layout"
      mandatory
      divided
      density="comfortable"
      variant="outlined"
      color="primary"
      aria-label="Layout"
      data-test="layout"
      @update:model-value="layout.setLayout($event as IncidentLayout)"
    >
      <v-btn
        value="cards"
        :icon="LayoutList"
        aria-label="Cards"
        :aria-pressed="layout.layout === 'cards'"
        title="Cards"
        data-test="layout-cards"
      />
      <v-btn
        value="table"
        :icon="Table2"
        aria-label="Table"
        :aria-pressed="layout.layout === 'table'"
        title="Table"
        data-test="layout-table"
      />
    </v-btn-toggle>
    <v-btn
      v-if="layout.layout === 'table'"
      variant="outlined"
      density="comfortable"
      :prepend-icon="Layers"
      :color="layout.grouping === 'address' ? 'primary' : undefined"
      :aria-pressed="layout.grouping === 'address'"
      data-test="group-by-address"
      @click="layout.setGrouping(layout.grouping === 'address' ? 'none' : 'address')"
    >
      Group by address
    </v-btn>
  </div>
</template>

<style scoped>
.layout-toggle {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
