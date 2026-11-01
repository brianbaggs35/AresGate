<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { saveLevel, type UsageLevel } from '@/api/aiUsage'
import { errorMessage } from '@/api/client'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * How much AI is used without being asked: a slider from Very low to Maximum. It decides how much
 * the worker reads by itself (which incidents, and how many an hour), and never what the owner
 * asks for. What each stop does is worded by the server from what the worker really does, so the
 * words here can't promise anything else.
 */
const props = defineProps<{ level: UsageLevel['key']; levels: readonly UsageLevel[] }>()
const emit = defineEmits<{ changed: [level: UsageLevel['key']] }>()

const session = useSessionStore()

// Where the slider is: the index of a level, which is not yet kept until it is saved.
const position = ref(0)
const busy = ref(false)
const failure = ref<string | null>(null)
const saved = ref(false)

const kept = computed(() => props.levels.findIndex(({ key }) => key === props.level))
const picked = computed(() => props.levels[position.value] as UsageLevel)
const changed = computed(() => position.value !== kept.value)
const rate = computed(() =>
  picked.value.per_hour === 0 ? 'Nothing by itself' : `Up to ${picked.value.per_hour} an hour`,
)

// The slider starts where the level is kept, and follows it when the page asks again.
watch(
  kept,
  (index) => {
    position.value = index
  },
  { immediate: true },
)

// A note that it was saved is about what was saved: moving the slider again withdraws it.
watch(position, () => {
  saved.value = false
})

// What a screen reader says of the slider's place: the level, not its number.
const spoken = ({ value }: { value: number }) => (props.levels[value] as UsageLevel).label

async function save() {
  busy.value = true
  failure.value = null
  saved.value = false
  const wanted = picked.value.key
  try {
    await session.change((token) => saveLevel(wanted, token))
    saved.value = true
    emit('changed', wanted)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <SectionCard
    title="How much AI is used"
    description="How much AresGate reads by itself, without being asked. It never changes what you ask for: Start investigating on an incident and your questions in the Assistant are answered at every level. Spending limits hold at every level too."
    data-test="level-card"
  >
    <div class="level__head">
      <span class="text-title-medium" data-test="level-name">{{ picked.label }}</span>
      <span class="text-body-medium text-medium-emphasis" data-test="level-rate">{{ rate }}</span>
    </div>
    <v-slider
      v-model="position"
      :min="0"
      :max="levels.length - 1"
      :step="1"
      show-ticks="always"
      :tick-size="4"
      color="primary"
      hide-details
      name="How much AI is used without being asked"
      :value-format="spoken"
      :disabled="busy"
      class="level__slider"
      data-test="level-slider"
    />
    <div class="level__ends text-label-medium text-medium-emphasis" aria-hidden="true">
      <span>Only when asked</span>
      <span>As much as it can</span>
    </div>
    <output class="level__summary d-block text-body-large" data-test="level-summary">
      {{ picked.summary }}
    </output>

    <div class="level__actions">
      <v-btn
        color="primary"
        :disabled="!changed"
        :loading="busy"
        data-test="level-save"
        @click="save"
      >
        Save
      </v-btn>
      <output v-if="saved" class="text-body-medium" data-test="level-saved"> Saved. </output>
    </div>
    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      class="mt-4"
      role="alert"
      data-test="level-failure"
    >
      {{ failure }}
    </v-alert>
  </SectionCard>
</template>

<style scoped>
.level__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.level__slider {
  margin-block: 0.75rem 0;
}

.level__ends {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.level__summary {
  margin-block: 1rem;
}

.level__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}
</style>
