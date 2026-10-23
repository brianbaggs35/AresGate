<script setup lang="ts">
import { ref } from 'vue'

/**
 * A card with a title, what it is for, and the actions for the card as a whole beside the title.
 * Every group of settings, every list and every panel on a page is one, so they all look alike.
 */
defineProps<{
  title: string
  description?: string
}>()

const heading = ref<HTMLElement | null>(null)

/** Moves the keyboard to the title, for a card whose content has just been replaced. */
function focusTitle() {
  heading.value?.focus()
}
defineExpose({ focusTitle })
</script>

<template>
  <v-card class="section-card pa-5 pa-sm-6">
    <div class="section-card__head">
      <h2
        ref="heading"
        tabindex="-1"
        class="section-card__title text-title-large"
        data-test="section-title"
      >
        {{ title }}
      </h2>
      <p
        v-if="description"
        class="section-card__description text-body-medium text-medium-emphasis"
        data-test="section-description"
      >
        {{ description }}
      </p>
      <div v-if="$slots.actions" class="section-card__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </v-card>
</template>

<style scoped>
/* The title and the actions share the first row, on a phone too, so the actions stay next to
 * what they are for; the description runs underneath across both. */
.section-card__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.25rem 1rem;
  margin-bottom: 1rem;
}

.section-card__title {
  grid-column: 1;
  grid-row: 1;
  margin: 0;
}

.section-card__title:focus {
  outline: none;
}

.section-card__description {
  grid-column: 1 / -1;
  grid-row: 2;
  margin: 0;
}

.section-card__actions {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
