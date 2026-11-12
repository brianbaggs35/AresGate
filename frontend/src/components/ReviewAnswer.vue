<script setup lang="ts">
import { Check, MessageSquarePlus, Undo2, X } from '@lucide/vue'
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import type { Classification, ReviewState } from '@/api/incidents'
import { answerDecision, type Answer, type Decision, type DecisionSubject } from '@/api/review'
import { useSessionStore } from '@/stores/session'

/**
 * The owner's answer to one decision of the AI: agree or disagree, with a reason if they want to
 * give one, which the AI is told the next time it decides. An answered decision shows what was
 * said and can be taken back. A kind that was set aside has one more choice: to keep it that way
 * (or in front of them) whatever the AI says next.
 */
const MAX_REASON = 300

const props = defineProps<{
  subject: DecisionSubject
  id: number
  kind: Classification
  review: ReviewState
  /** What the owner said of it, if they gave a reason. */
  said?: string | null
}>()
const emit = defineEmits<{ answered: [Decision] }>()

const session = useSessionStore()

const reason = ref('')
const reasoning = ref(false)
const keep = ref(false)
const sending = ref<Answer | null>(null)
const failure = ref<string | null>(null)

const answered = computed(() => props.review === 'agreed' || props.review === 'disagreed')
/** Only a kind of incident that was set aside can be kept so: a single incident is just one. */
const keepable = computed(
  () => props.subject === 'family' && (props.kind === 'noise' || props.kind === 'probe'),
)

async function send(answer: Answer) {
  sending.value = answer
  failure.value = null
  try {
    const result = await session.change((token) =>
      answerDecision(
        props.subject,
        props.id,
        answer,
        answer === 'undo' ? null : reason.value.trim() || null,
        answer !== 'undo' && keepable.value && keep.value,
        token,
      ),
    )
    reason.value = ''
    reasoning.value = false
    keep.value = false
    emit('answered', result)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    sending.value = null
  }
}
</script>

<template>
  <div class="answer" data-test="review-answer">
    <template v-if="answered">
      <p class="answer__said text-body-large" data-test="review-said">
        <v-icon
          :icon="review === 'agreed' ? Check : X"
          :color="review === 'agreed' ? 'success' : 'error'"
          size="20"
          aria-hidden="true"
        />
        <span>
          <b>{{ review === 'agreed' ? 'You agreed.' : 'You disagreed.' }}</b>
          <template v-if="said"> “{{ said }}”</template>
        </span>
      </p>
      <v-btn
        variant="text"
        size="small"
        :prepend-icon="Undo2"
        :loading="sending === 'undo'"
        :disabled="sending !== null"
        data-test="review-undo"
        @click="send('undo')"
      >
        Take it back
      </v-btn>
    </template>

    <template v-else>
      <v-textarea
        v-if="reasoning"
        v-model="reason"
        label="Why? (optional)"
        :counter="MAX_REASON"
        :maxlength="MAX_REASON"
        rows="2"
        auto-grow
        hide-details="auto"
        variant="outlined"
        density="comfortable"
        hint="The AI is told what you disagreed with, and why, the next time it decides."
        persistent-hint
        data-test="review-reason"
      />
      <v-checkbox
        v-if="keepable"
        v-model="keep"
        density="compact"
        hide-details
        color="primary"
        label="Remember this for every incident of this kind, whatever the AI says next"
        data-test="review-keep"
      />
      <div class="answer__buttons">
        <v-btn
          color="success"
          variant="tonal"
          :prepend-icon="Check"
          :loading="sending === 'agree'"
          :disabled="sending !== null"
          data-test="review-agree"
          @click="send('agree')"
        >
          Agree
        </v-btn>
        <v-btn
          color="error"
          variant="tonal"
          :prepend-icon="X"
          :loading="sending === 'disagree'"
          :disabled="sending !== null"
          data-test="review-disagree"
          @click="send('disagree')"
        >
          Disagree
        </v-btn>
        <v-btn
          v-if="!reasoning"
          variant="text"
          :prepend-icon="MessageSquarePlus"
          data-test="review-add-reason"
          @click="reasoning = true"
        >
          Add a reason
        </v-btn>
      </div>
    </template>

    <v-alert v-if="failure" type="error" variant="tonal" role="alert" data-test="review-failure">
      {{ failure }}
    </v-alert>
  </div>
</template>

<style scoped>
.answer {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  align-self: stretch;
}

.answer__said {
  display: flex;
  gap: 0.5rem;
  margin: 0;
}

.answer__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}
</style>
