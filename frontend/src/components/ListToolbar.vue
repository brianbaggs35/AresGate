<script setup lang="ts">
import { Bookmark, Download, Ellipsis } from '@lucide/vue'
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

import type { ViewPage } from '@/api/views'
import ListExport from '@/components/ListExport.vue'
import ListViews from '@/components/ListViews.vue'
import { useViewsStore } from '@/stores/views'

/**
 * What every list offers in the same place: a file of what it shows, and the views kept for it.
 * On a computer they are two buttons, and on a phone one menu that holds both. A page with no
 * filters set opens on the view its owner chose to open it on, if one was.
 */
const props = defineProps<{
  list: ViewPage
  /** The filters and the order, as the list's own request holds them. */
  asked: URLSearchParams
}>()

const route = useRoute()
const router = useRouter()
const views = useViewsStore()
const { xs: phone } = useDisplay()

onMounted(async () => {
  await views.load()
  const chosen = views.defaultOf(props.list)
  // Only a page that was opened bare: filters in the address are what someone came for.
  if (chosen && Object.keys(route.query).length === 0) {
    await router.replace({ query: chosen.query })
  }
})
</script>

<template>
  <div class="toolbar" data-test="list-toolbar">
    <v-menu v-if="phone" location="bottom end" :close-on-content-click="false">
      <template #activator="{ props: activator }">
        <v-btn v-bind="activator" variant="text" :prepend-icon="Ellipsis" data-test="list-options">
          Options
        </v-btn>
      </template>
      <v-card class="toolbar__panel pa-4" data-test="list-panel">
        <ListExport :list="list" :asked="asked" />
        <v-divider class="my-3" />
        <ListViews :list="list" />
      </v-card>
    </v-menu>
    <template v-else>
      <v-menu location="bottom end" :close-on-content-click="false">
        <template #activator="{ props: activator }">
          <v-btn v-bind="activator" variant="text" :prepend-icon="Download" data-test="list-export">
            Export
          </v-btn>
        </template>
        <v-card class="toolbar__panel pa-4" data-test="export-panel">
          <ListExport :list="list" :asked="asked" />
        </v-card>
      </v-menu>
      <v-menu location="bottom end" :close-on-content-click="false">
        <template #activator="{ props: activator }">
          <v-btn
            v-bind="activator"
            variant="text"
            :prepend-icon="Bookmark"
            data-test="list-views-button"
          >
            Views
          </v-btn>
        </template>
        <v-card class="toolbar__panel pa-4" data-test="views-panel">
          <ListViews :list="list" />
        </v-card>
      </v-menu>
    </template>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
}

.toolbar__panel {
  width: min(28rem, calc(100vw - 2rem));
  max-height: min(36rem, 80vh);
  overflow-y: auto;
}
</style>
