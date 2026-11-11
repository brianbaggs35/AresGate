<script setup lang="ts">
import { ref, useId, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { trust, type Trust, type TrustLevel } from '@/api/trust'
import TrustForm from '@/components/TrustForm.vue'
import { useKeyboardReturn } from '@/dialog'
import { useSessionStore } from '@/stores/session'
import { LEVEL, LEVELS, type Scope } from '@/trust'

/**
 * Says that something is safe. With `scopes` (what can be trusted about what is on the screen,
 * the narrowest first) it asks which, how much and why; without, it is the whole form, for
 * trusting something that is not on the screen. It saves the answer itself and says `trusted`
 * with what it saved, so the page can read again what the decision changes.
 */
const props = defineProps<{ scopes?: Scope[] }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ trusted: [rule: Trust] }>()

const session = useSessionStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const chosen = ref('')
const verdict = ref<TrustLevel>('not_suspicious')
const note = ref('')
const busy = ref(false)
const failure = ref<string | null>(null)

// Each time it opens it starts from the narrowest choice and a safe verdict.
watch(open, (opening) => {
  if (!opening) return
  chosen.value = props.scopes?.[0]?.key ?? ''
  verdict.value = 'not_suspicious'
  note.value = ''
  failure.value = null
})

async function save(request: Parameters<typeof trust>[0]) {
  busy.value = true
  failure.value = null
  try {
    const saved = await session.change((token) => trust(request, token))
    open.value = false
    emit('trusted', saved)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

function saveChoice() {
  const scope = props.scopes?.find((each) => each.key === chosen.value)
  if (!scope) return
  void save({ ...scope.request, verdict: verdict.value, note: note.value.trim() })
}
</script>

<template>
  <v-dialog
    v-model="open"
    :persistent="busy"
    max-width="620"
    scrollable
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="pa-6" data-test="trust-dialog">
      <h2 :id="titleId" class="text-title-large mb-1">Trust this</h2>
      <p class="text-body-medium text-medium-emphasis mb-4">
        What you trust never raises an alarm, whichever program reports it, now and from here on.
        You can take it back at any time under Trust.
      </p>

      <v-form v-if="scopes?.length" @submit.prevent="saveChoice">
        <v-radio-group v-model="chosen" hide-details class="mb-2" aria-label="What to trust">
          <v-radio
            v-for="scope in scopes"
            :key="scope.key"
            :value="scope.key"
            :data-test="`scope-${scope.key}`"
          >
            <template #label>
              <span class="trust-dialog__label">
                <span class="text-body-large">{{ scope.label }}</span>
                <span class="text-body-medium text-medium-emphasis">{{ scope.detail }}</span>
              </span>
            </template>
          </v-radio>
        </v-radio-group>
        <v-radio-group
          v-model="verdict"
          inline
          hide-details
          class="mb-2"
          aria-label="How much to trust it"
        >
          <v-radio
            v-for="kind in LEVELS"
            :key="kind"
            :value="kind"
            :label="LEVEL[kind].label"
            :data-test="`level-${kind}`"
          />
        </v-radio-group>
        <v-text-field
          v-model="note"
          label="Why (optional)"
          maxlength="500"
          autocomplete="off"
          class="mb-2"
          data-test="field-note"
        />
        <v-alert v-if="failure" type="error" variant="tonal" class="mb-3" data-test="trust-failure">
          {{ failure }}
        </v-alert>
        <div class="d-flex flex-wrap justify-end ga-3">
          <v-btn variant="text" :disabled="busy" data-test="trust-cancel" @click="open = false">
            Cancel
          </v-btn>
          <v-btn type="submit" color="primary" :loading="busy" data-test="trust-save">Trust</v-btn>
        </div>
      </v-form>
      <TrustForm
        v-else
        :rule="null"
        :busy="busy"
        :failure="failure"
        save-label="Trust"
        @save="save"
        @cancel="open = false"
      />
    </v-card>
  </v-dialog>
</template>

<style scoped>
.trust-dialog__label {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}
</style>
