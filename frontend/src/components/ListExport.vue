<script setup lang="ts">
import { Download } from '@lucide/vue'
import { computed, useId } from 'vue'

import { exportAddress } from '@/api/exports'
import type { ViewPage } from '@/api/views'

/**
 * The file of a list: everything its filters and its order show, not only the page on screen, as
 * a spreadsheet or as JSON. The links are ordinary downloads, so the browser saves the file as it
 * arrives however long it is.
 */
const props = defineProps<{
  list: ViewPage
  /** The filters and the order, as the list's own request holds them. */
  asked: URLSearchParams
}>()

const headingId = useId()
const csv = computed(() => exportAddress(props.list, 'csv', props.asked))
const json = computed(() => exportAddress(props.list, 'json', props.asked))
</script>

<template>
  <section class="export" :aria-labelledby="headingId" data-test="list-export">
    <h2 :id="headingId" class="text-title-small">Export</h2>
    <p class="text-body-medium text-medium-emphasis">
      Everything these filters show, in this order, up to 10,000 rows. Times are in your time zone.
    </p>
    <div class="export__links">
      <v-btn :href="csv" download variant="tonal" :prepend-icon="Download" data-test="export-csv">
        CSV
      </v-btn>
      <v-btn :href="json" download variant="tonal" :prepend-icon="Download" data-test="export-json">
        JSON
      </v-btn>
    </div>
  </section>
</template>

<style scoped>
.export {
  display: grid;
  gap: 0.5rem;
}

.export h2,
.export p {
  margin: 0;
}

.export__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
