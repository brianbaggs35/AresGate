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
  <v-container
    class="app-page py-6 py-md-8"
    :class="`app-page--${width}`"
    :style="{ '--page-width': `${WIDTHS[width]}px` }"
  >
    <div class="app-page__stack">
      <slot />
    </div>
  </v-container>
</template>

<style scoped>
/* Pages start at the same place whatever their width, so titles don't jump between them. */
.app-page {
  margin-inline: 0;
  max-width: var(--page-width);
}

/* On a big screen the pages that show data grow with it, so a wall of pixels is not left empty
 * beside a narrow column. A form stays the width it reads well at. */
@media (min-width: 1920px) {
  .app-page--regular {
    max-width: 1200px;
  }

  .app-page--wide {
    max-width: min(1800px, 94%);
  }
}

@media (min-width: 2560px) {
  .app-page--regular {
    max-width: 1440px;
  }

  .app-page--wide {
    max-width: min(2400px, 94%);
  }
}

.app-page__stack {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
</style>
