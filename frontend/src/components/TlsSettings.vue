<script setup lang="ts">
import { Info, SearchCheck } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'

import { ApiError, errorMessage } from '@/api/client'
import {
  lookUpCertificate,
  type CertificateChoice,
  type CertificateReview as Review,
  type TlsMode,
} from '@/api/integrations'
import CertificateReview from '@/components/CertificateReview.vue'
import { sameFingerprint } from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * How AresGate knows it is talking to the right device. Most devices at home use a certificate
 * they made for themselves, which no certificate authority vouches for. So the certificate the
 * device presents can be looked up whatever is chosen, reviewed, and trusted in one click (it is
 * pinned by its fingerprint). The ways of checking stay as they were: the certificates this
 * computer trusts, a certificate authority that is pasted, or one certificate pinned by its
 * fingerprint, typed in.
 */
const props = defineProps<{
  integration: string
  /** The connection's address, which a certificate is looked up at. */
  url: string
  /** Makes the ids of the fields unique on a page with several connections. */
  idPrefix: string
  /** What is wrong, by field name. */
  problems: Readonly<Record<string, string>>
  /** What this product's documentation adds about its certificate, if anything. */
  note?: string
  /** Whether the connection is saved, so that trusting a certificate can test it right away. */
  canTest?: boolean
}>()
const emit = defineEmits<{
  /** A certificate was trusted, and whether to save and test the connection straight after. */
  trusted: [test: boolean]
}>()
const mode = defineModel<TlsMode>('mode', { required: true })
const authority = defineModel<string>('authority', { required: true })
const fingerprint = defineModel<string>('fingerprint', { required: true })

const session = useSessionStore()

const section = ref<HTMLElement | null>(null)
const panel = ref<{ focus: () => void } | null>(null)
const found = ref<Review | null>(null)
/** How the certificate was set to be checked when it was looked up, which its verdict is about. */
const lookedUpWith = ref<CertificateChoice | null>(null)
const looking = ref(false)
const lookupError = ref<string | null>(null)

// What was found belongs to the address it was found at.
watch(
  () => props.url,
  () => {
    found.value = null
    lookupError.value = null
  },
)

async function lookUp() {
  looking.value = true
  lookupError.value = null
  found.value = null
  const choice = {
    mode: mode.value,
    authority: authority.value,
    fingerprint: fingerprint.value,
  }
  try {
    found.value = await session.change((token) =>
      lookUpCertificate(props.integration, props.url.trim(), choice, token),
    )
    lookedUpWith.value = choice
  } catch (error) {
    // This route says what is wrong with the address in words, as its one problem.
    lookupError.value =
      (error instanceof ApiError && error.problems[0]?.message) || errorMessage(error)
  } finally {
    looking.value = false
  }
}

/** Looks the certificate up and brings it into view, for a button elsewhere on the page. */
async function review() {
  section.value?.scrollIntoView({ block: 'nearest' })
  await lookUp()
  await nextTick()
  panel.value?.focus()
}
defineExpose({ review })

/** Whether the certificate found is the one trusted (pinned), however its fingerprint is written. */
const trusted = computed(
  () =>
    found.value !== null &&
    mode.value === 'pinned' &&
    sameFingerprint(fingerprint.value, found.value.fingerprint),
)

/** What the way of checking makes of the certificate found: only while it is chosen as it was
 * when the certificate was looked up. */
const verdict = computed(() => {
  const was = lookedUpWith.value
  if (!found.value || was?.mode !== mode.value) return null
  if (mode.value === 'ca' && was.authority !== authority.value) return null
  if (mode.value === 'pinned' && was.fingerprint !== fingerprint.value) return null
  return { accepted: found.value.accepted, text: found.value.verdict }
})

function trust(test: boolean) {
  if (!found.value) return
  mode.value = 'pinned'
  fingerprint.value = found.value.fingerprint
  emit('trusted', test)
}
</script>

<template>
  <fieldset ref="section" class="tls" :data-test="`${idPrefix}-tls`">
    <legend class="text-title-medium mb-1">Certificate</legend>
    <p class="text-body-medium text-medium-emphasis mb-3">
      How AresGate knows this is the right device. OPNsense, Wazuh and many others make a
      certificate for themselves that nothing else vouches for. Look up the one the device presents,
      compare its fingerprint with the device's own, and trust it: whatever it is, even a
      self-signed one.
    </p>
    <v-alert
      v-if="note"
      type="info"
      variant="tonal"
      density="compact"
      :icon="Info"
      class="mb-3"
      data-test="tls-note"
    >
      {{ note }}
    </v-alert>

    <div class="d-flex flex-wrap align-center ga-3">
      <v-btn
        variant="tonal"
        :prepend-icon="SearchCheck"
        :loading="looking"
        :disabled="url.trim() === ''"
        class="tls__look-up"
        data-test="tls-look-up"
        @click="lookUp"
      >
        Look up the certificate
      </v-btn>
      <span v-if="url.trim() === ''" class="text-body-medium text-medium-emphasis">
        Enter the address first.
      </span>
    </div>

    <v-alert
      v-if="lookupError"
      type="error"
      variant="tonal"
      density="compact"
      class="mt-4"
      data-test="tls-look-up-error"
    >
      {{ lookupError }}
    </v-alert>

    <CertificateReview
      v-if="found"
      ref="panel"
      :address="url.trim()"
      :certificate="found"
      :verdict="verdict"
      :trusted="trusted"
      :can-test="canTest === true"
      class="mt-4"
      @trust="trust"
    />

    <h4 class="text-title-small mt-6 mb-1">How it is checked</h4>
    <v-radio-group
      v-model="mode"
      :error-messages="problems.tls_mode"
      hide-details="auto"
      data-test="tls-mode"
    >
      <v-radio value="system" data-test="tls-system">
        <template #label>
          <span>
            <span class="d-block text-body-large">The certificates this computer trusts</span>
            <span class="d-block text-body-medium text-medium-emphasis">
              For a certificate from a public authority, such as Let's Encrypt.
            </span>
          </span>
        </template>
      </v-radio>
      <v-radio value="ca" data-test="tls-ca">
        <template #label>
          <span>
            <span class="d-block text-body-large">A certificate authority I paste</span>
            <span class="d-block text-body-medium text-medium-emphasis">
              For devices whose certificate comes from your own authority.
            </span>
          </span>
        </template>
      </v-radio>
      <v-radio value="pinned" data-test="tls-pinned">
        <template #label>
          <span>
            <span class="d-block text-body-large">Only this exact certificate</span>
            <span class="d-block text-body-medium text-medium-emphasis">
              For a self-signed certificate. Nothing else is accepted, even if it looks valid.
            </span>
          </span>
        </template>
      </v-radio>
    </v-radio-group>

    <v-textarea
      v-if="mode === 'ca'"
      :id="`${idPrefix}-tls_ca_pem`"
      v-model="authority"
      label="Certificate authority (PEM)"
      hint="Paste the whole certificate, from -----BEGIN CERTIFICATE----- to -----END CERTIFICATE-----. Never paste a private key."
      persistent-hint
      rows="5"
      auto-grow
      spellcheck="false"
      autocomplete="off"
      class="tls__pem mt-4"
      :error-messages="problems.tls_ca_pem"
      data-test="tls-ca-pem"
    />

    <v-text-field
      v-else-if="mode === 'pinned'"
      :id="`${idPrefix}-tls_fingerprint`"
      v-model="fingerprint"
      label="SHA-256 fingerprint"
      placeholder="AA:BB:CC:…"
      hint="Type it in, or look up the certificate above and trust it."
      persistent-hint
      spellcheck="false"
      autocomplete="off"
      class="tls__fingerprint mt-4"
      :error-messages="problems.tls_fingerprint"
      data-test="tls-fingerprint"
    />
  </fieldset>
</template>

<style scoped>
.tls {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.tls legend {
  padding: 0;
}

.tls__pem :deep(textarea),
.tls__fingerprint :deep(input) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
}

@media (max-width: 599px) {
  .tls__look-up {
    width: 100%;
  }
}
</style>
