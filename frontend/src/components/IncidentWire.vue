<script setup lang="ts">
import { Binary, Globe, Info, Lock, Search, Terminal } from '@lucide/vue'
import { computed, ref } from 'vue'

import type {
  Wire,
  WireBanner,
  WireCertificate,
  WireHeader,
  WireLookup,
  WireRequest,
} from '@/api/incidents'
import { formatCount } from '@/format'

/**
 * What was said on the wire in an incident's alerts, as the program that read it gave it: the
 * certificate a server showed, a web request sent in the clear, a name that was looked up, the
 * banners of an ssh login, the start of the packet that set an alert off. A few plain words at
 * the top say what stands out, and the details sit in panels below, so a page is not long until
 * someone asks. A header that can carry a password or a key is shown as hidden, because it was
 * never kept. The page leaves the whole section out when a program read none of it.
 */
const props = defineProps<{ wire: Wire }>()

type Panel = 'certificates' | 'requests' | 'lookups' | 'banners' | 'packet'

/** The panels with something in them, in the order the page shows them. */
const panels = computed(() => {
  const { certificates, requests, lookups, banners, payload, dump } = props.wire
  const found: { key: Panel; title: string; count: number }[] = [
    { key: 'certificates', title: 'Certificates', count: certificates.length },
    { key: 'requests', title: 'Web requests', count: requests.length },
    { key: 'lookups', title: 'Names looked up', count: lookups.length },
    { key: 'banners', title: 'ssh banners', count: banners.length },
    { key: 'packet', title: 'The start of the packet', count: payload || dump.length ? 1 : 0 },
  ]
  return found.filter((panel) => panel.count > 0)
})

// The first panel is open, because what stands out is usually in it.
const open = ref<Panel[]>(panels.value.slice(0, 1).map((panel) => panel.key))

function who(certificate: WireCertificate): string {
  return certificate.sni ?? certificate.subject ?? 'A server'
}

function target(request: WireRequest): string {
  return `${request.host ?? request.server ?? ''}${request.url ?? ''}`
}

function mentions(count: number): string {
  return `${formatCount(count)} ${count === 1 ? 'alert' : 'alerts'}`
}

/** The day a certificate begins or ends on. Suricata writes the time in UTC, and the day is what
 * matters. */
function day(stamp: string): string {
  return stamp.slice(0, 10)
}

function details(certificate: WireCertificate): [string, string][] {
  const rows: [string, string | null][] = [
    ['Issued to', certificate.subject],
    ['Vouched for by', certificate.self_signed ? 'itself' : certificate.issuer],
    ['Good from', certificate.not_before ? day(certificate.not_before) : null],
    ['Good until', certificate.not_after ? day(certificate.not_after) : null],
    ['Shown by', certificate.server],
    ['Serial', certificate.serial],
    ['Fingerprint', certificate.fingerprint],
    ['Client fingerprint', certificate.ja3],
    ['Server fingerprint', certificate.ja3s],
  ]
  return rows.filter((row): row is [string, string] => row[1] !== null)
}

function lookedUp(lookup: WireLookup): string {
  return lookup.answers.length ? lookup.answers.join(', ') : (lookup.rcode ?? 'no answer')
}

function software(banner: WireBanner): [string, string][] {
  const rows: [string, string | null][] = [
    ['The client runs', banner.client],
    ['The server runs', banner.server_software],
  ]
  return rows.filter((row): row is [string, string] => row[1] !== null)
}

function headerGroups(request: WireRequest): { title: string; rows: WireHeader[] }[] {
  return [
    { title: 'Sent', rows: request.request_headers },
    { title: 'Came back', rows: request.response_headers },
  ].filter((group) => group.rows.length > 0)
}
</script>

<template>
  <div class="wire" data-test="wire">
    <v-alert
      v-if="wire.notes.length"
      type="info"
      variant="tonal"
      :icon="Info"
      data-test="wire-notes"
    >
      <p v-for="note in wire.notes" :key="note" class="wire__note" data-test="wire-note">
        {{ note }}
      </p>
    </v-alert>

    <v-expansion-panels v-model="open" variant="accordion" multiple>
      <v-expansion-panel
        v-for="panel in panels"
        :key="panel.key"
        :value="panel.key"
        :data-test="`wire-panel-${panel.key}`"
      >
        <v-expansion-panel-title>
          <span class="text-title-medium">{{ panel.title }}</span>
          <v-chip
            v-if="panel.key !== 'packet'"
            size="small"
            variant="tonal"
            class="ml-3"
            data-test="wire-count"
          >
            {{ formatCount(panel.count) }}
          </v-chip>
        </v-expansion-panel-title>

        <v-expansion-panel-text>
          <ul v-if="panel.key === 'certificates'" class="wire__list">
            <li
              v-for="(certificate, index) in wire.certificates"
              :key="index"
              class="wire__item"
              data-test="wire-certificate"
            >
              <div class="wire__head">
                <v-icon :icon="Lock" size="18" aria-hidden="true" />
                <span class="text-title-small wire__name" data-test="wire-certificate-name">
                  {{ who(certificate) }}
                </span>
                <v-chip
                  v-if="certificate.self_signed"
                  size="small"
                  color="warning"
                  variant="tonal"
                  data-test="wire-self-signed"
                >
                  Self-signed
                </v-chip>
                <v-chip
                  v-if="certificate.expired"
                  size="small"
                  color="error"
                  variant="tonal"
                  data-test="wire-expired"
                >
                  Ran out
                </v-chip>
                <v-chip v-if="certificate.version" size="small" variant="outlined">
                  {{ certificate.version }}
                </v-chip>
                <span class="text-body-small text-medium-emphasis">
                  {{ mentions(certificate.alerts) }}
                </span>
              </div>
              <dl class="wire__facts">
                <template v-for="[label, value] in details(certificate)" :key="label">
                  <dt class="text-label-large text-medium-emphasis">{{ label }}</dt>
                  <dd class="text-body-medium wire__value">{{ value }}</dd>
                </template>
              </dl>
            </li>
          </ul>

          <ul v-else-if="panel.key === 'requests'" class="wire__list">
            <li
              v-for="(request, index) in wire.requests"
              :key="index"
              class="wire__item"
              data-test="wire-request"
            >
              <div class="wire__head">
                <v-icon :icon="Globe" size="18" aria-hidden="true" />
                <span class="text-title-small wire__name" data-test="wire-request-name">
                  {{ request.method ?? 'Request' }} {{ target(request) }}
                </span>
                <v-chip v-if="request.status !== null" size="small" variant="outlined">
                  {{ request.status }}
                </v-chip>
                <v-chip v-if="request.content_type" size="small" variant="outlined">
                  {{ request.content_type }}
                </v-chip>
                <span class="text-body-small text-medium-emphasis">
                  {{ mentions(request.alerts) }}
                </span>
              </div>
              <p v-if="request.user_agent" class="text-body-medium wire__plain">
                <span class="text-medium-emphasis">Software:</span> {{ request.user_agent }}
              </p>
              <div v-for="group in headerGroups(request)" :key="group.title">
                <p class="text-label-large text-medium-emphasis wire__plain">{{ group.title }}</p>
                <div class="wire__scroll">
                  <table :aria-label="`${group.title} headers`">
                    <tbody>
                      <tr v-for="(row, at) in group.rows" :key="at" data-test="wire-header">
                        <th scope="row">{{ row.name }}</th>
                        <td>
                          <v-chip
                            v-if="row.hidden"
                            size="x-small"
                            color="warning"
                            variant="tonal"
                            data-test="wire-hidden"
                          >
                            Hidden: it carries a login or a key
                          </v-chip>
                          <template v-else>{{ row.value }}</template>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </li>
          </ul>

          <ul v-else-if="panel.key === 'lookups'" class="wire__list">
            <li
              v-for="(lookup, index) in wire.lookups"
              :key="index"
              class="wire__item wire__item--line"
              data-test="wire-lookup"
            >
              <v-icon :icon="Search" size="18" aria-hidden="true" />
              <span class="wire__name">
                <span class="text-title-small">{{ lookup.name }}</span>
                <span class="text-body-medium text-medium-emphasis"> → {{ lookedUp(lookup) }}</span>
              </span>
              <v-chip v-if="lookup.type" size="x-small" variant="outlined">{{
                lookup.type
              }}</v-chip>
              <span class="text-body-small text-medium-emphasis">{{
                mentions(lookup.alerts)
              }}</span>
            </li>
          </ul>

          <ul v-else-if="panel.key === 'banners'" class="wire__list">
            <li
              v-for="(banner, index) in wire.banners"
              :key="index"
              class="wire__item"
              data-test="wire-banner"
            >
              <div class="wire__head">
                <v-icon :icon="Terminal" size="18" aria-hidden="true" />
                <span class="text-title-small wire__name">{{ banner.server ?? 'ssh' }}</span>
                <span class="text-body-small text-medium-emphasis">
                  {{ mentions(banner.alerts) }}
                </span>
              </div>
              <dl class="wire__facts">
                <template v-for="[label, value] in software(banner)" :key="label">
                  <dt class="text-label-large text-medium-emphasis">{{ label }}</dt>
                  <dd class="text-body-medium wire__value">{{ value }}</dd>
                </template>
              </dl>
            </li>
          </ul>

          <div v-else class="wire__item" data-test="wire-packet">
            <code v-if="wire.payload" class="wire__code text-body-medium" data-test="wire-payload">
              {{ wire.payload }}
            </code>
            <div v-if="wire.dump.length" class="wire__scroll">
              <p class="text-label-large text-medium-emphasis wire__plain">
                <v-icon :icon="Binary" size="16" aria-hidden="true" /> As bytes
              </p>
              <table class="wire__dump" aria-label="The first bytes of the packet">
                <tbody>
                  <tr v-for="row in wire.dump" :key="row.offset" data-test="wire-dump-row">
                    <td class="text-medium-emphasis">{{ row.offset }}</td>
                    <td>{{ row.hex }}</td>
                    <td>{{ row.text }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<style scoped>
.wire {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.wire__note,
.wire__plain {
  margin: 0;
}

.wire__note + .wire__note {
  margin-top: 0.5rem;
}

.wire__list {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.wire__item {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  min-width: 0;
}

.wire__item--line {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.wire__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.wire__name {
  overflow-wrap: anywhere;
}

.wire__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}

.wire__facts dd,
.wire__facts dt {
  margin: 0;
}

.wire__value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}

@media (max-width: 599px) {
  .wire__facts {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .wire__facts dd {
    margin-bottom: 0.5rem;
  }
}

.wire__scroll {
  max-width: 100%;
  overflow-x: auto;
}

.wire__scroll table {
  border-collapse: collapse;
  font-size: 0.8125rem;
  line-height: 1.6;
}

.wire__scroll th,
.wire__scroll td {
  padding: 0 1rem 0 0;
  text-align: start;
  vertical-align: top;
}

.wire__scroll th {
  font-weight: 600;
  white-space: nowrap;
}

.wire__dump {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.wire__dump td {
  white-space: pre;
}

.wire__code {
  display: block;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
