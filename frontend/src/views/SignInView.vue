<script setup lang="ts">
import { LogIn } from '@lucide/vue'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { SubmitEventPromise } from 'vuetify'

import { errorMessage } from '@/api/client'
import AuthLayout from '@/components/AuthLayout.vue'
import PasswordField from '@/components/PasswordField.vue'
import { isValid, vFocus } from '@/form'
import { landingPage } from '@/router/guard'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const required = (what: string) => (value: string) => value.trim() !== '' || `Enter ${what}.`

async function submit(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  busy.value = true
  error.value = null
  try {
    await session.logIn({ username: username.value, password: password.value })
    await router.replace(landingPage(route.query))
  } catch (signInError) {
    error.value = errorMessage(signInError)
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout title="Sign in" subtitle="Welcome back to AresGate.">
    <v-alert
      v-if="session.expired && !error"
      type="info"
      variant="tonal"
      class="mb-4"
      data-test="signed-out-notice"
    >
      Your sign-in ended. Sign in again to carry on.
    </v-alert>
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" data-test="sign-in-error">
      {{ error }}
    </v-alert>
    <v-form validate-on="submit" @submit.prevent="submit">
      <v-text-field
        v-model="username"
        v-focus
        label="Username"
        autocomplete="username"
        autocapitalize="off"
        spellcheck="false"
        :rules="[required('your username')]"
        data-test="username"
      />
      <PasswordField
        v-model="password"
        label="Password"
        :rules="[required('your password')]"
        data-test="password"
      />
      <v-btn
        type="submit"
        color="primary"
        size="large"
        block
        :prepend-icon="LogIn"
        :loading="busy"
        data-test="sign-in"
      >
        Sign in
      </v-btn>
    </v-form>
  </AuthLayout>
</template>
