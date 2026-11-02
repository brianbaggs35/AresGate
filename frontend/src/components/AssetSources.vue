<script setup lang="ts">
import { computed } from 'vue'

import type { Asset } from '@/api/assets'
import { sourcesOf } from '@/inventory'
import { formatAgo, formatDateTime } from '@/format'

/**
 * The programs that list an asset, each once, with the ways it does: "OPNsense: ARP table, DHCP
 * leases". A machine that was merged into a device says what it was matched by, since that is a
 * guess from its address or name and not a fact the program gave.
 */
const props = defineProps<{ asset: Pick<Asset, 'listings'> }>()

const sources = computed(() => sourcesOf(props.asset))
</script>

<template>
  <ul v-if="sources.length" class="asset-sources" data-test="asset-sources">
    <li v-for="source in sources" :key="source.key" class="asset-sources__source">
      <v-chip variant="outlined" size="small" :data-test="`asset-source-${source.key}`">
        <span class="asset-sources__name">{{ source.name }}</span>
        <span class="asset-sources__ways text-medium-emphasis">{{ source.ways.join(', ') }}</span>
        <span class="sr-only">, last listed</span>
        <time
          class="asset-sources__time text-medium-emphasis"
          :datetime="source.last_seen_at"
          :title="formatDateTime(source.last_seen_at)"
          >{{ formatAgo(source.last_seen_at) }}</time
        >
      </v-chip>
    </li>
  </ul>
  <p v-else class="text-body-medium text-medium-emphasis" data-test="asset-no-sources">
    No program has said how it found this yet.
  </p>
</template>

<style scoped>
.asset-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* A chip with several ways listed grows to a second line instead of running off a phone. */
.asset-sources :deep(.v-chip) {
  height: auto;
  min-height: 1.75rem;
  padding-block: 0.25rem;
}

.asset-sources :deep(.v-chip__content) {
  white-space: normal;
}

.asset-sources__name {
  font-weight: 500;
}

.asset-sources__ways::before,
.asset-sources__time::before {
  content: '·';
  margin-inline: 0.375rem;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
