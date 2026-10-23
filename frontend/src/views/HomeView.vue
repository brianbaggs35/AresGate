<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed, onMounted } from 'vue'

import AppPage from '@/components/AppPage.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useHealthStore } from '@/stores/health'

const store = useHealthStore()

const api = computed(() => {
  if (store.error) return { color: 'error', label: 'Unreachable' }
  if (store.health) return { color: 'success', label: 'Running' }
  return { color: 'grey', label: 'Checking…' }
})

const database = computed(() => {
  if (store.health?.database === 'ok') return { color: 'success', label: 'Connected' }
  if (store.health) return { color: 'warning', label: 'Unavailable' }
  return { color: 'grey', label: 'Unknown' }
})

onMounted(() => store.refresh())
</script>

<template>
  <AppPage width="narrow">
    <PageHeader
      title="AresGate"
      description="Your home network's security analyst. Integrations and dashboards are on their way."
    />
    <SectionCard title="Status" data-test="status-card">
      <div class="d-flex flex-wrap ga-3 mb-6">
        <v-chip :color="api.color" variant="tonal" data-test="api-status">
          API: {{ api.label }}
        </v-chip>
        <v-chip :color="database.color" variant="tonal" data-test="database-status">
          Database: {{ database.label }}
        </v-chip>
      </div>
      <v-btn
        color="primary"
        variant="tonal"
        :prepend-icon="RefreshCw"
        :loading="store.loading"
        data-test="refresh"
        @click="store.refresh()"
      >
        Check again
      </v-btn>
    </SectionCard>
  </AppPage>
</template>
