<script setup lang="ts">
import { Gavel } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  ruleOnThreat,
  takeBackRuling,
  type Ruled,
  type Ruling,
  type Verdict,
} from '@/api/threatIntel'
import { formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'
import { RULING } from '@/threatIntel'

/**
 * Where the owner says what they make of a subject, whatever the services made of it: safe, to
 * correct a false positive, or suspicious, to correct a false negative. The choice is two large
 * cards, which are radio buttons underneath, so the keyboard and a screen reader work as they do
 * for any other group. A reason may be written, which is kept with the ruling and shown to whoever
 * reads it later. Saving, or taking it back, says nothing to any service: it is only the owner's
 * word, and the pages and the AI go by it from then on. `changed` says what was ruled, or null
 * where the ruling was taken back.
 */
const props = defineProps<{
  /** What is ruled on: an address, a domain or a web address, as it was searched for. */
  subject: string
  /** What the owner has ruled of it already, if anything. */
  ruling: Ruled | null
}>()
const emit = defineEmits<{ changed: [ruling: Ruling | null] }>()

const session = useSessionStore()
const groupId = useId()
const choice = ref<Verdict | null>(props.ruling?.verdict ?? null)
const note = ref(props.ruling?.note ?? '')
const busy = ref(false)
const problem = ref<string | null>(null)

const MAX_NOTE = 500
const choices: Verdict[] = ['safe', 'suspicious']

/** What was said already, again, whenever the ruling shown is a different one. */
watch(
  () => props.ruling,
  (found) => {
    choice.value = found?.verdict ?? null
    note.value = found?.note ?? ''
  },
)

const unchanged = computed(
  () =>
    props.ruling !== null &&
    choice.value === props.ruling.verdict &&
    note.value.trim() === (props.ruling.note ?? ''),
)

const lead = computed(() => {
  const found = props.ruling
  if (!found) {
    return 'Services can be wrong either way. Say what you know and AresGate will go by it, on every page and in what the AI is told.'
  }
  const when = found.set_at ? `, ${formatDateTime(found.set_at)}` : ''
  return `${RULING[found.verdict].label}${when}. It stands over what the services say until you take it back.`
})

async function save() {
  const verdict = choice.value
  if (!verdict || busy.value) return
  busy.value = true
  problem.value = null
  try {
    const trimmed = note.value.trim()
    const ruled = await session.change((token) =>
      ruleOnThreat(props.subject, verdict, trimmed === '' ? null : trimmed, token),
    )
    emit('changed', ruled)
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

async function takeBack() {
  if (busy.value) return
  busy.value = true
  problem.value = null
  try {
    await session.change((token) => takeBackRuling(props.subject, token))
    choice.value = null
    note.value = ''
    emit('changed', null)
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="ruling" :aria-labelledby="`${groupId}-title`" data-test="ruling">
    <h3 :id="`${groupId}-title`" class="ruling__title text-title-small">
      <Gavel :size="18" aria-hidden="true" />
      Your ruling
    </h3>
    <p class="text-body-medium text-medium-emphasis ruling__lead" data-test="ruling-lead">
      {{ lead }}
    </p>

    <fieldset class="ruling__choices" data-test="ruling-choices">
      <legend class="ruling__legend">What do you make of it?</legend>
      <label
        v-for="verdict in choices"
        :key="verdict"
        class="choice"
        :class="[`choice--${verdict}`, { 'choice--on': choice === verdict }]"
        :data-test="`ruling-choice-${verdict}`"
      >
        <input
          v-model="choice"
          type="radio"
          class="choice__input"
          :name="`${groupId}-verdict`"
          :value="verdict"
        />
        <span class="choice__icon" aria-hidden="true">
          <component :is="RULING[verdict].icon" :size="22" />
        </span>
        <span class="choice__text">
          <span class="text-title-small">{{ RULING[verdict].short }}</span>
          <span class="text-body-small text-medium-emphasis">{{ RULING[verdict].effect }}</span>
        </span>
      </label>
    </fieldset>

    <v-textarea
      v-model="note"
      label="Why? (optional)"
      placeholder="For whoever reads this later"
      :counter="MAX_NOTE"
      :maxlength="MAX_NOTE"
      rows="2"
      auto-grow
      density="comfortable"
      data-test="ruling-note"
    />

    <v-alert
      v-if="problem"
      type="error"
      variant="tonal"
      density="compact"
      data-test="ruling-problem"
    >
      {{ problem }}
    </v-alert>

    <div class="ruling__actions">
      <v-btn
        color="primary"
        :loading="busy"
        :disabled="!choice || unchanged"
        data-test="ruling-save"
        @click="save"
      >
        {{ ruling ? 'Change my ruling' : 'Save my ruling' }}
      </v-btn>
      <v-btn
        v-if="ruling"
        variant="text"
        :disabled="busy"
        data-test="ruling-take-back"
        @click="takeBack"
      >
        Take it back
      </v-btn>
    </div>
  </section>
</template>

<style scoped>
.ruling {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.ruling__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
}

.ruling__lead {
  margin: 0;
}

.ruling__choices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

/* Read out as the name of the group, and not shown. */
.ruling__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

.choice {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border: 2px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 14px;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    transform 160ms ease;
}

.choice:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.choice__input {
  position: absolute;
  inset: 0;
  opacity: 0;
  margin: 0;
  cursor: pointer;
}

.choice:has(.choice__input:focus-visible) {
  outline: 3px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.choice__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.choice__text {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.choice--on {
  transform: translateY(-1px);
}

.choice--safe.choice--on {
  border-color: rgb(var(--v-theme-success));
  background: rgba(var(--v-theme-success), 0.1);
}

.choice--safe.choice--on .choice__icon {
  background: rgba(var(--v-theme-success), 0.25);
}

.choice--suspicious.choice--on {
  border-color: rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.1);
}

.choice--suspicious.choice--on .choice__icon {
  background: rgba(var(--v-theme-warning), 0.25);
}

.ruling__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

@media (prefers-reduced-motion: reduce) {
  .choice {
    transition: none;
  }

  .choice--on {
    transform: none;
  }
}
</style>
