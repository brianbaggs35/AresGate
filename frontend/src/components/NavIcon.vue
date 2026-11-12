<script setup lang="ts">
import { computed } from 'vue'

import type { NavItem } from '@/navigation'
import { useReviewStore } from '@/stores/review'

/**
 * The picture of a place in the menu. The Review place carries the number of decisions that wait
 * for the owner, in words for a screen reader as well.
 */
const props = defineProps<{ item: NavItem }>()
const review = useReviewStore()

const count = computed(() => (props.item.route === 'review' ? review.waiting : 0))
const shown = computed(() => (count.value > 99 ? '99+' : count.value.toString()))
</script>

<template>
  <template v-if="count > 0">
    <v-badge :content="shown" color="error" floating data-test="nav-badge">
      <v-icon :icon="item.icon" aria-hidden="true" />
    </v-badge>
    <span class="sr-only" data-test="nav-badge-spoken">, {{ count }} waiting</span>
  </template>
  <v-icon v-else :icon="item.icon" aria-hidden="true" />
</template>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
