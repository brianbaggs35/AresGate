<script setup lang="ts">
import { ArrowLeft, ArrowRight, UserPlus } from '@lucide/vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { SubmitEventPromise } from 'vuetify'

import { ApiError, errorMessage } from '@/api/client'
import AuthLayout from '@/components/AuthLayout.vue'
import PasswordField from '@/components/PasswordField.vue'
import { isValid, vFocus } from '@/form'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

const step = ref<1 | 2>(1)
const code = ref('')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

// What the API accepts. It says more when a password is too easy to guess; these catch typos.
const CODE_LENGTH = 12
const USERNAME_FORMAT = /^[a-z0-9._@-]{3,64}$/
const MIN_PASSWORD = 12
const MAX_PASSWORD = 128

/** The code as typed, in the letters the API reads: it ignores case, spaces and dashes. */
const codeLetters = (value: string) => value.toUpperCase().replace(/[^A-Z2-9]/g, '')

const rules = {
  code: (value: string) =>
    codeLetters(value).length === CODE_LENGTH ||
    'The code is 12 letters and numbers, such as K7QD-3MWX-9HPA.',
  username: (value: string) =>
    USERNAME_FORMAT.test(value.trim().toLowerCase()) ||
    'Use 3 to 64 letters, numbers, dots, dashes, underscores or @ signs.',
  password: (value: string) =>
    (value.length >= MIN_PASSWORD && value.length <= MAX_PASSWORD) ||
    `Use ${MIN_PASSWORD} to ${MAX_PASSWORD} characters. A few words in a row are easy to remember.`,
  confirmation: (value: string) => value === password.value || "The passwords don't match.",
}

async function continueToAccount(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  error.value = null
  step.value = 2
}

function goBack() {
  error.value = null
  step.value = 1
}

async function createAccount(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  busy.value = true
  error.value = null
  try {
    await session.setUp({ code: code.value, username: username.value, password: password.value })
    await router.replace({ name: 'home' })
  } catch (setupError) {
    error.value = errorMessage(setupError)
    if (setupError instanceof ApiError) {
      // A wrong code is the only thing step one can fix.
      if (setupError.status === 403) step.value = 1
      if (setupError.status === 409) {
        await session.restore()
        // Someone else got there first, so this is a sign-in now.
        if (!session.setupRequired) await router.replace({ name: 'sign-in' })
      }
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout
    title="Set up AresGate"
    :subtitle="
      step === 1
        ? 'Step 1 of 2. Prove you can read AresGate’s log.'
        : 'Step 2 of 2. Create the account you will sign in with.'
    "
  >
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" data-test="setup-error">
      {{ error }}
    </v-alert>
    <v-form
      :key="step"
      validate-on="submit"
      @submit.prevent="step === 1 ? continueToAccount($event) : createAccount($event)"
    >
      <template v-if="step === 1">
        <p class="text-body-medium mb-4">
          When AresGate starts for the first time, it prints a one-time setup code in its log. Run
          <code>make logs</code>, or <code>docker compose logs aresgate</code>, and look for “enter
          this setup code”.
        </p>
        <v-text-field
          v-model="code"
          v-focus
          label="Setup code"
          placeholder="K7QD-3MWX-9HPA"
          autocomplete="off"
          autocapitalize="characters"
          spellcheck="false"
          :rules="[rules.code]"
          data-test="setup-code"
        />
        <v-btn
          type="submit"
          color="primary"
          size="large"
          block
          :append-icon="ArrowRight"
          data-test="continue"
        >
          Continue
        </v-btn>
      </template>
      <template v-else>
        <v-text-field
          v-model="username"
          v-focus
          label="Username"
          autocomplete="username"
          autocapitalize="off"
          spellcheck="false"
          :rules="[rules.username]"
          data-test="username"
        />
        <PasswordField
          v-model="password"
          label="Password"
          creating
          :rules="[rules.password]"
          data-test="password"
        />
        <PasswordField
          v-model="confirmation"
          label="Confirm password"
          creating
          :rules="[rules.confirmation]"
          data-test="confirm-password"
        />
        <v-btn
          type="submit"
          color="primary"
          size="large"
          block
          class="mb-2"
          :prepend-icon="UserPlus"
          :loading="busy"
          data-test="create-account"
        >
          Create account
        </v-btn>
        <v-btn
          block
          variant="text"
          :prepend-icon="ArrowLeft"
          :disabled="busy"
          data-test="back"
          @click="goBack"
        >
          Back
        </v-btn>
      </template>
    </v-form>
  </AuthLayout>
</template>
