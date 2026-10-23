<script setup lang="ts">
import { LogOut } from '@lucide/vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import ChangePasswordCard from '@/components/ChangePasswordCard.vue'
import PasskeysCard from '@/components/PasskeysCard.vue'
import SectionCard from '@/components/SectionCard.vue'
import TwoFactorCard from '@/components/TwoFactorCard.vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

const signOutError = ref<string | null>(null)

async function signOut() {
  signOutError.value = null
  try {
    await session.logOut()
    await router.push({ name: 'sign-in' })
  } catch (logOutError) {
    signOutError.value = errorMessage(logOutError)
  }
}
</script>

<template>
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

  <ChangePasswordCard />

  <PasskeysCard />

  <TwoFactorCard />
</template>
