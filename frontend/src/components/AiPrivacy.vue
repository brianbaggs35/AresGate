<script setup lang="ts">
import { Check } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import type { AiProvider, Redaction } from '@/api/ai'
import { mayShowEverything, REDACTION_LEVELS, shownLevel } from '@/ai'

/**
 * How much of the network the AI provider is shown, as three cards that each show what a provider
 * would read of the same event, so the choice doesn't need explaining. They are radio buttons
 * underneath. Local is for a provider on the owner's own network and can't be chosen for any
 * other; if it was chosen and the provider changed since, the note says what is really shown.
 */
const props = defineProps<{
  level: Redaction
  /** The provider AresGate asks, if one is chosen. */
  asking: AiProvider | undefined
  busy: boolean
  /** Why the last change was refused, if it was. */
  failure: string | null
}>()
const emit = defineEmits<{ change: [level: Redaction] }>()

const allowed = computed(() => mayShowEverything(props.asking))
const really = computed(() => shownLevel(props.level, props.asking))

function choose(key: Redaction) {
  if (key !== props.level) emit('change', key)
}

// A radio button that was pressed stays pressed when the change is refused and the level is the
// same as before, which Vue sees no reason to draw again: once the change is over, it is put back.
const group = ref<HTMLElement | null>(null)
watch(
  () => props.busy,
  (busy) => {
    if (busy) return
    for (const input of group.value?.querySelectorAll('input') ?? []) {
      input.checked = input.value === props.level
    }
  },
)
</script>

<template>
  <fieldset ref="group" class="privacy" data-test="ai-privacy">
    <legend class="privacy__legend text-title-medium">What may the provider see?</legend>
    <div class="privacy__grid">
      <label
        v-for="item in REDACTION_LEVELS"
        :key="item.key"
        class="privacy__option"
        :class="{
          'privacy__option--chosen': level === item.key,
          'privacy__option--disabled': item.key === 'local' && !allowed,
        }"
        :data-test="`privacy-${item.key}`"
      >
        <input
          type="radio"
          name="ai-redaction"
          class="privacy__input"
          :value="item.key"
          :checked="level === item.key"
          :disabled="busy || (item.key === 'local' && !allowed)"
          @change="choose(item.key)"
        />
        <span class="privacy__mark" aria-hidden="true">
          <Check v-if="level === item.key" :size="16" :stroke-width="3" />
        </span>
        <span class="privacy__text">
          <span class="text-title-medium">{{ item.label }}</span>
          <span class="text-body-medium text-medium-emphasis">{{ item.summary }}</span>
          <code
            class="privacy__example text-body-medium"
            :data-test="`privacy-example-${item.key}`"
          >
            {{ item.example }}
          </code>
        </span>
      </label>
    </div>
    <p
      v-if="level === 'local' && really !== 'local' && asking"
      class="text-body-medium text-medium-emphasis"
      data-test="privacy-note"
    >
      {{ asking.label }} is not on your own network, so it is shown Balanced. Local only applies to
      a provider that runs at home.
    </p>
    <p v-else-if="!allowed" class="text-body-medium text-medium-emphasis" data-test="privacy-note">
      Local is for a provider on your own network, such as an Ollama at home. {{ asking?.label }}
      is hosted.
    </p>
    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="compact"
      data-test="privacy-failure"
    >
      {{ failure }}
    </v-alert>
  </fieldset>
</template>

<style scoped>
.privacy {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.privacy p {
  margin: 0;
}

.privacy__legend {
  padding: 0;
  margin-bottom: 0.25rem;
}

.privacy__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem;
}

.privacy__option {
  position: relative;
  display: grid;
  grid-template-columns: 1.5rem minmax(0, 1fr);
  align-items: start;
  gap: 0 0.875rem;
  padding: 1rem;
  border: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  cursor: pointer;
  transition:
    border-color 120ms,
    background-color 120ms;
}

.privacy__option:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.privacy__option--chosen {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.privacy__option--disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* The real radio button covers the card, so a click anywhere chooses it and it can be focused. */
.privacy__input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: inherit;
}

.privacy__option:has(.privacy__input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.privacy__mark {
  display: grid;
  place-items: center;
  width: 1.5rem;
  height: 1.5rem;
  margin-top: 0.1rem;
  border: 2px solid rgba(var(--v-theme-on-surface), 0.6);
  border-radius: 50%;
  color: rgb(var(--v-theme-on-primary));
}

.privacy__option--chosen .privacy__mark {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary));
}

.privacy__text {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}

.privacy__example {
  display: block;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}

@media (min-width: 960px) {
  .privacy__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
