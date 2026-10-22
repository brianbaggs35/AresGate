<script setup lang="ts">
import { LogOut, RefreshCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchRecentActivity, type AuditEvent } from '@/api/audit'
import { errorMessage } from '@/api/client'
import ActivityList from '@/components/ActivityList.vue'
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
  } catch (signOutFailure) {
    signOutError.value = errorMessage(signOutFailure)
  }
}

onMounted(loadActivity)
</script>

<template>
  <v-container class="py-8" max-width="720">
    <v-card class="pa-6 mb-6" data-test="account-card">
      <h2 class="text-title-large mb-1">Your account</h2>
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
    </v-card>

    <v-card class="pa-6" data-test="activity-card">
      <div class="d-flex align-center justify-space-between ga-3 mb-1">
        <h2 class="text-title-large">Recent activity</h2>
        <v-btn
          variant="text"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="refresh-activity"
          @click="loadActivity"
        >
          Refresh
        </v-btn>
      </div>
      <p class="text-body-medium text-medium-emphasis mb-2">
        Sign-ins, wrong guesses and sign-outs. If something here wasn't you, change your password.
      </p>
      <v-alert v-if="error" type="error" variant="tonal" data-test="activity-error">
        {{ error }}
      </v-alert>
      <ActivityList v-else-if="events?.length" :events="events" />
      <p v-else-if="events" class="text-body-large py-4" data-test="no-activity">
        Nothing has happened yet.
      </p>
      <v-skeleton-loader v-else type="list-item-two-line, list-item-two-line, list-item-two-line" />
    </v-card>
  </v-container>
</template>
