<script setup lang="ts">
import { Copy, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchStatus, type Part, type StatusReport } from '@/api/status'
import AppPage from '@/components/AppPage.vue'
import FactList from '@/components/FactList.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import PartList from '@/components/PartList.vue'
import SectionCard from '@/components/SectionCard.vue'
import UsageMeter from '@/components/UsageMeter.vue'
import { formatBytes, formatDateTime, formatDuration } from '@/format'
import { useSessionStore } from '@/stores/session'

/** A computer's clock more than this far from AresGate's is worth saying so. */
const CLOCK_TOLERANCE_SECONDS = 60
/** A certificate this close to its end is worth saying so. */
const CERTIFICATE_WARNING_DAYS = 14

const session = useSessionStore()

const report = ref<StatusReport | null>(null)
/** How far this computer's clock was ahead of AresGate's when the report arrived, in seconds
 * (behind when negative). */
const clockSkew = ref(0)
const loadError = ref<string | null>(null)
const loading = ref(false)
/** Whether the text for a bug report reached the clipboard, once that was tried. */
const copied = ref<boolean | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const fresh = await session.call(fetchStatus)
    clockSkew.value = Math.round((Date.now() - Date.parse(fresh.container.server_time)) / 1000)
    report.value = fresh
  } catch (error) {
    // What is on screen is no longer how things are, so it goes rather than mislead.
    report.value = null
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText((report.value as StatusReport).diagnostics)
    copied.value = true
  } catch {
    // No clipboard on a page that isn't secure, or the browser said no.
    copied.value = false
  }
}

const fact = (id: string, label: string, value: string) => ({ id, label, value })

/** A migration is named by its number, or "none" for a database that has none yet. */
const named = (migration: string | null) => migration ?? 'none'

function clockSummary(skew: number): string {
  if (Math.abs(skew) <= CLOCK_TOLERANCE_SECONDS) return 'In step with this computer'
  const direction = skew > 0 ? 'behind' : 'ahead of'
  return `${formatDuration(Math.abs(skew))} ${direction} this computer`
}

function certificateEnds(days: number): string {
  if (days < 0) return 'has expired'
  if (days === 0) return 'expires within a day'
  return `expires in ${days.toString()} ${days === 1 ? 'day' : 'days'}`
}

/** What needs a look, in words. Nothing here means everything checks out. */
const attention = computed(() => {
  const current = report.value as StatusReport
  const { database, certificate } = current.stack
  const found: string[] = []
  if (database.status === 'unavailable') {
    found.push("The database isn't answering.")
  } else if (database.migration !== database.migration_head) {
    found.push(
      `The database is at migration ${named(database.migration)}, but this version of AresGate expects ${named(database.migration_head)}.`,
    )
  }
  if (certificate && certificate.days_left <= CERTIFICATE_WARNING_DAYS) {
    found.push(`The certificate ${certificateEnds(certificate.days_left)}.`)
  }
  // A collector whose integration is already named is the same trouble said again.
  const failing = new Set(
    current.parts
      .filter((part) => part.group === 'integration' && part.state === 'problem')
      .map((part) => part.integration),
  )
  for (const part of current.parts) {
    const repeated = part.group === 'collector' && failing.has(part.integration)
    if (part.state === 'problem' && !repeated) found.push(`${part.name} has a problem.`)
  }
  if (Math.abs(clockSkew.value) > CLOCK_TOLERANCE_SECONDS) {
    found.push(`AresGate's clock is ${clockSummary(clockSkew.value)}.`)
  }
  return found
})

/** The parts of one group, in the order the API lists them. */
const partsOf = (group: Part['group']) =>
  (report.value as StatusReport).parts.filter((part) => part.group === group)

const aresgateFacts = computed(() => {
  const { aresgate } = report.value as StatusReport
  return [
    fact('version', 'Version', aresgate.version),
    fact('commit', 'Commit', aresgate.commit?.slice(0, 12) ?? 'Not recorded'),
    fact('built', 'Built', aresgate.built_at ? formatDateTime(aresgate.built_at) : 'Not recorded'),
    fact('environment', 'Environment', aresgate.environment),
    fact('started', 'Started', formatDateTime(aresgate.started_at)),
    fact('uptime', 'Running for', formatDuration(aresgate.uptime_seconds)),
  ]
})

const softwareFacts = computed(() => {
  const { python, nginx, database } = (report.value as StatusReport).stack
  const facts = [
    fact('python', 'Python', python),
    fact('nginx', 'nginx', nginx ?? 'Not found'),
    fact(
      'database',
      'PostgreSQL',
      database.status === 'ok' ? (database.version ?? 'Unknown') : 'Not answering',
    ),
  ]
  if (database.status === 'ok') {
    if (database.size_bytes !== null) {
      facts.push(fact('database-size', 'Database size', formatBytes(database.size_bytes)))
    }
    if (database.connections !== null && database.max_connections !== null) {
      facts.push(
        fact(
          'database-connections',
          'Connections',
          `${database.connections.toString()} of ${database.max_connections.toString()}`,
        ),
      )
    }
    const { migration, migration_head: head } = database
    facts.push(
      fact(
        'migration',
        'Migration',
        migration === head
          ? `${named(head)} (up to date)`
          : `${named(migration)}, expected ${named(head)}`,
      ),
    )
  }
  return facts
})

const certificateFacts = computed(() => {
  const certificate = (report.value as StatusReport).stack.certificate
  if (!certificate) return []
  return [
    fact('certificate-names', 'Names', certificate.names.join(', ')),
    fact(
      'certificate-issuer',
      'Issued by',
      certificate.self_signed ? 'Itself (self-signed)' : certificate.issuer,
    ),
    fact('certificate-from', 'Valid from', formatDateTime(certificate.not_before)),
    fact(
      'certificate-until',
      'Valid until',
      `${formatDateTime(certificate.not_after)} (${certificateEnds(certificate.days_left)})`,
    ),
  ]
})

/** Memory in use against what there is of it: the container's limit, or else the computer's. */
const memoryUse = computed(() => {
  const { memory } = (report.value as StatusReport).container
  if (!memory) return null
  const total = memory.limit_bytes ?? memory.total_bytes
  return total === null ? null : { used: memory.used_bytes, total }
})

const containerFacts = computed(() => {
  const { cpus, load: averages, memory } = (report.value as StatusReport).container
  const facts = [
    fact('cpus', 'CPUs', cpus === null ? 'Unknown' : cpus.toString()),
    fact(
      'load',
      'Load (1, 5, 15 minutes)',
      averages ? averages.map((value) => value.toFixed(2)).join(' · ') : 'Unknown',
    ),
    fact('clock', 'Clock', clockSummary(clockSkew.value)),
  ]
  // With no limit and no total there is nothing to measure memory against, so it is just a figure.
  if (memory && !memoryUse.value) {
    facts.push(fact('memory-used', 'Memory in use', formatBytes(memory.used_bytes)))
  }
  return facts
})

onMounted(load)
</script>

<template>
  <AppPage>
    <PageHeader
      title="Status"
      description="How AresGate and the programs it runs on are doing. Look here first when something seems wrong."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="status-refresh"
          @click="load"
        >
          Refresh
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError"
      :message="loadError"
      :loading="loading"
      retry-test-id="status-retry"
      data-test="status-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!report" type="card, card" data-test="status-loading" />
    <template v-else>
      <v-alert
        v-if="attention.length"
        type="warning"
        variant="tonal"
        :title="attention.length === 1 ? 'One thing needs a look' : 'Some things need a look'"
        data-test="status-attention"
      >
        <ul class="status__attention">
          <li v-for="item in attention" :key="item" data-test="status-attention-item">
            {{ item }}
          </li>
        </ul>
      </v-alert>
      <v-alert v-else type="success" variant="tonal" data-test="status-fine">
        Everything checks out.
      </v-alert>

      <SectionCard title="AresGate" data-test="status-aresgate">
        <FactList :facts="aresgateFacts" />
      </SectionCard>

      <SectionCard
        title="Software"
        description="What AresGate runs on, inside its container."
        data-test="status-software"
      >
        <FactList :facts="softwareFacts" />
      </SectionCard>

      <SectionCard
        v-if="certificateFacts.length"
        title="Certificate"
        description="The one your browser is shown when it opens AresGate."
        data-test="status-certificate"
      >
        <FactList :facts="certificateFacts" />
      </SectionCard>

      <SectionCard
        title="Container"
        description="What AresGate has to work with."
        data-test="status-container"
      >
        <FactList :facts="containerFacts" />
        <div class="status__meters">
          <UsageMeter
            v-if="memoryUse"
            label="Memory"
            :used="memoryUse.used"
            :total="memoryUse.total"
          />
          <UsageMeter
            v-if="report.container.disk"
            label="Data disk"
            :used="report.container.disk.used_bytes"
            :total="report.container.disk.total_bytes"
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Integrations"
        description="The systems AresGate watches the network through."
        data-test="status-parts"
      >
        <PartList :parts="partsOf('integration')" />
      </SectionCard>

      <SectionCard
        title="Collectors"
        description="The worker, and the jobs it runs on a schedule to read from each integration."
        data-test="status-collectors"
      >
        <PartList :parts="partsOf('collector')" />
      </SectionCard>

      <SectionCard
        title="For a bug report"
        description="The details above as text, with addresses left out. Paste it into an issue when you report a problem."
        data-test="status-report"
      >
        <template #actions>
          <v-btn variant="tonal" :prepend-icon="Copy" data-test="status-copy" @click="copy">
            Copy
          </v-btn>
        </template>
        <output class="status__copy">
          <v-alert
            v-if="copied === true"
            type="success"
            variant="tonal"
            density="compact"
            data-test="status-copied"
          >
            Copied.
          </v-alert>
          <v-alert
            v-else-if="copied === false"
            type="warning"
            variant="tonal"
            density="compact"
            data-test="status-copy-failed"
          >
            Your browser wouldn't copy it. Select the text below and copy it yourself.
          </v-alert>
        </output>
        <pre class="status__diagnostics text-body-medium" data-test="diagnostics">{{
          report.diagnostics
        }}</pre>
      </SectionCard>
    </template>
  </AppPage>
</template>

<style scoped>
.status__attention {
  margin: 0;
  padding-left: 1.25rem;
}

.status__meters {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1rem;
}

.status__copy {
  display: block;
  margin-bottom: 0.75rem;
}

.status__diagnostics {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant), 0.4);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
