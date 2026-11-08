<script setup lang="ts">
import { ref, watch } from 'vue'

import type { Exposure } from '@/api/threatSettings'
import SectionCard from '@/components/SectionCard.vue'
import { EXPOSURE_CHOICES, portsOf } from '@/threats'

/**
 * What the network is like, so that what is normal on it is known: whether anything is open to the
 * internet, which ports, and anything else worth knowing. The AI is told this when it judges a kind
 * of incident, which is what lets the same scan be background on a network with nothing open and
 * a threat on one that runs a service. Nothing is kept until the page saves.
 */
const props = defineProps<{
  exposure: Exposure
  ports: readonly number[]
  notes: string
  maxPorts: number
  maxNotes: number
}>()
const emit = defineEmits<{
  'update:exposure': [Exposure]
  'update:ports': [number[]]
  'update:notes': [string]
}>()

const text = ref(props.ports.join(', '))
/** The words in the field that are not a port, while there are any. */
const bad = ref<string[]>([])
const tooMany = ref(false)

// The field says what the ports are, except while it is being typed into: when they change from
// outside (the changes were discarded), it says them again.
watch(
  () => props.ports,
  (ports) => {
    const now = portsOf(text.value)
    if (now.bad.length === 0 && now.ports.join() === ports.join()) return
    text.value = ports.join(', ')
    bad.value = []
    tooMany.value = false
  },
)

function type(value: string) {
  text.value = value
  const found = portsOf(value)
  bad.value = found.bad
  tooMany.value = found.ports.length > props.maxPorts
  if (found.bad.length === 0 && !tooMany.value) emit('update:ports', found.ports)
}

const error = () => {
  if (bad.value.length)
    return `${bad.value.join(', ')} ${bad.value.length === 1 ? 'is' : 'are'} not a port number (1 to 65535).`
  return tooMany.value ? `At most ${props.maxPorts.toString()} ports.` : ''
}
</script>

<template>
  <SectionCard
    title="Your network"
    description="What is normal here. The same scan means little on a network with nothing open to the internet, and a lot on one that runs a service."
    data-test="threat-network-card"
  >
    <v-radio-group
      :model-value="exposure"
      hide-details
      aria-label="What is open to the internet"
      data-test="threat-exposure"
      @update:model-value="emit('update:exposure', $event as Exposure)"
    >
      <v-radio
        v-for="choice in EXPOSURE_CHOICES"
        :key="choice.value"
        :value="choice.value"
        :data-test="`exposure-${choice.value}`"
      >
        <template #label>
          <span>
            <span class="text-body-large">{{ choice.title }}</span>
            <span class="network__detail text-body-medium text-medium-emphasis">{{
              choice.detail
            }}</span>
          </span>
        </template>
      </v-radio>
    </v-radio-group>

    <v-text-field
      v-if="exposure === 'some'"
      label="Ports that are open to the internet"
      placeholder="22, 443, 51820"
      :model-value="text"
      :error-messages="error()"
      hint="Separate them with commas."
      class="mt-4"
      data-test="threat-ports"
      @update:model-value="type($event ?? '')"
    />

    <v-textarea
      label="Anything else about your network"
      :model-value="notes"
      :counter="maxNotes"
      :maxlength="maxNotes"
      rows="3"
      auto-grow
      placeholder="A Plex server on 32400, a camera that talks to a cloud service, a VPN to the office."
      class="mt-4"
      data-test="threat-notes"
      @update:model-value="emit('update:notes', $event ?? '')"
    />
  </SectionCard>
</template>

<style scoped>
.network__detail {
  display: block;
}
</style>
