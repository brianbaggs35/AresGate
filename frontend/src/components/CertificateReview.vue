<script setup lang="ts">
import { ShieldAlert, ShieldCheck, TriangleAlert } from '@lucide/vue'
import { computed, ref, useId } from 'vue'

import type { CertificateReview } from '@/api/integrations'
import { formatDateTime } from '@/format'

/**
 * The certificate a device presented, laid out for a person to decide about: whose it is, how long
 * it is good for, whether the way of checking chosen would already accept it and, if not, why, and
 * its fingerprint to compare with what the device itself shows. Trusting it is one click.
 */
const props = defineProps<{
  /** Where it was found. */
  address: string
  certificate: CertificateReview
  /** What the way of checking chosen makes of it, or nothing if that was chosen differently since
   * it was looked up. */
  verdict: { accepted: boolean; text: string } | null
  /** Whether this is the certificate that is trusted (pinned). */
  trusted: boolean
  /** Whether the connection is saved, so that trusting can test it straight away. */
  canTest: boolean
}>()
const emit = defineEmits<{ trust: [test: boolean] }>()

const heading = useId()
const root = ref<HTMLElement | null>(null)

const expired = computed(() => new Date(props.certificate.not_after) < new Date())
const notYet = computed(() => new Date(props.certificate.not_before) > new Date())
/** Nothing is left to do when it is trusted, or the way of checking already accepts it. */
const settled = computed(() => props.trusted || props.verdict?.accepted === true)

/** Takes the keyboard to the certificate, so that a screen reader reads it out. */
function focus() {
  root.value?.focus()
  root.value?.scrollIntoView({ block: 'nearest' })
}
defineExpose({ focus })
</script>

<template>
  <section ref="root" class="review" tabindex="-1" :aria-labelledby="heading" data-test="tls-found">
    <div class="review__head">
      <h4 :id="heading" class="text-title-small">The certificate at {{ address }}</h4>
      <div class="review__flags">
        <v-chip
          v-if="certificate.self_signed"
          size="small"
          color="info"
          variant="tonal"
          data-test="tls-self-signed"
        >
          Self-signed
        </v-chip>
        <v-chip v-if="expired" size="small" color="error" variant="tonal" data-test="tls-expired">
          Expired
        </v-chip>
        <v-chip v-else-if="notYet" size="small" color="warning" variant="tonal">
          Not valid yet
        </v-chip>
      </div>
    </div>

    <output v-if="trusted" class="review__verdict review__verdict--good" data-test="tls-trusted">
      <ShieldCheck :size="20" aria-hidden="true" />
      <span>This certificate is the one trusted.</span>
    </output>
    <output
      v-else-if="verdict"
      class="review__verdict"
      :class="{ 'review__verdict--good': verdict.accepted }"
      data-test="tls-verdict"
    >
      <component :is="verdict.accepted ? ShieldCheck : ShieldAlert" :size="20" aria-hidden="true" />
      <span>{{ verdict.text }}</span>
    </output>

    <dl class="review__details text-body-medium">
      <dt>Subject</dt>
      <dd data-test="tls-subject">{{ certificate.subject }}</dd>
      <dt>Issuer</dt>
      <dd>{{ certificate.issuer }}</dd>
      <template v-if="certificate.names.length">
        <dt>Names</dt>
        <dd>{{ certificate.names.join(', ') }}</dd>
      </template>
      <dt>Valid</dt>
      <dd>
        {{ formatDateTime(certificate.not_before) }} to {{ formatDateTime(certificate.not_after) }}
      </dd>
      <dt>SHA-256</dt>
      <dd class="review__digest" data-test="tls-found-fingerprint">
        {{ certificate.fingerprint }}
      </dd>
    </dl>

    <details v-if="certificate.issuers.length" class="review__also" data-test="tls-issuers">
      <summary class="text-body-medium">
        Also sent {{ certificate.issuers.length }} more
        {{ certificate.issuers.length === 1 ? 'certificate' : 'certificates' }}, which vouch for it
      </summary>
      <ul class="review__list">
        <li v-for="issuer in certificate.issuers" :key="issuer.fingerprint">
          <p class="text-body-medium">{{ issuer.subject }}</p>
          <p class="text-body-small text-medium-emphasis">
            Issued by {{ issuer.issuer }}<template v-if="issuer.self_signed"> (itself)</template>,
            good until {{ formatDateTime(issuer.not_after) }}
          </p>
          <p class="review__digest text-medium-emphasis">{{ issuer.fingerprint }}</p>
        </li>
      </ul>
    </details>

    <template v-if="!settled">
      <v-alert
        type="warning"
        variant="tonal"
        density="compact"
        :icon="TriangleAlert"
        class="my-3"
        data-test="tls-compare"
      >
        This is what the device presented just now, over your network. Check the fingerprint against
        the one in the device's own certificate settings before you trust it.
      </v-alert>
      <div class="review__actions">
        <v-btn
          v-if="canTest"
          color="primary"
          :prepend-icon="ShieldCheck"
          data-test="tls-trust-test"
          @click="emit('trust', true)"
        >
          Trust and test
        </v-btn>
        <v-btn
          :color="canTest ? undefined : 'primary'"
          :variant="canTest ? 'tonal' : 'flat'"
          :prepend-icon="canTest ? undefined : ShieldCheck"
          data-test="tls-trust"
          @click="emit('trust', false)"
        >
          Trust this certificate
        </v-btn>
      </div>
      <p v-if="canTest" class="text-body-medium text-medium-emphasis mt-2">
        Trust and test saves your changes, then tests the connection again.
      </p>
    </template>
    <p v-else-if="trusted" class="text-body-medium text-medium-emphasis mt-3">
      Nothing else is accepted for this connection, even a certificate that looks valid. If it is
      ever replaced, AresGate says so and you review the new one.
    </p>
  </section>
</template>

<style scoped>
.review {
  padding: 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.review:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.review__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 0.75rem;
}

.review__head h4 {
  min-width: 0;
  overflow-wrap: anywhere;
}

.review__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.review__verdict {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0 0 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  background: rgba(var(--v-theme-warning), 0.14);
}

.review__verdict svg {
  flex: none;
  margin-top: 0.125rem;
  color: rgb(var(--v-theme-warning));
}

.review__verdict--good {
  background: rgba(var(--v-theme-success), 0.14);
}

.review__verdict--good svg {
  color: rgb(var(--v-theme-success));
}

.review__verdict span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.review__details {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}

.review__details dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.review__details dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.review__digest {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

.review__also {
  margin-top: 0.75rem;
}

.review__also summary {
  cursor: pointer;
}

.review__list {
  display: grid;
  gap: 0.75rem;
  margin: 0.5rem 0 0;
  padding: 0 0 0 1rem;
  list-style: none;
  border-left: 2px solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.review__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

@media (max-width: 599px) {
  .review__details {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .review__details dd {
    margin-bottom: 0.5rem;
  }

  .review__actions {
    flex-direction: column;
  }

  .review__actions :deep(.v-btn) {
    width: 100%;
  }
}
</style>
