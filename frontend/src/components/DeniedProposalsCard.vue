<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  fetchDenials,
  forgetAllDenials,
  forgetDenial,
  type Denial,
  type Denials,
} from '@/api/aiDenials'
import { errorMessage } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatDateTime, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > AI > Denied suggestions: the changes the assistant proposed that you denied, which it
 * is not to propose again for a while (or until the incident changes). Each can be forgotten, so
 * the assistant may propose it again, and all of them can.
 */
const session = useSessionStore()

const found = ref<Denials | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const failure = ref<string | null>(null)
const busy = ref(false)
const asking = ref(false)

/** What each change is, in words. */
const WORDS: Record<string, string> = {
  open: 'Reopen',
  investigating: 'Start investigating',
  resolved: 'Mark as resolved',
  dismissed: 'Dismiss',
  not_suspicious: 'Call not suspicious',
  low_priority: 'Call low priority',
  threat: 'Call a real threat',
}

const wording = (denial: Denial) => WORDS[denial.value] ?? denial.value

async function load() {
  loading.value = true
  loadError.value = null
  try {
    found.value = await session.call(fetchDenials)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function forget(denial: Denial) {
  failure.value = null
  busy.value = true
  try {
    await session.change((token) => forgetDenial(denial.id, token))
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

async function forgetAll() {
  failure.value = null
  busy.value = true
  try {
    await session.change((token) => forgetAllDenials(token))
    asking.value = false
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
    asking.value = false
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <SectionCard
    title="Denied suggestions"
    description="When you deny something the assistant proposes, it is remembered, so the assistant does not suggest it again. It stops by itself after a while, or sooner if the incident changes."
    data-test="denials-card"
  >
    <template v-if="found && found.items.length > 0" #actions>
      <v-btn variant="text" :disabled="busy" data-test="denials-forget-all" @click="asking = true">
        Forget all
      </v-btn>
    </template>

    <LoadError
      v-if="loadError && !found"
      :message="loadError"
      :loading="loading"
      retry-test-id="denials-retry"
      data-test="denials-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!found" type="list-item-two-line" />
    <template v-else>
      <p
        v-if="found.items.length === 0"
        class="text-body-large text-medium-emphasis"
        data-test="denials-empty"
      >
        Nothing is denied. What you deny in the assistant's proposals is listed here for
        {{ formatCount(found.days) }} days.
      </p>
      <ul v-else class="denials" aria-label="Denied suggestions" data-test="denials-list">
        <li v-for="denial in found.items" :key="denial.id" class="denials__item">
          <div class="denials__what">
            <span class="text-title-small" data-test="denial-what">{{ wording(denial) }}</span>
            <router-link
              :to="{ name: 'incident', params: { id: String(denial.incident_id) } }"
              class="text-body-large"
              data-test="denial-incident"
            >
              {{ denial.title }}
            </router-link>
            <span class="text-body-medium text-medium-emphasis">
              Denied
              <time :datetime="denial.denied_at">{{ formatDateTime(denial.denied_at) }}</time>
              and stands until
              <time :datetime="denial.expires_at">{{ formatDateTime(denial.expires_at) }}</time>
              unless the incident changes.
            </span>
          </div>
          <v-btn
            variant="text"
            :disabled="busy"
            :aria-label="`Forget: ${wording(denial)}, ${denial.title}`"
            data-test="denial-forget"
            @click="forget(denial)"
          >
            Forget
          </v-btn>
        </li>
      </ul>
      <v-alert
        v-if="failure"
        type="error"
        variant="tonal"
        role="alert"
        class="mt-4"
        data-test="denials-failure"
      >
        {{ failure }}
      </v-alert>
    </template>
    <ConfirmDialog
      v-model="asking"
      title="Forget everything you denied?"
      confirm-label="Forget all"
      destructive
      :busy="busy"
      @confirm="forgetAll"
    >
      The assistant may propose any of these again.
    </ConfirmDialog>
  </SectionCard>
</template>

<style scoped>
.denials {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.denials__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding-block-end: 0.75rem;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.denials__item:last-child {
  padding-block-end: 0;
  border-block-end: 0;
}

.denials__what {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 14rem;
  overflow-wrap: anywhere;
}
</style>
