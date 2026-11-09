<script setup lang="ts">
import { Search } from '@lucide/vue'
import { ref } from 'vue'

import { errorMessage } from '@/api/client'
import { searchThreatIntel, type Lookup } from '@/api/threatIntel'
import SectionCard from '@/components/SectionCard.vue'
import ThreatReportDialog from '@/components/ThreatReportDialog.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Searches VirusTotal for an internet address, a domain or a web address, once the connection is
 * tested. What VirusTotal reports opens in a window over the page, and the last search stays one
 * click away after the window is closed. A search that is refused says why, and how long to wait
 * when the limits of the access level are reached.
 */
const session = useSessionStore()
const query = ref('')
const busy = ref(false)
const problem = ref<string | null>(null)
const last = ref<Lookup | null>(null)
const reportOpen = ref(false)

async function search() {
  const subject = query.value.trim()
  if (!subject || busy.value) return
  busy.value = true
  problem.value = null
  try {
    last.value = await session.change((token) => searchThreatIntel(subject, token))
    reportOpen.value = true
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <SectionCard
    title="Look up a threat"
    description="Ask VirusTotal about an IP address, a domain or a web address. Each search counts toward VirusTotal's limits, so AresGate spaces them out."
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
      v-if="problem"
      type="error"
      variant="tonal"
      class="threat-lookup__problem"
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

.threat-lookup__problem {
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
