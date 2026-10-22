<script setup lang="ts">
import { CircleAlert, CircleCheck } from '@lucide/vue'

import type { AuditEvent } from '@/api/audit'
import { describeBrowser, formatDateTime } from '@/format'

defineProps<{ events: readonly AuditEvent[] }>()

/** What each kind of event is called. One without a name here shows as it is. */
const TITLES: Readonly<Record<string, string>> = {
  'setup.completed': 'AresGate was set up',
  'setup.code_rejected': 'Wrong setup code',
  'auth.login_succeeded': 'Signed in',
  'auth.login_failed': 'Sign-in failed',
  'auth.logout': 'Signed out',
  'auth.two_factor_enabled': 'Two-step verification was turned on',
  'auth.two_factor_disabled': 'Two-step verification was turned off',
  'auth.two_factor_failed': 'Wrong verification code',
  'auth.recovery_codes_created': 'New recovery codes were made',
  'audit.events_purged': 'Old activity was removed',
}

const title = (event: AuditEvent) => TITLES[event.action] ?? event.action
</script>

<template>
  <ul class="activity-list" data-test="activity-list">
    <li v-for="event in events" :key="event.id" class="activity-list__item" data-test="activity">
      <v-icon
        :icon="event.outcome === 'success' ? CircleCheck : CircleAlert"
        :color="event.outcome === 'success' ? 'success' : 'warning'"
        :aria-label="event.outcome === 'success' ? 'Succeeded' : 'Failed'"
        role="img"
        :aria-hidden="false"
      />
      <div class="activity-list__text">
        <div class="text-body-large" data-test="activity-title">
          {{ title(event) }}<template v-if="event.username"> · {{ event.username }}</template>
        </div>
        <div class="text-body-medium text-medium-emphasis" data-test="activity-detail">
          {{ formatDateTime(event.occurred_at) }} · {{ describeBrowser(event.user_agent) }}
          <template v-if="event.client_address"> · {{ event.client_address }}</template>
        </div>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.activity-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.activity-list__item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.activity-list__item + .activity-list__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.activity-list__text {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
