<script setup lang="ts">
import { X } from '@lucide/vue'
import { ref, useId } from 'vue'
import { useDisplay } from 'vuetify'

import type { Ruled, Ruling } from '@/api/threatIntel'
import ThreatRuling from '@/components/ThreatRuling.vue'
import { useKeyboardReturn } from '@/dialog'

/**
 * A window over the page for ruling on one address, domain or web address: what the services said
 * of it, where there is something to say, and the owner's ruling. It is for the pages that show an
 * address and have no report to open, such as the incident page: the owner sees a service say
 * "clean" of the address that has been scanning them, and can say otherwise on the spot. The whole
 * screen on a phone. `changed` says what was ruled, or null where the ruling was taken back.
 */
defineProps<{
  subject: string
  ruling: Ruled | null
  /** What the services said of it, in a sentence, if they said anything. */
  heard?: string | null
}>()
const emit = defineEmits<{ changed: [ruling: Ruling | null] }>()
const open = defineModel<boolean>({ required: true })

const { xs: phone } = useDisplay()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)
const title = ref<HTMLElement | null>(null)

/** Moves the keyboard to the title, so a screen reader starts at the top of what opened. */
function takeTheKeyboard() {
  title.value?.focus({ preventScroll: true })
}
</script>

<template>
  <v-dialog
    v-model="open"
    :fullscreen="phone"
    scrollable
    max-width="560"
    :aria-labelledby="titleId"
    @after-enter="takeTheKeyboard"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card
      :class="{ 'dialog--screen': phone }"
      :rounded="phone ? 0 : undefined"
      :border="!phone"
      data-test="ruling-dialog"
    >
      <header class="head">
        <div class="head__text">
          <p class="text-label-large text-medium-emphasis">Rule on</p>
          <h2
            :id="titleId"
            ref="title"
            tabindex="-1"
            class="head__title text-title-large"
            data-test="ruling-subject"
          >
            {{ subject }}
          </h2>
        </div>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="ruling-close"
          @click="open = false"
        >
          <X :size="20" aria-hidden="true" />
        </v-btn>
      </header>
      <v-card-text class="body">
        <p v-if="heard" class="text-body-medium text-medium-emphasis" data-test="ruling-heard">
          {{ heard }}
        </p>
        <ThreatRuling :subject="subject" :ruling="ruling" @changed="emit('changed', $event)" />
      </v-card-text>
      <v-card-actions class="foot">
        <v-spacer />
        <v-btn variant="tonal" data-test="ruling-done" @click="open = false">Done</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.dialog--screen {
  height: 100%;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem 1.25rem 0.5rem 1.5rem;
}

.head__text {
  min-width: 0;
}

.head__text p {
  margin: 0;
}

.head__title {
  margin: 0.125rem 0 0;
  overflow-wrap: anywhere;
  outline: none;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-top: 0.5rem;
}

.body p {
  margin: 0;
}

.foot {
  padding: 0.75rem 1rem;
}
</style>
