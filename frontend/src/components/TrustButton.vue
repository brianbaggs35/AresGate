<script setup lang="ts">
import { ShieldCheck } from '@lucide/vue'
import { computed, ref } from 'vue'

import type { Trust } from '@/api/trust'
import TrustDialog from '@/components/TrustDialog.vue'
import { scopesFor } from '@/trust'

/**
 * A "Trust" button for an address on a page: it opens the question of what to trust about it (all
 * of it, or only the alert it was or only what a device sent to it) and how much. It says
 * `trusted` once the answer is saved, for the page to read again.
 */
const props = defineProps<{
  address: string
  /** The device on your network that sent to it, where that is known. */
  device?: { address: string; name?: string | null } | null
  /** The alert it was about, where there is one. */
  signature?: string | null
  /** A smaller button, for a list. */
  small?: boolean
}>()
const emit = defineEmits<{ trusted: [rule: Trust] }>()

const open = ref(false)
const scopes = computed(() =>
  scopesFor({ address: props.address, device: props.device, signature: props.signature }),
)
</script>

<template>
  <v-btn
    variant="tonal"
    color="success"
    :size="small ? 'small' : 'default'"
    :prepend-icon="ShieldCheck"
    :aria-label="`Trust ${address}`"
    data-test="trust-button"
    @click.stop="open = true"
  >
    Trust
  </v-btn>
  <TrustDialog v-model="open" :scopes="scopes" @trusted="emit('trusted', $event)" />
</template>
