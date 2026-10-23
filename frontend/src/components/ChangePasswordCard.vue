<script setup lang="ts">
import { KeyRound } from '@lucide/vue'
import { ref, watch } from 'vue'
import type { SubmitEventPromise } from 'vuetify'

import { changePassword } from '@/api/account'
import { ApiError, errorMessage } from '@/api/client'
import PasswordField from '@/components/PasswordField.vue'
import SectionCard from '@/components/SectionCard.vue'
import { isValid } from '@/form'
import { useSessionStore } from '@/stores/session'

// What the API accepts. It says more when a password is too easy to guess; these catch typos.
const MIN_PASSWORD = 12
const MAX_PASSWORD = 128

const session = useSessionStore()

const current = ref('')
const next = ref('')
const confirmation = ref('')
const busy = ref(false)
const done = ref<string | null>(null)
/** Something that went wrong with no field to point at. */
const failure = ref<string | null>(null)
/** What is wrong with the current password or the new one, shown at its field. */
const currentProblem = ref<string[]>([])
const nextProblem = ref<string[]>([])

const rules = {
  current: (value: string) => value.length > 0 || 'Enter your current password.',
  next: (value: string) =>
    (value.length >= MIN_PASSWORD && value.length <= MAX_PASSWORD) ||
    `Use ${MIN_PASSWORD} to ${MAX_PASSWORD} characters. A few words in a row are easy to remember.`,
  confirmation: (value: string) => value === next.value || "The passwords don't match.",
}

// A problem is about what was typed, so it goes away when that changes.
watch(current, () => (currentProblem.value = []))
watch(next, () => (nextProblem.value = []))

const saved = (ended: number) =>
  ended === 0
    ? 'Your password was changed.'
    : `Your password was changed, and ${ended === 1 ? '1 other sign-in was' : `${ended.toString()} other sign-ins were`} ended.`

async function submit(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  busy.value = true
  done.value = null
  failure.value = null
  try {
    const { ended } = await session.change((token) =>
      changePassword(current.value, next.value, token),
    )
    current.value = next.value = confirmation.value = ''
    done.value = saved(ended)
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) currentProblem.value = [error.message]
    else if (error instanceof ApiError && error.status === 422) nextProblem.value = [error.message]
    else failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <SectionCard
    title="Password"
    description="Changing it signs you out everywhere else, so anyone who had the old one is out."
    data-test="password-card"
  >
    <v-alert v-if="done" type="success" variant="tonal" class="mb-4" data-test="password-changed">
      {{ done }}
    </v-alert>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" data-test="password-error">
      {{ failure }}
    </v-alert>
    <v-form validate-on="submit" @submit.prevent="submit">
      <PasswordField
        v-model="current"
        label="Current password"
        :rules="[rules.current]"
        :error-messages="currentProblem"
        data-test="current-password"
      />
      <PasswordField
        v-model="next"
        label="New password"
        creating
        :rules="[rules.next]"
        :error-messages="nextProblem"
        data-test="new-password"
      />
      <PasswordField
        v-model="confirmation"
        label="Confirm new password"
        creating
        :rules="[rules.confirmation]"
        data-test="confirm-new-password"
      />
      <v-btn
        type="submit"
        color="primary"
        :prepend-icon="KeyRound"
        :loading="busy"
        data-test="change-password"
      >
        Change password
      </v-btn>
    </v-form>
  </SectionCard>
</template>
