<script setup lang="ts">
import { CircleUser, LogOut, Settings } from '@lucide/vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

const failure = ref<string | null>(null)
const showFailure = ref(false)

async function signOut() {
  try {
    await session.logOut()
    await router.push({ name: 'sign-in' })
  } catch (error) {
    failure.value = errorMessage(error)
    showFailure.value = true
  }
}
</script>

<template>
  <v-menu location="bottom end">
    <template #activator="{ props: activator }">
      <v-btn
        v-bind="activator"
        :icon="CircleUser"
        variant="text"
        :aria-label="`Account: ${session.username}`"
        data-test="user-menu"
      />
    </template>
    <v-card min-width="200">
      <div class="text-body-medium text-medium-emphasis px-4 py-3" data-test="user-name">
        Signed in as {{ session.username }}
      </div>
      <v-divider />
      <!-- The list's own role (list) wants list items, and these are a link and a button. -->
      <v-list density="compact" role="menu" aria-label="Account" tabindex="-1">
        <v-list-item
          role="menuitem"
          :prepend-icon="Settings"
          title="Settings"
          :to="{ name: 'settings-account' }"
          data-test="user-settings"
        />
        <v-list-item
          role="menuitem"
          :prepend-icon="LogOut"
          title="Sign out"
          data-test="sign-out"
          @click="signOut"
        />
      </v-list>
    </v-card>
  </v-menu>
  <v-snackbar v-model="showFailure" color="error" data-test="sign-out-error">
    {{ failure }}
  </v-snackbar>
</template>
