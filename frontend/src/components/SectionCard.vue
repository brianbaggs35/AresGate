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
      <div class="section-card__text">
        <h2 ref="heading" tabindex="-1" class="text-title-large" data-test="section-title">
          {{ title }}
        </h2>
        <p
          v-if="description"
          class="text-body-medium text-medium-emphasis"
          data-test="section-description"
        >
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions" class="section-card__actions">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </v-card>
</template>

<style scoped>
.section-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}

.section-card__text {
  flex: 1 1 16rem;
  min-width: 0;
}

.section-card__text h2:focus {
  outline: none;
}

.section-card__text p {
  margin: 0.25rem 0 0;
}

.section-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
