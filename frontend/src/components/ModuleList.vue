<script setup lang="ts">
import { computed } from 'vue'

import type { Module } from '@/api/integrations'
import { MODULE_STATE } from '@/integrations'

/**
 * The services that run on a system, such as Suricata and CrowdSec on OPNsense. Testing the
 * connection finds out which are there; each that is can be switched off if AresGate shouldn't
 * read it.
 */
const props = defineProps<{ modules: readonly Module[]; idPrefix: string }>()
/** The keys of the services that are switched off. */
const off = defineModel<string[]>({ required: true })

const checked = computed(() => props.modules.some((module) => module.state !== null))

function toggle(key: string, on: boolean | null) {
  const rest = off.value.filter((item) => item !== key)
  off.value = on ? rest : [...rest, key]
}
</script>

<template>
  <section class="module-list" :aria-labelledby="`${idPrefix}-services`" data-test="modules">
    <h3 :id="`${idPrefix}-services`" class="text-title-medium mb-1">Services</h3>
    <p class="text-body-medium text-medium-emphasis mb-2" data-test="modules-help">
      <template v-if="checked">
        What testing found on this system. AresGate only reads from the services that are switched
        on.
      </template>
      <template v-else>
        Test the connection to find which of these are installed. AresGate only reads from the
        services that are switched on.
      </template>
    </p>
    <ul class="module-list__items">
      <li v-for="module in modules" :key="module.key" class="module-list__item" data-test="module">
        <div class="module-list__text">
          <div class="module-list__name">
            <span class="text-body-large" data-test="module-name">{{ module.label }}</span>
            <v-chip
              v-if="module.state"
              :color="MODULE_STATE[module.state].color"
              size="small"
              variant="tonal"
              data-test="module-state"
            >
              {{ MODULE_STATE[module.state].label }}
            </v-chip>
          </div>
          <div class="text-body-medium text-medium-emphasis">{{ module.summary }}</div>
        </div>
        <v-switch
          :model-value="!off.includes(module.key)"
          :aria-label="`Read ${module.label}`"
          :disabled="module.state === 'not_installed'"
          color="primary"
          density="compact"
          hide-details
          inset
          data-test="module-switch"
          @update:model-value="toggle(module.key, $event)"
        />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.module-list__items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.module-list__item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.625rem 0;
}

.module-list__item + .module-list__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.module-list__text {
  flex: 1;
  min-width: 0;
}

.module-list__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.module-list__item :deep(.v-switch) {
  flex: none;
}
</style>
