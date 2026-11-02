<script setup lang="ts">
import { Fingerprint, MonitorSmartphone, Network, Server, Sparkles } from '@lucide/vue'
import { computed } from 'vue'

import type { Asset } from '@/api/assets'
import AssetSources from '@/components/AssetSources.vue'
import AssetStatusChip from '@/components/AssetStatusChip.vue'
import { addressesOf } from '@/inventory'
import { formatAgo, formatDateTime } from '@/format'

/**
 * An asset in a list: its name and what is known of what it is, whether it is on the network, its
 * addresses, the programs that list it and the interfaces it is on. On a computer these sit in
 * columns; on a phone they stack.
 */
const props = defineProps<{
  asset: Asset
  /** The names of the interfaces it is on. */
  interfaces: readonly string[]
}>()

const addresses = computed(() => addressesOf(props.asset))
const machine = computed(() => props.asset.kind === 'host')
/** Who made it, and its hardware address, when the name is not already one of them. */
const vendor = computed(() => (props.asset.name === props.asset.vendor ? null : props.asset.vendor))
const mac = computed(() => (props.asset.name === props.asset.mac ? null : props.asset.mac))
/** What a machine with no hardware address is: the program that lists it, and how it is doing. */
const kind = computed(() =>
  props.asset.listings
    .map(({ source_name, via_label, state }) =>
      [`${source_name} ${via_label.toLowerCase()}`, state].filter(Boolean).join(' · '),
    )
    .join(', '),
)
</script>

<template>
  <v-card class="asset" :class="`asset--${asset.status}`" data-test="asset-card">
    <div class="asset__main">
      <span class="asset__icon" aria-hidden="true">
        <v-icon :icon="machine ? Server : MonitorSmartphone" size="24" />
      </span>
      <div class="asset__who">
        <h3 class="asset__name text-title-large" data-test="asset-name">{{ asset.name }}</h3>
        <p
          v-if="machine || vendor || mac"
          class="asset__identity text-body-medium text-medium-emphasis"
          data-test="asset-identity"
        >
          <template v-if="machine">{{ kind }}</template>
          <template v-else>
            <span v-if="vendor">{{ vendor }}</span>
            <span v-if="vendor && mac" aria-hidden="true"> · </span>
            <span v-if="mac" class="asset__mono">{{ mac }}</span>
          </template>
        </p>
      </div>
      <div class="asset__state">
        <AssetStatusChip :status="asset.status" />
        <span class="text-body-medium text-medium-emphasis" data-test="asset-when">
          Listed
          <time :datetime="asset.last_seen_at" :title="formatDateTime(asset.last_seen_at)">{{
            formatAgo(asset.last_seen_at)
          }}</time>
        </span>
      </div>
    </div>

    <div v-if="asset.is_new || asset.private_mac || !asset.identified" class="asset__flags">
      <v-chip
        v-if="asset.is_new"
        :prepend-icon="Sparkles"
        color="warning"
        variant="tonal"
        size="small"
        data-test="asset-new"
      >
        New this week
      </v-chip>
      <v-chip
        v-if="asset.private_mac"
        :prepend-icon="Fingerprint"
        variant="tonal"
        size="small"
        data-test="asset-private"
      >
        Private hardware address
      </v-chip>
      <v-chip v-if="!asset.identified" variant="tonal" size="small" data-test="asset-unidentified">
        Nothing says what it is
      </v-chip>
    </div>

    <dl class="asset__facts">
      <div class="asset__fact">
        <dt class="text-label-large text-medium-emphasis">Addresses</dt>
        <dd class="asset__addresses" data-test="asset-addresses">
          <template v-if="addresses.shown.length">
            <span v-for="address in addresses.shown" :key="address" class="asset__mono">{{
              address
            }}</span>
            <span v-if="addresses.more > 0" class="text-medium-emphasis" data-test="asset-more">
              +{{ addresses.more }} more
            </span>
          </template>
          <span v-else class="text-medium-emphasis">None listed</span>
        </dd>
      </div>
      <div class="asset__fact">
        <dt class="text-label-large text-medium-emphasis">Listed by</dt>
        <dd><AssetSources :asset="asset" /></dd>
      </div>
      <div v-if="interfaces.length" class="asset__fact">
        <dt class="text-label-large text-medium-emphasis">On</dt>
        <dd class="asset__interfaces" data-test="asset-interfaces">
          <v-icon :icon="Network" size="16" aria-hidden="true" />
          {{ interfaces.join(', ') }}
        </dd>
      </div>
    </dl>
  </v-card>
</template>

<style scoped>
.asset {
  container-type: inline-size;
  position: relative;
  padding: 1rem;
  overflow: hidden;
}

@media (min-width: 600px) {
  .asset {
    padding: 1.25rem;
  }
}

/* The bar on the left says whether it is there at a glance, and the chip says it in words. */
.asset::before {
  content: '';
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 4px;
  background: rgba(var(--v-theme-on-surface), 0.2);
}

.asset--online::before {
  background: rgb(var(--v-theme-success));
}

.asset--recent::before {
  background: rgb(var(--v-theme-info));
}

.asset__main {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.25rem 0.875rem;
  align-items: start;
}

.asset__icon {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.asset__who {
  min-width: 0;
}

.asset__name {
  margin: 0;
  overflow-wrap: anywhere;
}

.asset__identity {
  margin: 0.125rem 0 0;
  overflow-wrap: anywhere;
}

.asset__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* Under the name on a phone; at the end of the row once there is room. */
.asset__state {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  margin-top: 0.5rem;
}

.asset__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.75rem;
}

.asset__facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem 1.5rem;
  margin: 1rem 0 0;
}

.asset__fact {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.asset__fact dt,
.asset__fact dd {
  margin: 0;
}

.asset__addresses {
  display: flex;
  flex-wrap: wrap;
  gap: 0.125rem 0.75rem;
  overflow-wrap: anywhere;
}

.asset__interfaces {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

@container (min-width: 44rem) {
  .asset__main {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .asset__state {
    grid-column: auto;
    flex-direction: column;
    align-items: flex-end;
    margin-top: 0;
  }

  .asset__facts {
    grid-template-columns: minmax(10rem, 1fr) minmax(0, 2fr) minmax(6rem, auto);
    align-items: start;
  }
}
</style>
