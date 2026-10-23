<script setup lang="ts">
/**
 * The frame every page sits in: how wide it may get, the space around it, and the same gap
 * between whatever is stacked inside it (a header, alerts, cards). A page puts its parts inside
 * and adds no margins of its own.
 */
withDefaults(defineProps<{ width?: 'narrow' | 'regular' | 'wide' }>(), { width: 'regular' })

/** In pixels: a form or list, a page of cards, and a page of charts and tables. */
const WIDTHS = { narrow: 720, regular: 960, wide: 1320 } as const
</script>

<template>
  <v-container class="app-page py-6 py-md-8" :max-width="WIDTHS[width]">
    <div class="app-page__stack">
      <slot />
    </div>
  </v-container>
</template>

<style scoped>
.app-page__stack {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
</style>
