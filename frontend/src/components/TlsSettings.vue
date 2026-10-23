<script setup lang="ts">
import { SearchCheck, ShieldCheck, TriangleAlert } from '@lucide/vue'
import { ref, watch } from 'vue'

import { ApiError, errorMessage } from '@/api/client'
import { lookUpCertificate, type Certificate, type TlsMode } from '@/api/integrations'
import { formatDateTime } from '@/format'
import { sameFingerprint } from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * How AresGate knows it is talking to the right device. Most devices at home use a certificate
 * they made for themselves, which no certificate authority vouches for, so besides the ones this
 * computer trusts, a certificate authority can be pasted, or one certificate pinned by its
 * fingerprint (which can be looked up, then compared with what the device itself shows).
 */
const props = defineProps<{
  integration: string
  /** The connection's address, which a certificate is looked up at. */
  url: string
  /** Makes the ids of the fields unique on a page with several connections. */
  idPrefix: string
  /** What is wrong, by field name. */
  problems: Readonly<Record<string, string>>
}>()
const mode = defineModel<TlsMode>('mode', { required: true })
const authority = defineModel<string>('authority', { required: true })
const fingerprint = defineModel<string>('fingerprint', { required: true })

const session = useSessionStore()

const found = ref<Certificate | null>(null)
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
  try {
    found.value = await session.change((token) =>
      lookUpCertificate(props.integration, props.url.trim(), token),
    )
  } catch (error) {
    // This route says what is wrong with the address in words, as its one problem.
    lookupError.value =
      (error instanceof ApiError && error.problems[0]?.message) || errorMessage(error)
  } finally {
    looking.value = false
  }
}

function trust(certificate: Certificate) {
  mode.value = 'pinned'
  fingerprint.value = certificate.fingerprint
}

const expired = (certificate: Certificate) => new Date(certificate.not_after) < new Date()
</script>

<template>
  <fieldset class="tls" :data-test="`${idPrefix}-tls`">
    <legend class="text-title-medium mb-1">Certificate</legend>
    <p class="text-body-medium text-medium-emphasis mb-2">
      How AresGate knows this is the right device. OPNsense, Wazuh and many others make their own
      certificate until you replace it: pin that one, or paste the authority that signed it.
    </p>
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

    <div v-else-if="mode === 'pinned'" class="mt-4">
      <v-text-field
        :id="`${idPrefix}-tls_fingerprint`"
        v-model="fingerprint"
        label="SHA-256 fingerprint"
        placeholder="AA:BB:CC:…"
        hint="Look it up below, then compare it with the one the device itself shows."
        persistent-hint
        spellcheck="false"
        autocomplete="off"
        class="tls__fingerprint"
        :error-messages="problems.tls_fingerprint"
        data-test="tls-fingerprint"
      />
      <v-btn
        variant="tonal"
        :prepend-icon="SearchCheck"
        :loading="looking"
        :disabled="url.trim() === ''"
        data-test="tls-look-up"
        @click="lookUp"
      >
        Look up the certificate
      </v-btn>
      <span v-if="url.trim() === ''" class="text-body-medium text-medium-emphasis ml-3">
        Enter the address first.
      </span>

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

      <div v-if="found" class="tls__found mt-4" data-test="tls-found">
        <h4 class="text-title-small mb-2">The certificate at {{ url.trim() }}</h4>
        <dl class="tls__details text-body-medium">
          <dt>Subject</dt>
          <dd data-test="tls-subject">{{ found.subject }}</dd>
          <dt>Issuer</dt>
          <dd>{{ found.issuer }}</dd>
          <template v-if="found.names.length">
            <dt>Names</dt>
            <dd>{{ found.names.join(', ') }}</dd>
          </template>
          <dt>Valid</dt>
          <dd>
            {{ formatDateTime(found.not_before) }} to {{ formatDateTime(found.not_after) }}
            <v-chip v-if="expired(found)" size="small" color="error" variant="tonal" class="ml-1">
              Expired
            </v-chip>
          </dd>
          <dt>SHA-256</dt>
          <dd class="tls__digest" data-test="tls-found-fingerprint">{{ found.fingerprint }}</dd>
        </dl>
        <v-alert
          type="warning"
          variant="tonal"
          density="compact"
          :icon="TriangleAlert"
          class="my-3"
        >
          This is what the device presented just now, over your network. Check the fingerprint
          against the one in the device's own certificate settings before you trust it.
        </v-alert>
        <p
          v-if="sameFingerprint(fingerprint, found.fingerprint)"
          class="d-flex align-center ga-2 text-success"
          data-test="tls-trusted"
        >
          <ShieldCheck :size="20" aria-hidden="true" />
          This certificate is the one trusted.
        </p>
        <v-btn
          v-else
          color="primary"
          :prepend-icon="ShieldCheck"
          data-test="tls-trust"
          @click="trust(found)"
        >
          Trust this certificate
        </v-btn>
      </div>
    </div>
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
.tls__fingerprint :deep(input),
.tls__digest {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
}

.tls__found {
  padding: 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.tls__details {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}

.tls__details dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.tls__details dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
