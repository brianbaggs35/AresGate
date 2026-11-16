<script setup lang="ts">
import { Plug } from '@lucide/vue'

/**
 * What a widget says in place of its chart when nothing that feeds it is connected: what it would
 * show, and what to connect to see it, with a way there.
 */
defineProps<{ title: string; words: string }>()
</script>

<template>
  <v-card class="needs pa-5 pa-sm-6" data-test="widget-needs">
    <span class="needs__icon" aria-hidden="true">
      <v-icon :icon="Plug" size="24" />
    </span>
    <div class="needs__text">
      <h2 class="text-title-medium">{{ title }}</h2>
      <p class="text-body-medium text-medium-emphasis" data-test="widget-needs-words">
        {{ words }}
      </p>
    </div>
    <v-btn variant="tonal" :to="{ name: 'integrations' }" data-test="widget-needs-link">
      Integrations
    </v-btn>
  </v-card>
</template>

<style scoped>
.needs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  height: 100%;
  border-style: dashed;
}

.needs__icon {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 0.875rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.needs__text {
  flex: 1;
  min-width: 12rem;
}

.needs__text h2,
.needs__text p {
  margin: 0;
}
</style>
