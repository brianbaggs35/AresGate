<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, onUnmounted, ref } from 'vue'

import { ApiError, errorMessage } from '@/api/client'
import type { Pause } from '@/api/integrations'
import {
  searchThreatIntel,
  type Lookup,
  type Provider,
  type Ruling,
  type SubjectKind,
} from '@/api/threatIntel'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { formatList } from '@/format'
import { limitNotice } from '@/integrations'
import { useSessionStore } from '@/stores/session'
import { JUDGEMENT, providerOf, tallyOf, typeOf, withRuling } from '@/threatIntel'

/**
 * Searches for one kind of subject (an IP address, a domain or a web address) in every connected
 * service that answers about that kind, at once. VirusTotal answers about all three, AlienVault
 * OTX about addresses and domains, GreyNoise about IPv4 addresses. A subject of another kind is
 * refused, so a search is never answered under the wrong tab. Each answer is one result, named for
 * its service and opening as a report in a window over the page; where only one service answered,
 * its report opens at once. While a service's own limit or a minute's wait holds, a notice says
 * when its searches resume: that is not a failure, and the services that are not held still
 * answer. A search of something AresGate has an answer kept for shows that answer when the service
 * can't be asked, and the report says why. Check again, in the report, asks that service for a
 * newer answer than the one kept. The report is where the owner rules the subject safe or
 * suspicious, whatever the services made of it, which holds for every service's answer.
 */
const props = defineProps<{
  kind: SubjectKind
  /** The connected services that answer about the kind, each with the limit that holds it. */
  services: { key: Provider; pause: Pause | null }[]
  /** The services that answer about the kind and are not connected. */
  missing: Provider[]
}>()
const emit = defineEmits<{ refused: []; answered: []; ruled: [] }>()

const session = useSessionStore()
const type = computed(() => typeOf(props.kind))
const query = ref('')
const busy = ref(false)
const checking = ref(false)
const problem = ref<string | null>(null)
const refusals = ref<Partial<Record<Provider, string>>>({})
const subject = ref('')
const answers = ref<Lookup[]>([])
const opened = ref<Provider | null>(null)
const reportOpen = ref(false)

// The clock is read again every half minute, so a notice goes once its service's limit lifts.
const now = ref(Date.now())
const clock = setInterval(() => {
  now.value = Date.now()
}, 30_000)
onUnmounted(() => {
  clearInterval(clock)
})

const notices = computed(() => [
  ...props.services.flatMap(({ key, pause }) =>
    pause && Date.parse(pause.until) > now.value
      ? [limitNotice(pause, 'Searches', providerOf(key).name)]
      : [],
  ),
  ...Object.entries(refusals.value).map(
    ([key, message]) => `${providerOf(key as Provider).name}: ${message}`,
  ),
])
const open = computed(() => answers.value.find((one) => one.provider === opened.value) ?? null)
const names = computed(() => formatList(props.services.map(({ key }) => providerOf(key).name)))
const sharing = computed(() =>
  props.services.flatMap(({ key }) => {
    const text = providerOf(key).sharing
    const name = providerOf(key).name
    return text
      ? [`If you use a free key, ${name} allows it for non-commercial use only. ${text}`]
      : []
  }),
)

/** One service's answer, or what went wrong asking it: a limit that holds, or anything else. */
async function askOne(
  provider: Provider,
  text: string,
  refresh: boolean,
): Promise<{ lookup: Lookup } | { error: unknown }> {
  try {
    return {
      lookup: await session.change((token) =>
        searchThreatIntel(provider, text, token, refresh, props.kind),
      ),
    }
  } catch (error) {
    return { error }
  }
}

/** Asks every service about a subject and shows what came back. Where one service was asked, that
 * is the only answer; where several, the answers sit side by side. */
async function ask(text: string, only: Provider | null, refresh: boolean): Promise<Lookup[]> {
  problem.value = null
  const asked = only ? [only] : props.services.map(({ key }) => key)
  const replies = await Promise.all(asked.map((key) => askOne(key, text, refresh)))
  const held = (reply: (typeof replies)[number]) =>
    'error' in reply && reply.error instanceof ApiError && reply.error.status === 429
  // Refusals are kept for the services that were not asked this time.
  const refused: Partial<Record<Provider, string>> = Object.fromEntries(
    Object.entries(refusals.value).filter(([key]) => !asked.includes(key as Provider)),
  )
  replies.forEach((reply, index) => {
    if (held(reply))
      refused[asked[index] as Provider] = errorMessage((reply as { error: unknown }).error)
    else if ('error' in reply) problem.value = errorMessage(reply.error)
  })
  refusals.value = refused
  const found = replies.flatMap((reply) => ('lookup' in reply ? [reply.lookup] : []))
  // The page asks again for the limits, so that a limit a service set shows as one, or a kept
  // answer shown because a limit holds.
  if (replies.some(held) || found.some((one) => one.notice)) emit('refused')
  return found
}

async function search() {
  const text = query.value.trim()
  if (!text || busy.value) return
  busy.value = true
  const found = await ask(text, null, false)
  subject.value = text
  answers.value = found
  if (found.length) {
    emit('answered')
    // With one answer there is nothing to choose, so its report opens.
    if (found.length === 1) show((found[0] as Lookup).provider)
  }
  busy.value = false
}

function show(provider: Provider) {
  opened.value = provider
  reportOpen.value = true
}

/** Shows every answer as the owner ruled it, or as its service made it again where the ruling was
 * taken back, and tells the page, so that what else it shows is read again. */
function ruled(ruling: Ruling | null) {
  answers.value = answers.value.map((one) => withRuling(one, ruling))
  emit('ruled')
}

/** Asks the service of the report that is open again, whatever is kept of its answer. */
async function checkAgain() {
  const current = open.value
  if (!current || checking.value) return
  checking.value = true
  const [fresh] = await ask(current.subject, current.provider, true)
  checking.value = false
  if (!fresh) {
    // What went wrong is said on the page, under the window.
    reportOpen.value = false
    return
  }
  answers.value = answers.value.map((one) => (one.provider === fresh.provider ? fresh : one))
  emit('answered')
}
</script>

<template>
  <SectionCard
    :title="`Look up ${type.about}`"
    :description="`Ask ${names} at once. Every answer is kept, and one that is still fresh comes from what AresGate kept, with no search. Any other search counts toward each service's limits, so AresGate spaces them out.`"
    data-test="threat-lookup"
  >
    <form novalidate class="threat-lookup" data-test="threat-form" @submit.prevent="search">
      <v-text-field
        v-model="query"
        :label="type.label"
        :placeholder="type.placeholder"
        :prepend-inner-icon="Search"
        autocomplete="off"
        spellcheck="false"
        density="comfortable"
        clearable
        data-test="threat-subject"
      />
      <div class="threat-lookup__actions">
        <v-btn
          type="submit"
          color="primary"
          :loading="busy"
          :disabled="!query.trim()"
          data-test="threat-search"
        >
          Search
        </v-btn>
      </div>
    </form>

    <v-alert
      v-for="notice in notices"
      :key="notice"
      type="info"
      variant="tonal"
      class="threat-lookup__alert"
      data-test="threat-notice"
    >
      {{ notice }}
    </v-alert>

    <v-alert
      v-if="problem"
      type="error"
      variant="tonal"
      class="threat-lookup__alert"
      data-test="threat-problem"
    >
      {{ problem }}
    </v-alert>

    <div v-if="answers.length" class="threat-lookup__last" data-test="threat-last">
      <span class="text-body-medium text-medium-emphasis">Last search</span>
      <span class="threat-lookup__subject" data-test="threat-last-subject">{{ subject }}</span>
      <v-btn
        v-for="one in answers"
        :key="one.provider"
        variant="tonal"
        size="small"
        :color="JUDGEMENT[one.judgement].color"
        :prepend-icon="JUDGEMENT[one.judgement].icon"
        :aria-label="`View the report of ${one.provider_name}: ${JUDGEMENT[one.judgement].short}, ${tallyOf(one)}`"
        data-test="threat-result"
        @click="show(one.provider)"
      >
        {{ one.provider_name }}
        <span class="threat-lookup__tally">{{ tallyOf(one) }}</span>
      </v-btn>
    </div>

    <p
      v-if="missing.length"
      class="text-body-small text-medium-emphasis threat-lookup__note"
      data-test="threat-missing"
    >
      {{ formatList(missing.map((key) => providerOf(key).name)) }}
      {{ missing.length === 1 ? 'also answers' : 'also answer' }} about {{ type.about }} and
      {{ missing.length === 1 ? 'is' : 'are' }} not connected, so
      {{ missing.length === 1 ? 'it is' : 'they are' }} not asked.
      <router-link :to="{ name: 'integrations' }">Go to Integrations</router-link>
    </p>

    <p
      v-for="text in sharing"
      :key="text"
      class="text-body-small text-medium-emphasis threat-lookup__note"
      data-test="threat-note"
    >
      {{ text }}
    </p>

    <ThreatReportDialog
      v-if="open"
      v-model="reportOpen"
      :lookup="open"
      :busy="checking"
      @refresh="checkAgain"
      @ruled="ruled"
    />
  </SectionCard>
</template>

<style scoped>
.threat-lookup {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.threat-lookup__actions {
  display: flex;
  justify-content: flex-end;
}

.threat-lookup__alert {
  margin-top: 0.75rem;
}

.threat-lookup__last {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin-top: 0.75rem;
}

.threat-lookup__subject {
  min-width: 0;
  overflow-wrap: anywhere;
}

.threat-lookup__tally {
  margin-inline-start: 0.5rem;
  opacity: 0.8;
}

.threat-lookup__note {
  margin: 0.75rem 0 0;
}
</style>
