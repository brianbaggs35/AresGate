<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchChains, type Chain } from '@/api/threats'
import ChainCard from '@/components/ChainCard.vue'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/**
 * The attacks across two devices there are, at the top of the Threats page: an exploit at one
 * device and that device then calling out is one attack, and it is the most serious thing the
 * page can show. Nothing is drawn while there are none, and a failure to read them is not an
 * error of the page: the page's own threats are what it is for.
 */
const REFRESH_SECONDS = 30
const MOST = 6

const session = useSessionStore()
const items = ref<Chain[]>([])
const total = ref(0)

async function load() {
  try {
    const page = await session.call(() => fetchChains({ limit: MOST }))
    items.value = page.items
    total.value = page.total
  } catch {
    // What was shown stays: these are an addition to the page.
  }
}

onMounted(load)
usePolling(load, REFRESH_SECONDS * 1000)
</script>

<template>
  <section v-if="items.length" aria-labelledby="chains-title" class="chains" data-test="chains">
    <header>
      <h2 id="chains-title" class="text-title-large">Attacks across two devices</h2>
      <p class="text-body-medium text-medium-emphasis" data-test="chains-count">
        {{ formatCount(total) }} {{ total === 1 ? 'attack' : 'attacks' }} that got into a device
        from the internet and made it call out. Each is a threat.
      </p>
    </header>
    <ul class="chains__list">
      <li v-for="chain in items" :key="chain.id">
        <ChainCard :chain="chain" />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.chains {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.chains h2,
.chains p {
  margin: 0;
}

.chains__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
