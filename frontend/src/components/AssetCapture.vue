<script setup lang="ts">
import { Radio } from '@lucide/vue'
import { ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { MAX_CAPTURE_SECONDS, takeCapture, type Capture, type CapturedPacket } from '@/api/captures'
import SectionCard from '@/components/SectionCard.vue'
import { formatBytes, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Raw data from the network for one asset: ntopng listens to its address for a few seconds, and
 * the packets are shown as they were, who sent each to whom, over what, how big it was, the flags
 * of a TCP segment and the first bytes it carried. It is for looking, at what a camera is doing
 * when it should be asleep, say. Nothing of the capture is kept and it never goes to an AI, and
 * encrypted traffic shows as it is, bytes that mean nothing.
 */
const props = defineProps<{ addresses: readonly string[] }>()

const SECONDS = [5, 10, 20, MAX_CAPTURE_SECONDS]

const session = useSessionStore()
const address = ref(props.addresses[0] ?? '')
const seconds = ref(10)
const running = ref(false)
const failure = ref<string | null>(null)
const result = ref<Capture | null>(null)

// A page for another asset starts clear: what was captured was another host's.
watch(
  () => props.addresses.join(','),
  () => {
    if (!props.addresses.includes(address.value)) address.value = props.addresses[0] ?? ''
    result.value = null
    failure.value = null
  },
)

/** Listens, and shows what came. A failure says why, in ntopng's words where it gave them. */
async function capture() {
  running.value = true
  failure.value = null
  try {
    result.value = await session.change((token) => takeCapture(address.value, seconds.value, token))
  } catch (error) {
    result.value = null
    failure.value = errorMessage(error)
  } finally {
    running.value = false
  }
}

/** Where a packet came from or went to, with its port where it has one. */
function end(address: string, port: number | null): string {
  if (port === null) return address
  return address.includes(':') ? `[${address}]:${port}` : `${address}:${port}`
}

/** What it is: its protocol, then its flags where it has some. */
function what(packet: CapturedPacket): string {
  return packet.flags ? `${packet.protocol} ${packet.flags}` : packet.protocol
}

/** The packets as rows: each with how long after the first it came, in seconds. */
function rowsOf(found: Capture): { packet: CapturedPacket; offset: string }[] {
  const first = Math.min(...found.packets.map((each) => Date.parse(each.at)))
  return found.packets.map((packet) => ({
    packet,
    offset: `+${((Date.parse(packet.at) - first) / 1000).toFixed(3)}`,
  }))
}

function summaryOf(found: Capture): string {
  if (found.total === 0) return `No packet to or from ${found.host} in ${found.seconds} seconds.`
  const packets = `${formatCount(found.total)} ${found.total === 1 ? 'packet' : 'packets'}`
  return `${packets} to or from ${found.host} in ${found.seconds} seconds, ${formatBytes(found.bytes)} in the capture.`
}

/** What is left out of what is shown, as sentences. */
function notesOf(found: Capture): string {
  const said: string[] = []
  if (found.total > found.packets.length) {
    said.push(`The first ${formatCount(found.packets.length)} are listed.`)
  }
  if (found.cut) said.push('ntopng sent more than AresGate reads, so the end is missing.')
  if (found.skipped) {
    said.push(
      `${formatCount(found.skipped)} ${found.skipped === 1 ? 'frame is' : 'frames are'} neither IP nor ARP and ${found.skipped === 1 ? "isn't" : "aren't"} shown.`,
    )
  }
  return said.join(' ')
}
</script>

<template>
  <SectionCard
    title="Packets"
    description="Have ntopng listen to this device for a few seconds and show what it saw. Nothing is kept, and the packets are not sent to an AI."
    data-test="asset-capture"
  >
    <div class="controls">
      <v-select
        v-if="addresses.length > 1"
        v-model="address"
        :items="[...addresses]"
        label="Address"
        density="comfortable"
        hide-details
        class="controls__address"
        data-test="capture-address"
      />
      <v-btn-toggle
        v-model="seconds"
        mandatory
        density="comfortable"
        variant="outlined"
        divided
        aria-label="How long to listen"
        data-test="capture-seconds"
      >
        <v-btn v-for="item in SECONDS" :key="item" :value="item" :aria-pressed="seconds === item">
          {{ item }} s
        </v-btn>
      </v-btn-toggle>
      <v-btn
        color="primary"
        :prepend-icon="Radio"
        :loading="running"
        :disabled="!address"
        data-test="capture-start"
        @click="capture"
      >
        Capture packets
      </v-btn>
    </div>

    <output v-if="running" class="listening text-body-medium text-medium-emphasis mt-3">
      Listening for {{ seconds }} seconds…
    </output>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="comfortable"
      class="mt-4"
      data-test="capture-failure"
    >
      {{ failure }}
    </v-alert>

    <div v-if="result" class="result" data-test="capture-result">
      <p class="text-body-large" data-test="capture-summary">{{ summaryOf(result) }}</p>
      <ul v-if="result.protocols.length" class="chips" aria-label="Protocols">
        <li v-for="item in result.protocols" :key="item.protocol">
          <v-chip size="small" variant="tonal" data-test="capture-protocol">
            {{ item.protocol }} {{ formatCount(item.packets) }}
          </v-chip>
        </li>
      </ul>
      <p
        v-if="notesOf(result)"
        class="text-body-medium text-medium-emphasis"
        data-test="capture-notes"
      >
        {{ notesOf(result) }}
      </p>
      <div v-if="result.packets.length" class="scroll">
        <v-table density="compact" data-test="capture-packets">
          <caption class="sr-only">
            Packets captured
          </caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">From</th>
              <th scope="col">To</th>
              <th scope="col">Protocol</th>
              <th scope="col">Size</th>
              <th scope="col">Data</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rowsOf(result)" :key="index" data-test="capture-packet">
              <td class="mono">{{ row.offset }}</td>
              <td class="mono">{{ end(row.packet.source, row.packet.source_port) }}</td>
              <td class="mono">{{ end(row.packet.destination, row.packet.destination_port) }}</td>
              <td>{{ what(row.packet) }}</td>
              <td>{{ formatBytes(row.packet.length) }}</td>
              <td class="mono preview">{{ row.packet.preview }}</td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </div>
  </SectionCard>
</template>

<style scoped>
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.controls__address {
  max-width: 260px;
}

.listening {
  display: block;
}

.result {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.scroll {
  overflow-x: auto;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: nowrap;
}

.preview {
  max-width: 28rem;
  overflow: hidden;
  text-overflow: ellipsis;
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
