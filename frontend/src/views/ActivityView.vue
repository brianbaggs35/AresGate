<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { fetchRecentActivity, type AuditEvent } from '@/api/audit'
import { errorMessage } from '@/api/client'
import ActivityList from '@/components/ActivityList.vue'
import EmptyState from '@/components/EmptyState.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

const RECENT = 20

const session = useSessionStore()

const events = ref<AuditEvent[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function loadActivity() {
  loading.value = true
  error.value = null
  try {
    events.value = await session.call(() => fetchRecentActivity(RECENT))
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

onMounted(loadActivity)
</script>

<template>
  <SectionCard
    title="Recent activity"
    description="Sign-ins, wrong guesses and sign-outs, and changes to passwords, passkeys, two-step verification and integrations. If something here wasn't you, change your password."
    data-test="activity-card"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="refresh-activity"
        @click="loadActivity"
      >
        Refresh
      </v-btn>
    </template>
    <v-alert v-if="error" type="error" variant="tonal" data-test="activity-error">
      {{ error }}
    </v-alert>
    <ActivityList v-else-if="events?.length" :events="events" />
    <EmptyState v-else-if="events" title="Nothing has happened yet." data-test="no-activity" />
    <v-skeleton-loader v-else type="list-item-two-line, list-item-two-line, list-item-two-line" />
  </SectionCard>
</template>
