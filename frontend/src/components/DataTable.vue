<script setup lang="ts">
/**
 * The frame a wide table sits in, so every table behaves the same where it is wider than the
 * screen: it scrolls sideways inside its own box (never the page), the box can be reached with
 * the keyboard and is named for a screen reader, a fade at an edge says there is more that way,
 * and, with `stickyFirst`, the first column stays while the rest goes by. It leaves the table
 * itself alone, so the page keeps its own columns and cells.
 */
defineProps<{
  /** What the table is, for a screen reader. */
  label: string
  /** Keeps the first column in place while the others scroll. */
  stickyFirst?: boolean
}>()
</script>

<template>
  <div
    class="data-table"
    :class="{ 'data-table--sticky-first': stickyFirst }"
    role="region"
    :aria-label="label"
    tabindex="0"
    data-test="data-table"
  >
    <slot />
  </div>
</template>

<style scoped>
/* The fades are the page's own color drawn over the edge that has more beyond it (`local` moves
 * with the content, so each is covered once that end is reached), and a faint shadow that stays
 * (`scroll`). Where the table fits, none of it shows. */
.data-table {
  overflow-x: auto;
  background:
    linear-gradient(to right, rgb(var(--v-theme-surface)) 30%, transparent) left center / 2rem 100%
      no-repeat local,
    linear-gradient(to left, rgb(var(--v-theme-surface)) 30%, transparent) right center / 2rem 100%
      no-repeat local,
    radial-gradient(farthest-side at 0 50%, rgba(0, 0, 0, 0.22), transparent) left center / 0.5rem
      100% no-repeat scroll,
    radial-gradient(farthest-side at 100% 50%, rgba(0, 0, 0, 0.22), transparent) right center /
      0.5rem 100% no-repeat scroll;
}

.data-table:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.data-table--sticky-first :deep(tr > :first-child) {
  position: sticky;
  inset-inline-start: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
}

@media (forced-colors: active) {
  .data-table {
    background: none;
    border-inline: 1px solid CanvasText;
  }

  .data-table--sticky-first :deep(tr > :first-child) {
    background: Canvas;
  }
}
</style>
