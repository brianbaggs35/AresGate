<script setup lang="ts">
import { ExternalLink, X } from '@lucide/vue'
import { computed, ref, useId } from 'vue'
import { useDisplay } from 'vuetify'

import type { Cve } from '@/api/threatCatalog'
import SeverityChip from '@/components/SeverityChip.vue'
import { useKeyboardReturn } from '@/dialog'
import { formatDate, formatDateTime } from '@/format'

/**
 * What NVD says of one CVE, in a window over the page: how severe it is and what the score is made
 * of, what it is, the weaknesses behind it, and whether CISA lists it as exploited in the wild,
 * with what it asks to be done about it and by when. A CVE NVD has no record of says so. A link
 * to NVD's own page, and the notice NVD asks a service that shows its data to carry. The whole
 * screen on a phone.
 */
const props = defineProps<{ cve: Cve; notice: string }>()
const open = defineModel<boolean>({ required: true })

const { xs: phone } = useDisplay()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)
const title = ref<HTMLElement | null>(null)

/** Moves the keyboard to the title, so a screen reader starts at the top of what opened. */
function takeTheKeyboard() {
  title.value?.focus({ preventScroll: true })
}

const facts = computed(() => {
  const { cve } = props
  return [
    ['Status', cve.status],
    ['Published', cve.published_at ? formatDateTime(cve.published_at) : null],
    ['Last changed', cve.modified_at ? formatDateTime(cve.modified_at) : null],
    ['Vector', cve.vector],
  ].filter((fact): fact is [string, string] => fact[1] !== null)
})
</script>

<template>
  <v-dialog
    v-model="open"
    :fullscreen="phone"
    scrollable
    max-width="680"
    :aria-labelledby="titleId"
    @after-enter="takeTheKeyboard"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card
      :class="{ 'dialog--screen': phone }"
      :rounded="phone ? 0 : undefined"
      :border="!phone"
      data-test="cve-dialog"
    >
      <header class="head">
        <div class="head__text">
          <p class="text-label-large text-medium-emphasis">NVD · Vulnerability</p>
          <h2 :id="titleId" ref="title" tabindex="-1" class="head__title text-title-large">
            {{ cve.cve_id }}
          </h2>
        </div>
        <v-btn icon variant="text" aria-label="Close" data-test="cve-close" @click="open = false">
          <X :size="20" aria-hidden="true" />
        </v-btn>
      </header>

      <v-card-text class="body">
        <p v-if="cve.state === 'unknown'" class="text-body-large" data-test="cve-unknown">
          NVD has no record of this CVE yet. A CVE published a moment ago can take a while to reach
          it. AresGate asks again later.
        </p>

        <template v-else>
          <div class="verdict">
            <SeverityChip v-if="cve.rating !== 'unrated'" :severity="cve.rating" />
            <v-chip v-else variant="tonal" data-test="cve-unrated">Not scored yet</v-chip>
            <span v-if="cve.score !== null" class="text-title-medium" data-test="cve-score">
              {{ cve.score.toFixed(1) }}
              <span class="text-body-small text-medium-emphasis">
                CVSS {{ cve.cvss_version }}
              </span>
            </span>
            <v-chip
              v-if="cve.exploited"
              color="error"
              variant="flat"
              size="small"
              data-test="cve-exploited"
            >
              Exploited in the wild
            </v-chip>
          </div>

          <p v-if="cve.description" class="text-body-large" data-test="cve-description">
            {{ cve.description }}
          </p>

          <v-alert
            v-if="cve.exploited"
            type="error"
            variant="tonal"
            density="comfortable"
            data-test="cve-kev"
          >
            <p v-if="cve.kev_name" class="kev__name">{{ cve.kev_name }}</p>
            <p>
              CISA lists it in its Known Exploited Vulnerabilities catalog<template
                v-if="cve.exploited_on"
              >
                since {{ formatDate(cve.exploited_on) }}</template
              >, which means someone has been seen using it against real systems.
            </p>
            <p v-if="cve.required_action" data-test="cve-action">
              {{ cve.required_action }}
              <template v-if="cve.action_due"> Due {{ formatDate(cve.action_due) }}.</template>
            </p>
          </v-alert>

          <dl v-if="facts.length" class="facts" data-test="cve-facts">
            <template v-for="[label, value] in facts" :key="label">
              <dt class="text-label-large text-medium-emphasis">{{ label }}</dt>
              <dd class="text-body-medium">{{ value }}</dd>
            </template>
          </dl>

          <div v-if="cve.weaknesses.length" data-test="cve-weaknesses">
            <p class="text-label-large text-medium-emphasis">Weaknesses behind it</p>
            <div class="weaknesses">
              <v-chip v-for="weakness in cve.weaknesses" :key="weakness" size="small" label>
                {{ weakness }}
              </v-chip>
            </div>
          </div>
        </template>

        <p class="text-body-small text-medium-emphasis" data-test="cve-checked">
          AresGate asked NVD {{ formatDateTime(cve.checked_at) }}.
        </p>
        <p class="text-body-small text-medium-emphasis" data-test="cve-notice">{{ notice }}</p>
      </v-card-text>

      <v-card-actions class="foot">
        <v-btn
          :href="cve.link"
          target="_blank"
          rel="noopener noreferrer"
          variant="text"
          :append-icon="ExternalLink"
          data-test="cve-link"
        >
          View on NVD
        </v-btn>
        <v-spacer />
        <v-btn variant="tonal" data-test="cve-done" @click="open = false">Done</v-btn>
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

.verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.kev__name {
  font-weight: 600;
}

.facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.25rem 1rem;
  margin: 0;
}

.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.weaknesses {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.foot {
  padding: 0.75rem 1rem;
}
</style>
