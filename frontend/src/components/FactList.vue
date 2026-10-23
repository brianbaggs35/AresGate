<script setup lang="ts">
/**
 * Facts as a list of labelled values, such as the versions on the status page: the label beside
 * its value where there's room, and above it on a phone.
 */
defineProps<{
  facts: readonly { id: string; label: string; value: string }[]
}>()
</script>

<template>
  <dl class="fact-list">
    <div v-for="fact in facts" :key="fact.id" class="fact-list__row" :data-test="`fact-${fact.id}`">
      <dt class="text-body-medium text-medium-emphasis" data-test="fact-label">{{ fact.label }}</dt>
      <dd class="text-body-large" data-test="fact-value">{{ fact.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.fact-list {
  margin: 0;
}

.fact-list__row {
  display: grid;
  grid-template-columns: minmax(7rem, 12rem) minmax(0, 1fr);
  gap: 0.25rem 1rem;
  padding: 0.5rem 0;
}

.fact-list__row + .fact-list__row {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.fact-list dd {
  margin: 0;
  overflow-wrap: anywhere;
}

@media (max-width: 599px) {
  .fact-list__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
