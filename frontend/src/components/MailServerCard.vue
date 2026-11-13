<script setup lang="ts">
import { Pencil, Server, Trash2 } from '@lucide/vue'
import { computed } from 'vue'

import type { MailServer, Security } from '@/api/alerts'

/**
 * The mail server email destinations send through: what it is, how the connection is made and
 * from which address the emails come, or that none is set up yet. The password is never shown,
 * only whether one is kept. It only asks; what the buttons do is up to the page.
 */
const props = defineProps<{
  server: MailServer
  /** The server is being changed or removed, so its buttons wait. */
  busy?: boolean
}>()
const emit = defineEmits<{ edit: []; remove: [] }>()

const WAYS: Readonly<Record<Security, string>> = {
  starttls: 'STARTTLS',
  ssl: 'SSL/TLS',
  none: 'not encrypted',
}

const way = computed(() => WAYS[props.server.security])
const signIn = computed(() => {
  const { username, password_kept: kept } = props.server
  if (!username) return 'It signs in with no user name.'
  const without = kept ? '' : ', with no password'
  return `It signs in as ${username}${without}.`
})
</script>

<template>
  <div class="mail" data-test="mail-server">
    <template v-if="server.configured">
      <div class="mail__head">
        <v-icon :icon="Server" size="22" class="mail__icon" aria-hidden="true" />
        <h3 class="text-title-medium mail__name" data-test="mail-name">
          {{ server.host }}:{{ server.port }}
        </h3>
        <v-chip size="small" variant="outlined" data-test="mail-way">{{ way }}</v-chip>
      </div>
      <p class="text-body-medium" data-test="mail-details">
        Emails come from {{ server.sender }}. {{ signIn }}
      </p>
      <p
        v-if="server.password_kept"
        class="text-body-medium text-medium-emphasis"
        data-test="mail-password-kept"
      >
        The password is saved, encrypted. It is never shown again.
      </p>
    </template>
    <p v-else class="text-body-medium" data-test="mail-none">
      No mail server is set up. Enter your email provider's settings, or those of a mail server on
      your network, and email destinations can send through it.
    </p>
    <div class="mail__actions">
      <v-btn
        variant="tonal"
        color="primary"
        :prepend-icon="server.configured ? Pencil : Server"
        :disabled="busy"
        data-test="mail-edit"
        @click="emit('edit')"
      >
        {{ server.configured ? 'Change the mail server' : 'Set up the mail server' }}
      </v-btn>
      <v-btn
        v-if="server.configured"
        variant="text"
        color="error"
        :prepend-icon="Trash2"
        :disabled="busy"
        data-test="mail-remove"
        @click="emit('remove')"
      >
        Remove
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.mail {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.mail p {
  margin: 0;
  overflow-wrap: anywhere;
}

.mail__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.mail__icon {
  color: rgb(var(--v-theme-primary));
}

.mail__name {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.mail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.5rem;
}
</style>
