<script setup lang="ts">
import { Copy, RefreshCw, ShieldCheck, ShieldOff, Smartphone } from '@lucide/vue'
import { nextTick, onMounted, ref } from 'vue'
import type { SubmitEventPromise } from 'vuetify'

import { errorMessage } from '@/api/client'
import {
  confirmTwoFactor,
  fetchTwoFactorStatus,
  renewRecoveryCodes,
  startTwoFactor,
  turnOffTwoFactor,
  type Enrollment,
  type TwoFactorStatus,
} from '@/api/two-factor'
import LoadError from '@/components/LoadError.vue'
import PasswordField from '@/components/PasswordField.vue'
import QrCode from '@/components/QrCode.vue'
import SectionCard from '@/components/SectionCard.vue'
import { isValid, vFocus } from '@/form'
import { useSessionStore } from '@/stores/session'

/** What the card is showing, apart from adding an app, which is whenever there is an `enrollment`. */
type View = 'overview' | 'codes' | 'renewing' | 'turning-off'

/** At or below this many recovery codes, the card suggests making new ones. */
const RUNNING_LOW = 3

const session = useSessionStore()

const status = ref<TwoFactorStatus | null>(null)
const loadError = ref<string | null>(null)
const view = ref<View>('overview')
const enrollment = ref<Enrollment | null>(null)
const recoveryCodes = ref<string[]>([])
const code = ref('')
const password = ref('')
const saved = ref(false)
const copyNote = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const card = ref<{ focusTitle: () => void } | null>(null)
const codesTitle = ref<HTMLElement | null>(null)

const required = (what: string) => (value: string) => value.trim() !== '' || `Enter ${what}.`

/** A key in groups of four, which is easier to type in. */
const inGroups = (key: string) => key.replace(/(.{4})(?=.)/g, '$1 ')

async function load() {
  loadError.value = null
  try {
    status.value = await session.call(fetchTwoFactorStatus)
  } catch (statusError) {
    loadError.value = errorMessage(statusError)
  }
}

/** Shows another view, and moves the keyboard (and so a screen reader) to where it begins,
 * unless it begins with a field, which takes the focus itself. */
async function show(next: View) {
  view.value = next
  error.value = null
  code.value = ''
  password.value = ''
  await nextTick()
  if (next === 'overview') card.value?.focusTitle()
  if (next === 'codes') codesTitle.value?.focus()
}

/** Runs one of the card's changes, showing why it failed. A code or password that was refused
 * isn't kept. */
async function attempt(change: () => Promise<void>) {
  busy.value = true
  error.value = null
  try {
    await change()
  } catch (changeError) {
    error.value = errorMessage(changeError)
    code.value = ''
    password.value = ''
  } finally {
    busy.value = false
  }
}

/** Shows the recovery codes that a change just made. */
async function showCodes(codes: string[]) {
  recoveryCodes.value = codes
  saved.value = false
  copyNote.value = null
  await show('codes')
  await load()
}

const begin = () =>
  attempt(async () => {
    enrollment.value = await session.change(startTwoFactor)
  })

async function cancelAdding() {
  enrollment.value = null
  await show('overview')
}

async function confirm(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  await attempt(async () => {
    const codes = await session.change((token) => confirmTwoFactor(code.value, token))
    enrollment.value = null
    await showCodes(codes)
  })
}

async function renew(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  await attempt(async () => {
    await showCodes(await session.change((token) => renewRecoveryCodes(code.value, token)))
  })
}

async function turnOff(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  await attempt(async () => {
    await session.change((token) => turnOffTwoFactor(password.value, code.value, token))
    await show('overview')
    await load()
  })
}

async function copyCodes() {
  try {
    await navigator.clipboard.writeText(recoveryCodes.value.join('\n'))
    copyNote.value = 'Copied.'
  } catch {
    copyNote.value = "Couldn't copy them. Select the codes and copy them by hand."
  }
}

async function finish() {
  recoveryCodes.value = []
  await show('overview')
}

const plural = (count: number) => `${count} recovery code${count === 1 ? '' : 's'}`

onMounted(load)
</script>

<template>
  <SectionCard ref="card" title="Two-step verification" data-test="two-factor-card">
    <v-alert v-if="error" type="error" variant="tonal" class="my-4" data-test="two-factor-error">
      {{ error }}
    </v-alert>

    <template v-if="enrollment">
      <h3 class="text-title-medium mt-4 mb-2">Add your authenticator app</h3>
      <p class="text-body-large mb-4">
        In an authenticator app, such as the one in your password manager, add an account by
        scanning this code.
      </p>
      <QrCode
        :text="enrollment.otpauth_uri"
        label="QR code for your authenticator app"
        class="mb-4"
      />
      <p class="text-body-medium mb-2">
        Can't scan it?
        <a :href="enrollment.otpauth_uri" data-test="open-in-app"
          >Open it in an app on this device</a
        >, or type this key into your app:
      </p>
      <code class="two-factor-codes__key mb-4" data-test="two-factor-key">
        {{ inGroups(enrollment.secret) }}
      </code>
      <v-form validate-on="submit" @submit.prevent="confirm">
        <v-text-field
          v-model="code"
          v-focus
          label="Code from the app"
          autocomplete="one-time-code"
          inputmode="numeric"
          spellcheck="false"
          hint="The 6 digits it shows now."
          :rules="[required('the code from the app')]"
          data-test="confirm-code"
        />
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            type="submit"
            color="primary"
            :prepend-icon="ShieldCheck"
            :loading="busy"
            data-test="confirm"
          >
            Turn on
          </v-btn>
          <v-btn variant="text" data-test="cancel" @click="cancelAdding">Cancel</v-btn>
        </div>
      </v-form>
    </template>

    <template v-else-if="view === 'overview'">
      <LoadError
        v-if="loadError"
        :message="loadError"
        retry-test-id="two-factor-retry"
        class="my-4"
        data-test="two-factor-load-error"
        @retry="load"
      />
      <v-skeleton-loader v-else-if="!status" type="list-item-two-line" />
      <template v-else-if="status.enabled">
        <p class="text-body-medium text-medium-emphasis mb-4">
          Signing in asks for a code from your authenticator app as well as your password.
        </p>
        <div class="d-flex align-center flex-wrap ga-3 mb-4">
          <v-chip
            color="success"
            variant="tonal"
            :prepend-icon="ShieldCheck"
            data-test="two-factor-state"
          >
            On
          </v-chip>
          <span class="text-body-large" data-test="recovery-codes-left">
            {{ plural(status.recovery_codes_left) }} left
          </span>
        </div>
        <v-alert
          v-if="status.recovery_codes_left <= RUNNING_LOW"
          :type="status.recovery_codes_left === 0 ? 'error' : 'warning'"
          variant="tonal"
          density="compact"
          class="mb-4"
          data-test="recovery-codes-low"
        >
          {{
            status.recovery_codes_left === 0
              ? 'You have no recovery codes left. Make new ones in case you lose your phone.'
              : 'You are running low on recovery codes. Make new ones.'
          }}
        </v-alert>
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            variant="tonal"
            :prepend-icon="RefreshCw"
            data-test="renew-codes"
            @click="show('renewing')"
          >
            Make new recovery codes
          </v-btn>
          <v-btn
            variant="text"
            color="error"
            :prepend-icon="ShieldOff"
            data-test="turn-off"
            @click="show('turning-off')"
          >
            Turn off
          </v-btn>
        </div>
      </template>
      <template v-else>
        <p class="text-body-medium text-medium-emphasis mb-4" data-test="two-factor-off">
          Off. Add an authenticator app and signing in will ask for a code from it as well as your
          password, so a stolen password isn't enough.
        </p>
        <v-btn
          color="primary"
          :prepend-icon="Smartphone"
          :loading="busy"
          data-test="add-app"
          @click="begin"
        >
          Add an authenticator app
        </v-btn>
      </template>
    </template>

    <template v-else-if="view === 'codes'">
      <h3 ref="codesTitle" tabindex="-1" class="text-title-medium mt-4 mb-2">
        Save your recovery codes
      </h3>
      <p class="text-body-large mb-4">
        If you lose your phone, each of these signs you in once, in place of a code from your app.
        They are shown only now, so keep them somewhere safe, such as your password manager.
      </p>
      <ul class="two-factor-codes mb-4" data-test="recovery-codes">
        <li v-for="recoveryCode in recoveryCodes" :key="recoveryCode" data-test="recovery-code">
          <code>{{ recoveryCode }}</code>
        </li>
      </ul>
      <div class="d-flex align-center flex-wrap ga-3 mb-2">
        <v-btn variant="tonal" :prepend-icon="Copy" data-test="copy-codes" @click="copyCodes">
          Copy the codes
        </v-btn>
        <output class="text-body-medium" data-test="copy-note">{{ copyNote }}</output>
      </div>
      <v-checkbox
        v-model="saved"
        label="I've saved these codes"
        hide-details
        data-test="codes-saved"
      />
      <v-btn color="primary" class="mt-4" :disabled="!saved" data-test="codes-done" @click="finish">
        Done
      </v-btn>
    </template>

    <template v-else-if="view === 'renewing'">
      <h3 class="text-title-medium mt-4 mb-2">Make new recovery codes</h3>
      <p class="text-body-large mb-4">
        This ends the recovery codes you have now. To show it's you, enter a code from your app, or
        a recovery code.
      </p>
      <v-form validate-on="submit" @submit.prevent="renew">
        <v-text-field
          v-model="code"
          v-focus
          label="Code"
          autocomplete="one-time-code"
          spellcheck="false"
          :rules="[required('a code')]"
          data-test="renew-code"
        />
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            type="submit"
            color="primary"
            :prepend-icon="RefreshCw"
            :loading="busy"
            data-test="renew"
          >
            Make new codes
          </v-btn>
          <v-btn variant="text" data-test="cancel" @click="show('overview')">Cancel</v-btn>
        </div>
      </v-form>
    </template>

    <template v-else>
      <h3 class="text-title-medium mt-4 mb-2">Turn off two-step verification</h3>
      <p class="text-body-large mb-4">
        Signing in will need only your password again. Enter it with a code from your app, or a
        recovery code.
      </p>
      <v-form validate-on="submit" @submit.prevent="turnOff">
        <PasswordField
          v-model="password"
          label="Password"
          :rules="[required('your password')]"
          data-test="turn-off-password"
        />
        <v-text-field
          v-model="code"
          label="Code"
          autocomplete="one-time-code"
          spellcheck="false"
          :rules="[required('a code')]"
          data-test="turn-off-code"
        />
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            type="submit"
            color="error"
            :prepend-icon="ShieldOff"
            :loading="busy"
            data-test="confirm-turn-off"
          >
            Turn off
          </v-btn>
          <v-btn variant="text" data-test="cancel" @click="show('overview')">Cancel</v-btn>
        </div>
      </v-form>
    </template>
  </SectionCard>
</template>

<style scoped>
.two-factor-codes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: 0.5rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.two-factor-codes li,
.two-factor-codes__key {
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
}

.two-factor-codes code,
.two-factor-codes__key {
  font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
  letter-spacing: 0.05em;
}

.two-factor-codes__key {
  display: inline-block;
  overflow-wrap: anywhere;
}
</style>
