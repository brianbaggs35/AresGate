<script setup lang="ts">
import { Network, UserPen } from '@lucide/vue'

import type { Through, ThroughRole } from '@/api/incidents'
import AssetCard from '@/components/AssetCard.vue'
import { formatCount } from '@/format'

/**
 * The devices an incident went through or touched, in the order it met them: the firewall that
 * the internet's traffic crosses, the device it was for or came from, and any other device that
 * turned up in it. Each is listed as the Assets page lists it, with what the owner said it is, so a
 * router reads as a router and a camera as a camera. A device nobody has said anything about
 * asks to be classified, because the analyst reads the same incident differently for a camera
 * than for a laptop. An address that no asset has is said so rather than hidden.
 */
defineProps<{ through: readonly Through[] }>()

const WHAT: Record<ThroughRole, string> = {
  gateway: 'Crossed on the way',
  target: 'The device it was about',
  also: 'Also in it',
}

function mentions(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'alert names' : 'alerts name'} it`
}
</script>

<template>
  <ol class="through" aria-label="The devices it went through, in order" data-test="through">
    <li
      v-for="(stop, index) in through"
      :key="`${stop.role}-${stop.address}-${index}`"
      class="through__stop"
      :data-role="stop.role"
      data-test="through-stop"
    >
      <p class="through__what text-label-large text-medium-emphasis">
        <span data-test="through-role">{{ WHAT[stop.role] }}</span>
        <span aria-hidden="true"> · </span>
        <span data-test="through-signals">{{ mentions(stop.signals) }}</span>
      </p>

      <template v-if="stop.asset">
        <AssetCard :asset="stop.asset" :interfaces="[]" />
        <p v-if="!stop.asset.profile" class="through__ask text-body-medium">
          <v-icon :icon="UserPen" size="18" aria-hidden="true" />
          <router-link
            :to="{ name: 'asset', params: { key: stop.asset.key } }"
            data-test="through-classify"
          >
            Say what it is
          </router-link>
          <span class="text-medium-emphasis">
            so the analyst reads this the way it should be read.
          </span>
        </p>
      </template>
      <v-card v-else class="through__bare" variant="tonal" data-test="through-bare">
        <v-icon :icon="Network" size="24" aria-hidden="true" />
        <div>
          <p class="text-title-medium through__address" data-test="through-address">
            {{ stop.address }}
          </p>
          <p class="text-body-medium text-medium-emphasis">
            Not on the Assets list: nothing connected has listed this address as a device.
          </p>
        </div>
      </v-card>
    </li>
  </ol>
</template>

<style scoped>
.through {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.through__stop {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}

.through__what {
  margin: 0;
}

.through__ask {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  margin: 0;
}

.through__bare {
  display: flex;
  gap: 0.875rem;
  align-items: center;
  padding: 1rem;
}

.through__bare p {
  margin: 0;
}

.through__address {
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}
</style>
