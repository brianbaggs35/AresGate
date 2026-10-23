<script setup lang="ts">
import { LogOut, RefreshCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchRecentActivity, type AuditEvent } from '@/api/audit'
import { errorMessage } from '@/api/client'
import ActivityList from '@/components/ActivityList.vue'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PasskeysCard from '@/components/PasskeysCard.vue'
import SectionCard from '@/components/SectionCard.vue'
import TwoFactorCard from '@/components/TwoFactorCard.vue'
import { useSessionStore } from '@/stores/session'

const RECENT = 20

const session = useSessionStore()
const router = useRouter()

const events = ref<AuditEvent[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const signOutError = ref<string | null>(null)

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

async function signOut() {
  signOutError.value = null
  try {
    await session.logOut()
    await router.push({ name: 'sign-in' })
  } catch (logOutError) {
    signOutError.value = errorMessage(logOutError)
  }
}

onMounted(loadActivity)
</script>

<template>
  <AppPage width="narrow">
    <PageHeader
      title="Security"
      description="Your account, how you sign in, and what has happened lately."
    />

    <SectionCard title="Your account" data-test="account-card">
      <p class="text-body-large mb-4">
        Signed in as <strong data-test="account-name">{{ session.username }}</strong>
      </p>
      <v-alert
        v-if="signOutError"
        type="error"
        variant="tonal"
        class="mb-4"
        data-test="sign-out-here-error"
      >
        {{ signOutError }}
      </v-alert>
      <v-btn variant="tonal" :prepend-icon="LogOut" data-test="sign-out-here" @click="signOut">
        Sign out
      </v-btn>
    </SectionCard>

    <PasskeysCard />

    <TwoFactorCard />

    <SectionCard
      title="Recent activity"
      description="Sign-ins, wrong guesses and sign-outs, and changes to passkeys and two-step verification. If something here wasn't you, change your password."
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
  </AppPage>
</template>
