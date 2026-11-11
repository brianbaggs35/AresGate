<script setup lang="ts">
import { Gavel, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchRulings, takeBackRuling, type Ruling } from '@/api/threatIntel'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import ThreatRulingDialog from '@/components/ThreatRulingDialog.vue'
import { formatAgo } from '@/format'
import { useSessionStore } from '@/stores/session'
import { KIND, RULING } from '@/threatIntel'

/**
 * What the owner has ruled safe or suspicious, whatever the services made of it, in one place: to
 * rule on something no service has been asked about, to change a ruling, or to take one back. A
 * ruling is the owner's own word and asks no service anything, so this works whether or not a
 * threat intelligence service is connected. `version` changes when something on the page was
 * ruled, so the list is read again, and `changed` says that something was ruled here.
 */
const props = defineProps<{ version?: number }>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()
const items = ref<Ruling[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const problem = ref<string | null>(null)
const typed = ref('')
const subject = ref('')
const dialogOpen = ref(false)
const removing = ref<string | null>(null)

/** What is ruled, once it has been read. */
const list = computed(() => items.value ?? [])

/** What is ruled already of what the dialog is open on, so it says so and can take it back. */
const current = computed(
  () =>
    list.value.find((item) => item.subject.toLowerCase() === subject.value.toLowerCase()) ?? null,
)

async function load() {
  loading.value = true
  error.value = null
  try {
    items.value = (await session.call(fetchRulings)).items
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

/** Opens the window on what was typed, or on a ruling in the list. */
function rule(text: string) {
  subject.value = text.trim()
  if (!subject.value) return
  problem.value = null
  dialogOpen.value = true
}

async function remove(item: Ruling) {
  if (removing.value) return
  removing.value = item.subject
  problem.value = null
  try {
    await session.change((token) => takeBackRuling(item.subject, token))
    await load()
    emit('changed')
  } catch (removeError) {
    problem.value = errorMessage(removeError)
  } finally {
    removing.value = null
  }
}

/** A ruling made or taken back in the window: the list is read again and the page told. */
async function changed() {
  await load()
  emit('changed')
}

watch(() => props.version, load)
onMounted(load)
</script>

<template>
  <SectionCard
    title="What you have ruled"
    description="Services can be wrong either way. Rule an address, a domain or a web address safe to correct a false alarm, or suspicious to correct one a service missed. A ruling is your word: it shows in place of what a service says, on every page, and the AI is told. It asks no service anything, and you can take it back at any time."
    data-test="threat-rulings"
  >
    <LoadError
      v-if="error && !items"
      :message="error"
      :loading="loading"
      retry-test-id="threat-rulings-retry"
      data-test="threat-rulings-error"
      @retry="load"
    />

    <v-skeleton-loader v-else-if="!items" type="list-item-two-line@2" data-test="rulings-loading" />

    <template v-else>
      <form novalidate class="rulings__add" data-test="rulings-form" @submit.prevent="rule(typed)">
        <v-text-field
          v-model="typed"
          label="Rule on something"
          placeholder="203.0.113.7, example.com or https://example.com/login"
          :prepend-inner-icon="Gavel"
          autocomplete="off"
          spellcheck="false"
          density="comfortable"
          hide-details
          clearable
          data-test="rulings-subject"
        />
        <v-btn type="submit" variant="tonal" :disabled="!typed.trim()" data-test="rulings-rule">
          Rule on it
        </v-btn>
      </form>

      <v-alert
        v-if="problem"
        type="error"
        variant="tonal"
        class="rulings__alert"
        data-test="rulings-problem"
      >
        {{ problem }}
      </v-alert>

      <EmptyState
        v-if="!list.length"
        title="Nothing is ruled yet"
        description="When a service flags something you know is fine, or misses something that is not, say so here, or from a report or an incident."
        data-test="rulings-empty"
      />

      <ul v-else class="rulings__list" data-test="rulings-list">
        <li
          v-for="item in list"
          :key="`${item.kind}-${item.subject}`"
          class="ruled"
          data-test="ruling-row"
        >
          <v-chip
            :color="RULING[item.verdict].color"
            :prepend-icon="RULING[item.verdict].icon"
            variant="tonal"
            size="small"
            class="ruled__verdict"
            data-test="ruling-verdict"
          >
            {{ RULING[item.verdict].short }}
          </v-chip>
          <span class="ruled__subject" data-test="ruling-subject-name">{{ item.subject }}</span>
          <span class="ruled__facts text-body-small text-medium-emphasis">
            <span>{{ KIND[item.kind] }}</span>
            <span>Ruled {{ formatAgo(item.set_at) }}</span>
            <span v-if="item.note" class="ruled__note" data-test="ruling-note-text">
              “{{ item.note }}”
            </span>
          </span>
          <span class="ruled__actions">
            <v-btn
              variant="text"
              size="small"
              :aria-label="`Change what you ruled of ${item.subject}`"
              data-test="ruling-change"
              @click="rule(item.subject)"
            >
              Change
            </v-btn>
            <v-btn
              icon
              variant="text"
              size="small"
              :loading="removing === item.subject"
              :aria-label="`Take back what you ruled of ${item.subject}`"
              data-test="ruling-remove"
              @click="remove(item)"
            >
              <Trash2 :size="18" aria-hidden="true" />
            </v-btn>
          </span>
        </li>
      </ul>
    </template>

    <ThreatRulingDialog
      v-if="subject"
      v-model="dialogOpen"
      :subject="subject"
      :ruling="current"
      @changed="changed"
    />
  </SectionCard>
</template>

<style scoped>
.rulings__add {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.rulings__alert {
  margin-top: 0.75rem;
}

.rulings__list {
  display: flex;
  flex-direction: column;
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.ruled {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas:
    'verdict subject actions'
    'facts facts actions';
  align-items: center;
  gap: 0.25rem 0.75rem;
  padding: 0.75rem 0.5rem;
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.ruled:first-child {
  border-top: 0;
}

.ruled__verdict {
  grid-area: verdict;
}

.ruled__subject {
  grid-area: subject;
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

.ruled__facts {
  grid-area: facts;
  display: flex;
  flex-wrap: wrap;
  gap: 0.125rem 1rem;
  min-width: 0;
}

.ruled__note {
  font-style: italic;
  overflow-wrap: anywhere;
}

.ruled__actions {
  grid-area: actions;
  display: flex;
  align-items: center;
}

@media (max-width: 599px) {
  .rulings__add {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
