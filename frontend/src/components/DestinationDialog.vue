<script setup lang="ts">
import { ExternalLink } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'

import type { Destination } from '@/api/alerts'
import SecretField from '@/components/SecretField.vue'
import { useKeyboardReturn } from '@/dialog'

/**
 * Adds a Discord destination, or changes one: its name and its webhook address. The address is a
 * secret that only goes in, so changing a destination leaves it empty to keep the one saved. It
 * only asks; saving the answer is up to the page, which hands back what was wrong with each field.
 */
const props = defineProps<{
  /** The destination being changed, or none for a new one. It keeps showing as the dialog fades. */
  destination: Destination | null
  /** The answer is being saved. */
  busy?: boolean
  /** What was wrong with each field the last time it was saved, by field: `name` and `url`. */
  problems?: Record<string, string>
  /** Something that went wrong that is not about a field. */
  failure?: string | null
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [answer: { name: string; url: string }] }>()

const titleId = useId()
const nameId = useId()
const urlId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const name = ref('')
const url = ref('')

const changing = computed(() => props.destination !== null)
// Adding needs both; changing keeps the address when it is left empty.
const ready = computed(
  () => name.value.trim() !== '' && (changing.value || url.value.trim() !== ''),
)

// Each time it opens it shows what is kept now, not what an earlier visit left.
watch(open, (opening) => {
  if (!opening) return
  name.value = props.destination?.name ?? ''
  url.value = ''
})

function save() {
  if (ready.value) emit('save', { name: name.value.trim(), url: url.value.trim() })
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
    <v-card class="pa-6" data-test="destination-dialog">
      <h2 :id="titleId" class="text-title-large mb-1" data-test="dialog-title">
        {{ changing ? 'Change this destination' : 'Add a Discord destination' }}
      </h2>
      <p class="text-body-medium text-medium-emphasis mb-4">
        AresGate posts a message to one channel of your Discord server through a webhook. It never
        sends anything to Discord except the alerts you ask for.
      </p>
      <v-form @submit.prevent="save">
        <v-text-field
          :id="nameId"
          v-model="name"
          label="Name"
          placeholder="Security channel"
          hint="What you call it here."
          persistent-hint
          maxlength="60"
          autocomplete="off"
          :error-messages="problems?.name"
          class="mb-4"
          data-test="dialog-name"
        />
        <SecretField
          :id="urlId"
          v-model="url"
          label="Webhook address"
          :saved="changing"
          hint="Starts with https://discord.com/api/webhooks/"
          :error-messages="problems?.url"
          class="mb-2"
          data-test="dialog-url"
        />
        <p class="text-body-medium text-medium-emphasis mb-4" data-test="dialog-help">
          In Discord, open your server's Integrations settings, choose Webhooks, make a webhook for
          the channel you want and copy its URL (see Discord's
          <a
            href="https://support.discord.com/hc/en-us/articles/360045093012"
            target="_blank"
            rel="noopener noreferrer"
            >help page<ExternalLink :size="14" aria-hidden="true" /></a
          >). Anyone who has the address can post to that channel, so AresGate keeps it encrypted
          and never shows it again.
        </p>
        <v-alert
          v-if="failure"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-4"
          data-test="dialog-failure"
        >
          {{ failure }}
        </v-alert>
        <div class="d-flex flex-wrap justify-end ga-3">
          <v-btn variant="text" :disabled="busy" data-test="dialog-cancel" @click="open = false">
            Cancel
          </v-btn>
          <v-btn
            type="submit"
            color="primary"
            :loading="busy"
            :disabled="!ready"
            data-test="dialog-save"
          >
            {{ changing ? 'Save' : 'Add destination' }}
          </v-btn>
        </div>
      </v-form>
    </v-card>
  </v-dialog>
</template>
