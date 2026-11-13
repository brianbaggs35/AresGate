<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'

import type { MailServer, MailServerChange, Security } from '@/api/alerts'
import SecretField from '@/components/SecretField.vue'
import { useKeyboardReturn } from '@/dialog'

/**
 * The mail server that email destinations send through: its name, how the connection is made, the
 * port, the user name and password it needs (if any) and the address the emails come from. The
 * password is a secret that only goes in, so it starts empty and leaving it empty keeps the one
 * saved. It only asks; saving the answer is up to the page, which hands back what was wrong with
 * each field.
 */
const props = defineProps<{
  /** The settings as they are now. */
  server: MailServer
  /** The answer is being saved. */
  busy?: boolean
  /** What was wrong with each field the last time it was saved, by field: `host`, `port`,
   * `security`, `username`, `sender` and `password`. */
  problems?: Record<string, string>
  /** Something that went wrong that is not about a field. */
  failure?: string | null
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [answer: MailServerChange] }>()

const SECURITIES: { value: Security; title: string }[] = [
  { value: 'starttls', title: 'STARTTLS (encrypted after it connects)' },
  { value: 'ssl', title: 'SSL/TLS (encrypted from the start)' },
  { value: 'none', title: 'None (not encrypted, no password)' },
]

const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const host = ref('')
const security = ref<Security>('starttls')
const port = ref('587')
const username = ref('')
const password = ref('')
const forget = ref(false)
const sender = ref('')

const portNumber = computed(() => (/^\d{1,5}$/.test(port.value.trim()) ? Number(port.value) : NaN))
const ready = computed(
  () =>
    host.value.trim() !== '' &&
    sender.value.trim() !== '' &&
    portNumber.value >= 1 &&
    portNumber.value <= 65535,
)

// Each time it opens it shows what is kept now, not what an earlier visit left.
watch(open, (opening) => {
  if (!opening) return
  host.value = props.server.host
  security.value = props.server.security
  port.value = props.server.port.toString()
  username.value = props.server.username ?? ''
  password.value = ''
  forget.value = false
  sender.value = props.server.sender
})

// Choosing another way to connect moves the port to the usual one, unless it was set to something
// else on purpose.
watch(security, (now, before) => {
  if (port.value === props.server.default_ports[before].toString()) {
    port.value = props.server.default_ports[now].toString()
  }
})

function save() {
  if (!ready.value) return
  const answer: MailServerChange = {
    host: host.value.trim(),
    port: portNumber.value,
    security: security.value,
    username: username.value.trim() || null,
    sender: sender.value.trim(),
  }
  if (forget.value) answer.clear_password = true
  else if (password.value) answer.password = password.value
  emit('save', answer)
}
</script>

<template>
  <v-dialog
    v-model="open"
    :persistent="busy"
    max-width="560"
    scrollable
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="pa-6" data-test="mail-dialog">
      <h2 :id="titleId" class="text-title-large mb-1" data-test="mail-dialog-title">
        {{ server.configured ? 'Change the mail server' : 'Set up the mail server' }}
      </h2>
      <p class="text-body-medium text-medium-emphasis mb-4">
        Email destinations send through this server, such as your email provider's or one on your
        network. Use an app password if your provider offers one. AresGate keeps the password
        encrypted and never shows it again.
      </p>
      <v-form @submit.prevent="save">
        <v-text-field
          v-model="host"
          label="Server name"
          placeholder="smtp.example.com"
          maxlength="253"
          autocomplete="off"
          spellcheck="false"
          :error-messages="problems?.host"
          class="mb-4"
          data-test="mail-host"
        />
        <v-select
          v-model="security"
          :items="SECURITIES"
          label="Connection"
          hint="STARTTLS on port 587 is the usual choice."
          persistent-hint
          :error-messages="problems?.security"
          class="mb-4"
          data-test="mail-security"
        />
        <v-text-field
          v-model="port"
          label="Port"
          inputmode="numeric"
          autocomplete="off"
          :error-messages="problems?.port"
          class="mb-4"
          data-test="mail-port"
        />
        <v-text-field
          v-model="username"
          label="User name"
          hint="Leave it empty if the server needs none."
          persistent-hint
          maxlength="254"
          autocomplete="off"
          spellcheck="false"
          :error-messages="problems?.username"
          class="mb-4"
          data-test="mail-username"
        />
        <SecretField
          v-model="password"
          label="Password"
          :saved="server.password_kept && !forget"
          :error-messages="problems?.password"
          class="mb-2"
          data-test="mail-password"
        />
        <v-checkbox
          v-if="server.password_kept"
          v-model="forget"
          label="Forget the saved password"
          hide-details
          density="compact"
          class="mb-2"
          data-test="mail-forget"
        />
        <v-text-field
          v-model="sender"
          label="Send from"
          placeholder="alerts@example.com"
          hint="The address the emails come from."
          persistent-hint
          maxlength="254"
          autocomplete="off"
          spellcheck="false"
          :error-messages="problems?.sender"
          class="mb-4"
          data-test="mail-sender"
        />
        <v-alert
          v-if="failure"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-4"
          data-test="mail-failure"
        >
          {{ failure }}
        </v-alert>
        <div class="d-flex flex-wrap justify-end ga-3">
          <v-btn variant="text" :disabled="busy" data-test="mail-cancel" @click="open = false">
            Cancel
          </v-btn>
          <v-btn
            type="submit"
            color="primary"
            :loading="busy"
            :disabled="!ready"
            data-test="mail-save"
          >
            Save
          </v-btn>
        </div>
      </v-form>
    </v-card>
  </v-dialog>
</template>
