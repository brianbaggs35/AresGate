<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, onUnmounted, ref } from 'vue'

import { ApiError, errorMessage } from '@/api/client'
import type { Pause } from '@/api/integrations'
import { searchThreatIntel, type Lookup, type Provider, type Ruling } from '@/api/threatIntel'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { limitNotice } from '@/integrations'
import { useSessionStore } from '@/stores/session'
import { providerOf, withRuling } from '@/threatIntel'

/**
 * Searches one service (VirusTotal, AlienVault OTX or GreyNoise) for what it answers about, once
 * its connection is tested: an internet address, a domain or a web address for VirusTotal, an
 * address or a domain for OTX, an IPv4 address for GreyNoise. What the service reports opens in a
 * window over the page, and the last search stays one click away after the window is closed. While
 * the service's own limit or a minute's wait holds, a notice says when searches resume: that is not
 * a failure. A search refused for the spacing between lookups says how long to wait. A search of
 * something AresGate has an answer kept for shows that answer when the service can't be asked, and
 * the report says why. Check again, in the report, asks the service for a newer answer than the one
 * kept. The report is where the owner rules the subject safe or suspicious, whatever the service
 * made of it.
 */
const props = defineProps<{ provider: Provider; pause?: Pause | null }>()
const service = computed(() => providerOf(props.provider))
const emit = defineEmits<{ refused: []; answered: []; ruled: [] }>()

const session = useSessionStore()
const query = ref('')
const busy = ref(false)
const checking = ref(false)
const problem = ref<string | null>(null)
const refusal = ref<string | null>(null)
const last = ref<Lookup | null>(null)
const reportOpen = ref(false)

// The clock is read again every half minute, so the notice goes once the service's limit lifts.
const now = ref(Date.now())
const clock = setInterval(() => {
  now.value = Date.now()
}, 30_000)
onUnmounted(() => {
  clearInterval(clock)
})

const notice = computed(() => {
  const pause = props.pause
  if (pause && Date.parse(pause.until) > now.value)
    return limitNotice(pause, 'Searches', service.value.name)
  return refusal.value
})

/** Asks about a subject, and opens what came back. Returns whether an answer did. */
async function ask(subject: string, refresh: boolean): Promise<boolean> {
  problem.value = null
  refusal.value = null
  try {
    last.value = await session.change((token) =>
      searchThreatIntel(props.provider, subject, token, refresh),
    )
    reportOpen.value = true
    emit('answered')
    // A kept answer shown because a limit holds: the page asks for the limits again.
    if (last.value.notice) emit('refused')
    return true
  } catch (error) {
    if (error instanceof ApiError && error.status === 429) {
      refusal.value = errorMessage(error)
      // The page asks again for the limits, so that a limit the service set shows as one.
      emit('refused')
    } else {
      problem.value = errorMessage(error)
    }
    return false
  }
}

async function search() {
  const subject = query.value.trim()
  if (!subject || busy.value) return
  busy.value = true
  await ask(subject, false)
  busy.value = false
}

/** Shows the last search as the owner ruled it, or as the service made it again where the ruling was
 * taken back, and tells the page, so that what else it shows is read again. */
function ruled(ruling: Ruling | null) {
  // Only the report of the last search can say this, so there is one.
  last.value = withRuling(last.value as Lookup, ruling)
  emit('ruled')
}

/** Asks the service again about the last search, whatever is kept of it. */
async function checkAgain() {
  if (!last.value || checking.value) return
  checking.value = true
  const answered = await ask(last.value.subject, true)
  checking.value = false
  // What went wrong is said on the page, under the window.
  if (!answered) reportOpen.value = false
}
</script>

<template>
  <SectionCard
    title="Look up a threat"
    :description="`Ask ${service.name} about ${service.about}. Every answer is kept, and one that is still fresh comes from what AresGate kept, with no search. Any other search counts toward ${service.name}'s limits, so AresGate spaces them out.`"
    data-test="threat-lookup"
  >
    <form novalidate class="threat-lookup" data-test="threat-form" @submit.prevent="search">
      <v-text-field
        v-model="query"
        :label="service.label"
        :placeholder="service.placeholder"
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
      v-if="notice"
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

    <div v-if="last" class="threat-lookup__last" data-test="threat-last">
      <span class="text-body-medium text-medium-emphasis">Last search</span>
      <span class="threat-lookup__subject" data-test="threat-last-subject">{{ last.subject }}</span>
      <v-btn variant="tonal" size="small" data-test="threat-reopen" @click="reportOpen = true">
        View report
      </v-btn>
    </div>

    <p
      v-if="service.sharing"
      class="text-body-small text-medium-emphasis threat-lookup__note"
      data-test="threat-note"
    >
      If you use a free key, {{ service.name }} allows it for non-commercial use only.
      {{ service.sharing }}
    </p>

    <ThreatReportDialog
      v-if="last"
      v-model="reportOpen"
      :lookup="last"
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

.threat-lookup__note {
  margin: 0.75rem 0 0;
}
</style>
