<script setup lang="ts">
import { Info } from '@lucide/vue'
import { computed } from 'vue'

import type { Incident } from '@/api/incidents'
import FactList from '@/components/FactList.vue'
import { formatDateTime } from '@/format'
import { RESPONSE, banEnds, banReason, banStatus, headline, stepsOf, turnedAway } from '@/response'

/**
 * What was done about an incident: how it stands in a sentence, the bans CrowdSec made and how
 * long each lasts, what else turned the address away, what happened in order, and what AresGate
 * can't tell. All of it is read from what the programs reported, so it says "seen" and not
 * "done", and where a program is not connected it says that nothing can be seen of it.
 */
const props = defineProps<{
  incident: Incident
  /** The moment to count from, for the time left of a ban. */
  now?: number
}>()

const moment = computed(() => props.now ?? Date.now())
const done = computed(() => props.incident.response)
const look = computed(() => RESPONSE[done.value.state])
const sentence = computed(() => headline(props.incident, moment.value))
const steps = computed(() => stepsOf(props.incident, moment.value))
const facts = computed(() => turnedAway(done.value, moment.value))
</script>

<template>
  <div class="response" :data-state="done.state" data-test="response">
    <div class="response__lead">
      <span class="response__badge" :style="{ '--tone': `var(--v-theme-${look.color})` }">
        <v-icon :icon="look.icon" size="28" aria-hidden="true" />
      </span>
      <div>
        <p class="response__state text-title-large" data-test="response-state">
          {{ done.label }}
        </p>
        <p class="text-body-large" data-test="response-headline">{{ sentence }}</p>
      </div>
    </div>

    <section v-if="done.bans.length" class="response__section" data-test="response-bans">
      <h3 class="text-title-medium">What CrowdSec decided</h3>
      <ul class="response__bans">
        <li
          v-for="(ban, index) in done.bans"
          :key="index"
          class="response__ban"
          data-test="response-ban"
        >
          <div class="response__head">
            <span class="response__mono text-title-medium" data-test="response-ban-address">{{
              ban.address
            }}</span>
            <v-chip
              size="small"
              :variant="ban.in_force ? 'tonal' : 'outlined'"
              :color="ban.in_force ? 'success' : undefined"
              data-test="response-ban-status"
            >
              {{ banStatus(ban) }}
            </v-chip>
          </div>
          <p v-if="banReason(ban)" class="text-body-medium" data-test="response-ban-reason">
            {{ banReason(ban) }}
          </p>
          <p class="text-body-medium text-medium-emphasis">
            Read by AresGate
            <time :datetime="ban.seen_at">{{ formatDateTime(ban.seen_at) }}</time
            >. <span data-test="response-ban-ends">{{ banEnds(ban, moment) }}</span>
          </p>
        </li>
      </ul>
    </section>

    <section v-if="facts.length" class="response__section" data-test="response-facts">
      <h3 class="text-title-medium">What else turned it away</h3>
      <FactList :facts="facts" />
    </section>

    <section v-if="steps.length > 1" class="response__section" data-test="response-steps">
      <h3 class="text-title-medium">In order</h3>
      <ol class="response__steps">
        <li v-for="step in steps" :key="step.key" class="response__step" data-test="response-step">
          <time :datetime="step.at" class="response__when text-body-medium text-medium-emphasis">{{
            formatDateTime(step.at)
          }}</time>
          <div>
            <p class="text-body-large" data-test="response-step-title">{{ step.title }}</p>
            <p v-if="step.detail" class="text-body-medium text-medium-emphasis">
              {{ step.detail }}
            </p>
          </div>
        </li>
      </ol>
    </section>

    <section v-if="done.unknown.length" class="response__section" data-test="response-unknown">
      <h3 class="text-title-medium">
        <v-icon :icon="Info" size="20" aria-hidden="true" />
        What AresGate can't tell
      </h3>
      <ul class="response__notes text-body-medium text-medium-emphasis">
        <li v-for="note in done.unknown" :key="note" data-test="response-note">{{ note }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.response {
  display: grid;
  gap: 1.25rem;
}

.response__lead {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
}

.response__badge {
  display: grid;
  flex: none;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 999px;
  background: rgba(var(--tone), 0.16);
  color: rgb(var(--tone));
}

.response__lead p {
  margin: 0;
}

.response__state {
  font-weight: 600;
}

.response__section h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.5rem;
}

.response__bans,
.response__steps,
.response__notes {
  margin: 0;
  padding: 0;
  list-style: none;
}

.response__notes {
  display: grid;
  gap: 0.25rem;
}

.response__ban {
  padding: 0.75rem 0;
}

.response__ban + .response__ban {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.response__ban:first-child {
  padding-top: 0;
}

.response__ban p {
  margin: 0.25rem 0 0;
}

.response__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.response__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}

/* A line down the side joins the steps, as in the timeline of signals. */
.response__steps {
  position: relative;
  display: grid;
  gap: 0.75rem;
  padding-inline-start: 1.25rem;
  border-inline-start: 2px solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.response__step {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.125rem;
}

.response__step p {
  margin: 0;
}

@media (min-width: 600px) {
  .response__step {
    grid-template-columns: 12rem minmax(0, 1fr);
    gap: 1rem;
  }
}
</style>
