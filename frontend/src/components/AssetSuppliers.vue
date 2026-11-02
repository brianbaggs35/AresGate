<script setup lang="ts">
import { CircleCheck, CircleDashed } from '@lucide/vue'
import { RouterLink } from 'vue-router'

import type { Supplier } from '@/api/assets'
import { formatCount, formatList } from '@/format'

/**
 * Where the assets come from: the programs that can list devices, whether each is connected, how
 * it lists them and how many it lists. It is why a device may be missing (nothing that could see
 * it is connected) and where to go to change that.
 */
defineProps<{ suppliers: readonly Supplier[] }>()
</script>

<template>
  <section aria-labelledby="assets-suppliers" class="suppliers" data-test="suppliers">
    <h2 id="assets-suppliers" class="text-title-large">Where the assets come from</h2>
    <p class="text-body-medium text-medium-emphasis">
      Each program lists the devices it can see. What they say about one device is put together
      here, so a device that two of them list is shown once.
    </p>
    <ul class="suppliers__list">
      <li
        v-for="supplier in suppliers"
        :key="supplier.key"
        class="suppliers__item"
        :data-test="`supplier-${supplier.key}`"
      >
        <v-icon
          :icon="supplier.connected ? CircleCheck : CircleDashed"
          :color="supplier.connected ? 'success' : undefined"
          size="20"
          aria-hidden="true"
        />
        <div class="suppliers__text">
          <RouterLink
            :to="{ name: 'integration', params: { key: supplier.key } }"
            class="text-title-medium"
            :data-test="`supplier-link-${supplier.key}`"
            >{{ supplier.name }}</RouterLink
          >
          <p class="text-body-medium text-medium-emphasis">
            <span data-test="supplier-state">{{
              supplier.connected ? 'Connected' : 'Not connected'
            }}</span>
            · lists {{ formatList(supplier.ways) }}
            <template v-if="supplier.connected || supplier.assets > 0">
              · <span data-test="supplier-count">{{ formatCount(supplier.assets) }}</span>
              {{ supplier.assets === 1 ? 'asset' : 'assets' }}
              <template v-if="!supplier.connected">listed while it was connected</template>
            </template>
          </p>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.suppliers h2,
.suppliers p {
  margin: 0;
}

.suppliers__list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.suppliers__item {
  display: flex;
  gap: 0.625rem;
  align-items: flex-start;
  min-width: 0;
}

.suppliers__item > .v-icon {
  margin-top: 0.125rem;
}

.suppliers__text {
  min-width: 0;
}

.suppliers__text a {
  color: inherit;
}
</style>
