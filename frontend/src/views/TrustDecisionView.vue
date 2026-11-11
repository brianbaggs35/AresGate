<script setup lang="ts">
import { CircleCheck, ShieldCheck, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, errorMessage } from '@/api/client'
import {
  changeTrust,
  fetchTrusted,
  revokeTrust,
  type TrustDetail,
  type TrustRequest,
} from '@/api/trust'
import AppPage from '@/components/AppPage.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import TrustForm from '@/components/TrustForm.vue'
import { formatAgo, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { LEVEL, appliedText } from '@/trust'

/**
 * One trust decision: what it is about, how much it is trusted and why, all of which can be
 * changed here, what it has kept quiet and the incidents it was applied to, and a way to take it
 * back. Changing what it is about judges again the incidents it no longer reaches and those it
 * now does.
 */
const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const rule = ref<TrustDetail | null>(null)
const loadError = ref<string | null>(null)
const missing = ref(false)
const loading = ref(false)

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = ref(false)
const confirming = ref(false)

async function load() {
  loading.value = true
  try {
    rule.value = await session.call(() => fetchTrusted(id.value))
    loadError.value = null
    missing.value = false
  } catch (error) {
    loadError.value = errorMessage(error)
    missing.value = error instanceof ApiError && error.status === 404
  } finally {
    loading.value = false
  }
}

async function save(request: TrustRequest) {
  busy.value = true
  failure.value = null
  notice.value = null
  try {
    await session.change((token) => changeTrust(id.value, request, token))
    await load()
    notice.value = 'Saved. What it reaches is judged again.'
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

async function takeBack() {
  busy.value = true
  failure.value = null
  try {
    await session.change((token) => revokeTrust(id.value, token))
    await router.push({ name: 'trust' })
  } catch (error) {
    failure.value = errorMessage(error)
    confirming.value = false
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppPage width="wide" class="decision">
    <template v-if="rule">
      <PageHeader :title="rule.about" :back="{ to: { name: 'trust' }, label: 'Trust' }">
        <template #icon>
          <v-icon :icon="ShieldCheck" size="32" />
        </template>
        <template #badge>
          <v-chip
            size="small"
            variant="tonal"
            :color="LEVEL[rule.verdict].color"
            :prepend-icon="LEVEL[rule.verdict].icon"
            data-test="decision-level"
          >
            {{ LEVEL[rule.verdict].label }}
          </v-chip>
        </template>
        <template #actions>
          <v-btn
            variant="tonal"
            color="error"
            :prepend-icon="Trash2"
            data-test="decision-revoke"
            @click="confirming = true"
          >
            Take it back
          </v-btn>
        </template>
      </PageHeader>

      <v-alert type="info" variant="tonal" data-test="decision-info">
        <p class="text-title-medium">
          {{ LEVEL[rule.verdict].label }}: {{ LEVEL[rule.verdict].meaning }}
        </p>
        <p class="text-body-large" data-test="decision-applied">
          {{ appliedText(rule)
          }}<template v-if="rule.last_hit_at"> , last {{ formatAgo(rule.last_hit_at) }}</template
          >. It holds for every program that reports it, not only one.
        </p>
      </v-alert>

      <output v-if="notice" class="decision__notice text-body-large" data-test="decision-notice">
        <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
        {{ notice }}
      </output>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="decision-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>

      <SectionCard
        title="What it says"
        description="Change any of it. Saying the same as another decision is refused, so that each thing has one."
        data-test="decision-form-card"
      >
        <TrustForm
          :rule="rule"
          :busy="busy"
          :failure="failure"
          save-label="Save"
          @save="save"
          @cancel="load"
        />
      </SectionCard>

      <SectionCard
        title="What it was applied to"
        description="The incidents with alerts this decision kept from raising an alarm, the latest first."
        data-test="decision-applied-card"
      >
        <ul v-if="rule.applied_to.length" class="decision__list" data-test="decision-incidents">
          <li v-for="incident in rule.applied_to" :key="incident.id" class="applied">
            <router-link
              :to="{ name: 'incident', params: { id: incident.id } }"
              class="applied__link"
              data-test="applied-incident"
            >
              <span class="text-title-medium applied__title">{{ incident.title }}</span>
              <span class="text-body-medium text-medium-emphasis">
                {{ formatCount(incident.signals) }}
                {{ incident.signals === 1 ? 'alert' : 'alerts' }}, last
                {{ formatAgo(incident.last_seen_at) }}
              </span>
              <span class="applied__chips">
                <SeverityChip :severity="incident.severity" />
                <IncidentStatusChip :status="incident.status" />
              </span>
            </router-link>
          </li>
        </ul>
        <EmptyState
          v-else
          title="Not applied to anything yet"
          description="It will be, the next time something it matches is reported."
          data-test="decision-none"
        />
      </SectionCard>
    </template>
    <template v-else-if="loadError">
      <PageHeader title="Trust decision" :back="{ to: { name: 'trust' }, label: 'Trust' }" />
      <LoadError
        :message="missing ? `${loadError} It may have been taken back.` : loadError"
        :can-retry="!missing"
        :loading="loading"
        data-test="decision-error"
        @retry="load"
      />
    </template>
    <v-skeleton-loader v-else type="article, article" data-test="decision-loading" />

    <ConfirmDialog
      v-model="confirming"
      title="Take this back?"
      confirm-label="Take it back"
      destructive
      :busy="busy"
      @confirm="takeBack"
    >
      <p v-if="rule" class="mb-2">{{ rule.about }}</p>
      <p>It is judged as if you had never said it, which means it can raise alarms again.</p>
    </ConfirmDialog>
  </AppPage>
</template>

<style scoped>
.decision :deep(p) {
  margin: 0;
}

.decision__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.decision__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.applied {
  border-block-start: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.applied:first-child {
  border-block-start: 0;
}

.applied__link {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-height: 44px;
  padding: 0.75rem 0.5rem;
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
}

.applied__link:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.applied__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.applied__title {
  overflow-wrap: anywhere;
}

.applied__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}
</style>
