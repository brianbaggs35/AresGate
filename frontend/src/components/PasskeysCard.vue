<script setup lang="ts">
import { KeyRound, Plus, Trash2 } from '@lucide/vue'
import { nextTick, onMounted, ref } from 'vue'
import type { SubmitEventPromise } from 'vuetify'

import { errorMessage } from '@/api/client'
import {
  addPasskey,
  fetchPasskeys,
  removePasskey,
  startAddingPasskey,
  type Passkey,
} from '@/api/passkeys'
import LoadError from '@/components/LoadError.vue'
import PasswordField from '@/components/PasswordField.vue'
import SectionCard from '@/components/SectionCard.vue'
import { describeBrowser, formatDateTime } from '@/format'
import { isValid, vFocus } from '@/form'
import { useSessionStore } from '@/stores/session'
import { createPasskey, passkeysSupported } from '@/webauthn'

/** What the card is showing: the passkeys, making one, or taking one off. */
type View = 'overview' | 'adding' | 'removing'

const session = useSessionStore()
const supported = passkeysSupported()

const passkeys = ref<Passkey[] | null>(null)
const loadError = ref<string | null>(null)
const view = ref<View>('overview')
const name = ref('')
const password = ref('')
/** The passkey the person is about to remove. */
const target = ref<Passkey | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const card = ref<{ focusTitle: () => void } | null>(null)

const required = (what: string) => (value: string) => value.trim() !== '' || `Enter ${what}.`

async function load() {
  loadError.value = null
  try {
    passkeys.value = await session.call(fetchPasskeys)
  } catch (listError) {
    loadError.value = errorMessage(listError)
  }
}

/** Shows another view, and moves the keyboard (and so a screen reader) back to the title when
 * it is the overview. The others begin with a field, which takes the focus itself. */
async function show(next: View) {
  view.value = next
  error.value = null
  password.value = ''
  name.value = next === 'adding' ? describeBrowser(navigator.userAgent) : ''
  await nextTick()
  if (next === 'overview') card.value?.focusTitle()
}

/** Runs one of the card's changes, showing why it failed. A password that was refused isn't
 * kept. */
async function attempt(change: () => Promise<void>) {
  busy.value = true
  error.value = null
  try {
    await change()
  } catch (changeError) {
    error.value = errorMessage(changeError)
    password.value = ''
  } finally {
    busy.value = false
  }
}

async function remove(passkey: Passkey) {
  target.value = passkey
  await show('removing')
}

async function add(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  await attempt(async () => {
    const challenge = await session.change((token) => startAddingPasskey(password.value, token))
    // The password has done its job, so it isn't kept while the device asks for its unlock.
    password.value = ''
    const credential = await createPasskey(challenge.options)
    await session.change((token) =>
      addPasskey(challenge.challenge_id, credential, name.value, token),
    )
    await show('overview')
    await load()
  })
}

async function confirmRemove(event: SubmitEventPromise) {
  if (!(await isValid(event)) || target.value === null) return
  const { id } = target.value
  await attempt(async () => {
    await session.change((token) => removePasskey(id, password.value, token))
    await show('overview')
    await load()
  })
}

const lastUsed = (passkey: Passkey) =>
  passkey.last_used_at ? `Last used ${formatDateTime(passkey.last_used_at)}` : 'Never used'

onMounted(load)
</script>

<template>
  <SectionCard ref="card" title="Passkeys" data-test="passkeys-card">
    <v-alert v-if="error" type="error" variant="tonal" class="my-4" data-test="passkeys-error">
      {{ error }}
    </v-alert>

    <template v-if="view === 'overview'">
      <p class="text-body-medium text-medium-emphasis mb-4">
        Sign in by unlocking your device with a fingerprint, your face or its PIN, instead of typing
        a password. A passkey also takes the place of two-step verification.
      </p>
      <LoadError
        v-if="loadError"
        :message="loadError"
        retry-test-id="passkeys-retry"
        class="my-4"
        data-test="passkeys-load-error"
        @retry="load"
      />
      <v-skeleton-loader v-else-if="!passkeys" type="list-item-two-line" />
      <template v-else>
        <ul v-if="passkeys.length" class="passkey-list mb-4" data-test="passkey-list">
          <li v-for="passkey in passkeys" :key="passkey.id" class="passkey-list__item">
            <KeyRound class="passkey-list__icon" aria-hidden="true" />
            <div class="passkey-list__text">
              <div class="text-body-large" data-test="passkey-name">{{ passkey.name }}</div>
              <div class="text-body-medium text-medium-emphasis" data-test="passkey-details">
                Added {{ formatDateTime(passkey.created_at) }} · {{ lastUsed(passkey) }}
              </div>
            </div>
            <v-btn
              variant="text"
              color="error"
              :prepend-icon="Trash2"
              :aria-label="`Remove ${passkey.name}`"
              data-test="remove-passkey"
              @click="remove(passkey)"
            >
              Remove
            </v-btn>
          </li>
        </ul>
        <p v-else class="text-body-large mb-4" data-test="no-passkeys">
          You haven't added a passkey yet.
        </p>
        <v-alert
          v-if="!supported"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          data-test="passkeys-unsupported"
        >
          This browser can't make a passkey. Use a recent version of Chrome, Edge, Firefox or Safari
          to add one.
        </v-alert>
        <v-btn
          v-else
          color="primary"
          :prepend-icon="Plus"
          data-test="add-passkey"
          @click="show('adding')"
        >
          Add a passkey
        </v-btn>
      </template>
    </template>

    <template v-else-if="view === 'adding'">
      <h3 class="text-title-medium mt-4 mb-2">Add a passkey</h3>
      <p class="text-body-large mb-4">
        Enter your password, then unlock this device when it asks. To use a phone or a security key
        instead, choose it in the prompt your browser shows.
      </p>
      <v-form validate-on="submit" @submit.prevent="add">
        <v-text-field
          v-model="name"
          v-focus
          label="Name"
          hint="Something to tell it apart by, such as Work laptop."
          maxlength="64"
          :rules="[required('a name')]"
          data-test="new-passkey-name"
        />
        <PasswordField
          v-model="password"
          label="Password"
          :rules="[required('your password')]"
          data-test="new-passkey-password"
        />
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            type="submit"
            color="primary"
            :prepend-icon="KeyRound"
            :loading="busy"
            data-test="create-passkey"
          >
            Add passkey
          </v-btn>
          <v-btn variant="text" data-test="cancel" @click="show('overview')">Cancel</v-btn>
        </div>
      </v-form>
    </template>

    <template v-else>
      <h3 class="text-title-medium mt-4 mb-2">Remove {{ target?.name }}</h3>
      <p class="text-body-large mb-4">
        This device or key can no longer sign in to AresGate. It keeps its own copy, which you can
        delete in its settings. Enter your password to remove it.
      </p>
      <v-form validate-on="submit" @submit.prevent="confirmRemove">
        <PasswordField
          v-model="password"
          v-focus
          label="Password"
          :rules="[required('your password')]"
          data-test="remove-passkey-password"
        />
        <div class="d-flex flex-wrap ga-3">
          <v-btn
            type="submit"
            color="error"
            :prepend-icon="Trash2"
            :loading="busy"
            data-test="confirm-remove-passkey"
          >
            Remove passkey
          </v-btn>
          <v-btn variant="text" data-test="cancel" @click="show('overview')">Cancel</v-btn>
        </div>
      </v-form>
    </template>
  </SectionCard>
</template>

<style scoped>
.passkey-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.passkey-list__item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
}

.passkey-list__item + .passkey-list__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.passkey-list__icon {
  flex: none;
}

.passkey-list__text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
