<script setup lang="ts">
import type { AssetPeer } from '@/api/assets'
import { formatAgo, formatCount } from '@/format'

/**
 * The other addresses an asset's traffic went to, and the ones that sent it traffic, over the last
 * week, the most often seen first.
 */
defineProps<{ talksTo: readonly AssetPeer[]; contactedBy: readonly AssetPeer[] }>()

function events(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'event' : 'events'}`
}
</script>

<template>
  <div class="peers">
    <section class="peers__side" aria-labelledby="talks-to-title">
      <h3 id="talks-to-title" class="text-title-medium">Talks to</h3>
      <ul v-if="talksTo.length" class="peers__items" data-test="asset-talks-to">
        <li v-for="item in talksTo" :key="item.address" class="peer" data-test="asset-peer">
          <span class="peer__address">{{ item.address }}</span>
          <span class="text-body-medium text-medium-emphasis">
            {{ events(item.events) }}, {{ formatAgo(item.last_seen_at) }}
          </span>
        </li>
      </ul>
      <p v-else class="text-body-medium text-medium-emphasis" data-test="asset-talks-to-none">
        Nothing in the last week.
      </p>
    </section>

    <section class="peers__side" aria-labelledby="contacted-by-title">
      <h3 id="contacted-by-title" class="text-title-medium">Contacted by</h3>
      <ul v-if="contactedBy.length" class="peers__items" data-test="asset-contacted-by">
        <li v-for="item in contactedBy" :key="item.address" class="peer" data-test="asset-peer">
          <span class="peer__address">{{ item.address }}</span>
          <span class="text-body-medium text-medium-emphasis">
            {{ events(item.events) }}, {{ formatAgo(item.last_seen_at) }}
          </span>
        </li>
      </ul>
      <p v-else class="text-body-medium text-medium-emphasis" data-test="asset-contacted-by-none">
        Nothing in the last week.
      </p>
    </section>
  </div>
</template>

<style scoped>
.peers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1.5rem;
}

.peers__side h3 {
  margin: 0 0 0.5rem;
}

.peers__items {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.peer {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0;
}

.peer + .peer {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.peer__address {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}
</style>
