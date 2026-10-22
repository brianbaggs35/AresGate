<script setup lang="ts">
import { ArrowLeft, LogIn, ShieldCheck } from '@lucide/vue'
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
/** Set once the password is right on an account that has an authenticator app: the code is the
 * second step, and this is what it is sent back with. */
const challenge = ref<string | null>(null)
const code = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

const required = (what: string) => (value: string) => value.trim() !== '' || `Enter ${what}.`

async function submit(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  busy.value = true
  error.value = null
  try {
    challenge.value = await session.logIn({ username: username.value, password: password.value })
    password.value = ''
    if (challenge.value === null) await router.replace(landingPage(route.query))
  } catch (signInError) {
    error.value = errorMessage(signInError)
    password.value = ''
  } finally {
    busy.value = false
  }
}

async function submitCode(event: SubmitEventPromise) {
  if (!(await isValid(event)) || challenge.value === null) return
  busy.value = true
  error.value = null
  try {
    await session.logInWithCode(challenge.value, code.value)
    await router.replace(landingPage(route.query))
  } catch (codeError) {
    error.value = errorMessage(codeError)
    code.value = ''
  } finally {
    busy.value = false
  }
}

function startOver() {
  challenge.value = null
  code.value = ''
  error.value = null
}
</script>

<template>
  <AuthLayout
    :title="challenge === null ? 'Sign in' : 'Enter a code'"
    :subtitle="
      challenge === null
        ? 'Welcome back to AresGate.'
        : 'Open your authenticator app and enter the 6-digit code it shows, or enter a recovery code.'
    "
  >
    <v-alert
      v-if="session.expired && !error && challenge === null"
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
    <v-form v-if="challenge !== null" validate-on="submit" @submit.prevent="submitCode">
      <v-text-field
        v-model="code"
        v-focus
        label="Code"
        autocomplete="one-time-code"
        autocapitalize="off"
        spellcheck="false"
        :rules="[required('a code')]"
        data-test="code"
      />
      <v-btn
        type="submit"
        color="primary"
        size="large"
        block
        :prepend-icon="ShieldCheck"
        :loading="busy"
        data-test="verify"
      >
        Verify
      </v-btn>
      <v-btn
        variant="text"
        block
        class="mt-2"
        :prepend-icon="ArrowLeft"
        data-test="start-over"
        @click="startOver"
      >
        Use a different account
      </v-btn>
    </v-form>
    <v-form v-else validate-on="submit" @submit.prevent="submit">
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
