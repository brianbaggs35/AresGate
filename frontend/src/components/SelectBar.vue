<script setup lang="ts">
import { X } from '@lucide/vue'

import { formatCount } from '@/format'

/**
 * The row above a list that changes many of its rows at once. With none picked it is the box that
 * picks every row and a hint; with some picked it says how many and holds the changes, which
 * whoever shows it puts in the slot, and a button that lets them all go. It stays under the top
 * bar as the list is scrolled, so it is there for the last row of a long list too.
 */
const props = defineProps<{
  /** How many rows are picked. */
  count: number
  /** Every row that is shown is picked, and there is something shown. */
  whole: boolean
  /** What a row is, in one and in many: "decision", "decisions". */
  singular: string
  plural: string
}>()
const emit = defineEmits<{ 'toggle-all': []; clear: [] }>()

const noun = (count: number) => (count === 1 ? props.singular : props.plural)
</script>

<template>
  <section
    class="select-bar"
    :class="{ 'select-bar--on': count > 0 }"
    :aria-label="`Change many ${plural} at once`"
    data-test="select-bar"
  >
    <label class="select-bar__all">
      <input
        type="checkbox"
        class="select-bar__box"
        :checked="whole"
        :indeterminate="count > 0 && !whole"
        :aria-label="`Select every ${singular} on this list`"
        data-test="select-all"
        @change="emit('toggle-all')"
      />
    </label>

    <p
      v-if="count === 0"
      class="select-bar__hint text-body-medium text-medium-emphasis"
      data-test="select-hint"
    >
      Select {{ plural }} to change them together
    </p>
    <template v-else>
      <output class="select-bar__count text-title-medium" data-test="select-count">
        {{ formatCount(count) }} {{ noun(count) }} selected
      </output>
      <div class="select-bar__actions">
        <slot />
      </div>
      <v-btn
        variant="text"
        density="comfortable"
        :prepend-icon="X"
        class="select-bar__clear"
        data-test="select-clear"
        @click="emit('clear')"
      >
        Clear
      </v-btn>
    </template>
  </section>
</template>

<style scoped>
.select-bar {
  position: sticky;
  top: calc(var(--v-layout-top, 0px) + 0.5rem);
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  min-height: 52px;
  margin-block-end: 0.5rem;
  padding: 0.25rem 0.75rem 0.25rem 0.5rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface));
}

.select-bar--on {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.14);
}

.select-bar__all {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  cursor: pointer;
}

.select-bar__box {
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
  cursor: pointer;
}

.select-bar__box:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}

.select-bar__hint,
.select-bar__count {
  margin: 0;
}

.select-bar__hint {
  flex: 1;
}

.select-bar__count {
  flex: 1;
  min-width: 0;
}

/* On a phone the changes take a row of their own, under the count. */
.select-bar__actions {
  display: flex;
  flex: 1 0 100%;
  flex-wrap: wrap;
  gap: 0.5rem;
  order: 3;
}

.select-bar__clear {
  min-height: 2.75rem;
}

@media (min-width: 600px) {
  .select-bar__actions {
    flex: 0 1 auto;
    order: 0;
  }

  .select-bar__count {
    flex: 0 1 auto;
  }

  .select-bar__clear {
    margin-inline-start: auto;
  }
}
</style>
