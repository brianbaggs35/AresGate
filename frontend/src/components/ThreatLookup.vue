<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, onUnmounted, ref } from 'vue'

import { ApiError, errorMessage } from '@/api/client'
import type { Pause } from '@/api/integrations'
import { searchThreatIntel, type Lookup } from '@/api/threatIntel'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { limitNotice } from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * Searches VirusTotal for an internet address, a domain or a web address, once the connection is
 * tested. What VirusTotal reports opens in a window over the page, and the last search stays one
 * click away after the window is closed. While VirusTotal's own daily limit or a minute's wait
 * holds, a notice says when searches resume: that is not a failure. A search refused for the
 * spacing between lookups says how long to wait.
 */
const props = defineProps<{ pause?: Pause | null }>()
const emit = defineEmits<{ refused: [] }>()

const session = useSessionStore()
const query = ref('')
const busy = ref(false)
const problem = ref<string | null>(null)
const refusal = ref<string | null>(null)
const last = ref<Lookup | null>(null)
const reportOpen = ref(false)

// The clock is read again every half minute, so the notice goes once VirusTotal's limit lifts.
const now = ref(Date.now())
const clock = setInterval(() => {
  now.value = Date.now()
}, 30_000)
onUnmounted(() => {
  clearInterval(clock)
})

const notice = computed(() => {
  const pause = props.pause
  if (pause && Date.parse(pause.until) > now.value) return limitNotice(pause, 'Searches')
  return refusal.value
})

async function search() {
  const subject = query.value.trim()
  if (!subject || busy.value) return
  busy.value = true
  problem.value = null
  refusal.value = null
  try {
    last.value = await session.change((token) => searchThreatIntel(subject, token))
    reportOpen.value = true
  } catch (error) {
    if (error instanceof ApiError && error.status === 429) {
      refusal.value = errorMessage(error)
      // The page asks again for the limits, so that a limit VirusTotal set shows as one.
      emit('refused')
    } else {
      problem.value = errorMessage(error)
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <SectionCard
    title="Look up a threat"
    description="Ask VirusTotal about an IP address, a domain or a web address. An answer checked within the last week comes from what AresGate kept, with no search. Any other search counts toward VirusTotal's limits, so AresGate spaces them out."
    data-test="threat-lookup"
  >
    <form novalidate class="threat-lookup" data-test="threat-form" @submit.prevent="search">
      <v-text-field
        v-model="query"
        label="IP address, domain or web address"
        placeholder="203.0.113.7, example.com or https://example.com/login"
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

    <p class="text-body-small text-medium-emphasis threat-lookup__note">
      If you use a free key, VirusTotal allows it for non-commercial use only. What you search for
      is added to VirusTotal's shared data, so keep private names out of searches.
    </p>

    <ThreatReportDialog v-if="last" v-model="reportOpen" :lookup="last" />
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
