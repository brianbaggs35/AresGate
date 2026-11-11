<script setup lang="ts">
import type { AssetPeer } from '@/api/assets'
import { formatAgo, formatCount } from '@/format'
import { describePort } from '@/ports'
import { JUDGEMENT, RULING } from '@/threatIntel'

/**
 * The other addresses an asset's traffic went to, and the ones that sent it traffic, over the last
 * week, the most often seen first. Each says which ports the traffic used at the far end, and what
 * threat intelligence has kept of the address: its judgement and the counts behind it, or what the
 * owner ruled of it, which stands over them. A peer on a
 * network of its own is never sent to a service, so it says it is on the network. A public peer
 * with nothing kept says so, and shows no judgement of its own.
 */
defineProps<{ talksTo: readonly AssetPeer[]; contactedBy: readonly AssetPeer[] }>()

function events(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'event' : 'events'}`
}

/** How many engines flagged the address, of how many gave a verdict. */
function flagged(peer: AssetPeer): string {
  const standing = peer.standing
  if (!standing || standing.reported === 'unknown') return ''
  return `${formatCount(standing.malicious + standing.suspicious)} of ${formatCount(standing.engines)} engines flagged it`
}

/** What the owner ruled of the address, if they did: it stands over what the service said. */
function ruled(peer: AssetPeer): string {
  const ruling = peer.standing?.ruling
  return ruling ? RULING[ruling].label : ''
}

/** Who owns the address, when threat intelligence says. */
function owner(peer: AssetPeer): string {
  const standing = peer.standing
  if (!standing) return ''
  return [standing.owner, standing.country].filter(Boolean).join(', ')
}
</script>

<template>
  <div class="peers">
    <section class="peers__side" aria-labelledby="talks-to-title">
      <h3 id="talks-to-title" class="text-title-medium">Talks to</h3>
      <ul v-if="talksTo.length" class="peers__items" data-test="asset-talks-to">
        <li v-for="item in talksTo" :key="item.address" class="peer" data-test="asset-peer">
          <span class="peer__head">
            <span class="peer__address">{{ item.address }}</span>
            <v-chip
              v-if="item.standing"
              :color="JUDGEMENT[item.standing.judgement].color"
              :prepend-icon="JUDGEMENT[item.standing.judgement].icon"
              variant="tonal"
              size="small"
              data-test="peer-standing"
              :data-judgement="item.standing.judgement"
            >
              {{ JUDGEMENT[item.standing.judgement].short }}
            </v-chip>
            <v-chip
              v-else-if="item.internal"
              size="small"
              variant="outlined"
              data-test="peer-internal"
            >
              On your network
            </v-chip>
            <v-chip v-else size="small" variant="outlined" data-test="peer-unchecked">
              Not checked yet
            </v-chip>
          </span>
          <span class="text-body-medium text-medium-emphasis">
            {{ events(item.events) }}, {{ formatAgo(item.last_seen_at) }}
          </span>
          <span v-if="item.ports.length" class="peer__ports text-body-small" data-test="peer-ports">
            <v-chip
              v-for="port in item.ports"
              :key="`${port.protocol}-${port.port}`"
              size="x-small"
              label
            >
              {{ describePort(port.port, port.protocol) }}
            </v-chip>
          </span>
          <span
            v-if="ruled(item) || flagged(item) || owner(item)"
            class="peer__intel text-body-small text-medium-emphasis"
            data-test="peer-intel"
          >
            {{ [ruled(item), flagged(item), owner(item)].filter(Boolean).join(' · ') }}
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
          <span class="peer__head">
            <span class="peer__address">{{ item.address }}</span>
            <v-chip
              v-if="item.standing"
              :color="JUDGEMENT[item.standing.judgement].color"
              :prepend-icon="JUDGEMENT[item.standing.judgement].icon"
              variant="tonal"
              size="small"
              data-test="peer-standing"
              :data-judgement="item.standing.judgement"
            >
              {{ JUDGEMENT[item.standing.judgement].short }}
            </v-chip>
            <v-chip
              v-else-if="item.internal"
              size="small"
              variant="outlined"
              data-test="peer-internal"
            >
              On your network
            </v-chip>
            <v-chip v-else size="small" variant="outlined" data-test="peer-unchecked">
              Not checked yet
            </v-chip>
          </span>
          <span class="text-body-medium text-medium-emphasis">
            {{ events(item.events) }}, {{ formatAgo(item.last_seen_at) }}
          </span>
          <span v-if="item.ports.length" class="peer__ports text-body-small" data-test="peer-ports">
            <v-chip
              v-for="port in item.ports"
              :key="`${port.protocol}-${port.port}`"
              size="x-small"
              label
            >
              {{ describePort(port.port, port.protocol) }}
            </v-chip>
          </span>
          <span
            v-if="ruled(item) || flagged(item) || owner(item)"
            class="peer__intel text-body-small text-medium-emphasis"
            data-test="peer-intel"
          >
            {{ [ruled(item), flagged(item), owner(item)].filter(Boolean).join(' · ') }}
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

.peer__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.peer__ports {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.25rem;
}

.peer__intel {
  margin-top: 0.125rem;
}

.peer__address {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}
</style>
