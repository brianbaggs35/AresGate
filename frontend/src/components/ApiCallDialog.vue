<script setup lang="ts">
import { ChevronDown, ChevronUp, X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { errorMessage } from '@/api/client'
import { fetchCall, type Call, type CallFull, type CallPair } from '@/api/integrations'
import { addressOf, curlOf, fullAddressOf, timings } from '@/apiCall'
import CopyButton from '@/components/CopyButton.vue'
import LoadError from '@/components/LoadError.vue'
import { useKeyboardReturn } from '@/dialog'
import { formatBytes, formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * One request of the API log, with all that was kept of it: where it went, what it carried, how
 * it was answered and the start of the answer. None of it is a secret: a header or a query
 * parameter that holds a credential is shown by its name with the value hidden. What the system
 * answered is its own text, so it is shown as plain text and nothing more. `j` and `k`, or the
 * arrows at the top, go to the next older or newer request without closing it.
 */
const props = defineProps<{
  integration: string
  /** The request as the list has it, which is on screen at once; the rest is asked for. */
  call: Call | null
  /** The name of its connection, when the integration has more than one. */
  connection: string | null
  hasOlder: boolean
  hasNewer: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ step: [direction: 'older' | 'newer'] }>()

const session = useSessionStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)
// On a phone it fills the screen: there is a lot to read, and a card that stops short of the
// bottom bar leaves its buttons half under it.
const { smAndDown } = useDisplay()

const full = ref<CallFull | null>(null)
const failure = ref<string | null>(null)
const loading = ref(false)
const body = ref<HTMLElement | null>(null)
/** Which load is the newest, so the answer for a request that has been stepped past is dropped. */
let latest = 0

async function load() {
  const mine = ++latest
  const id = props.call?.id
  full.value = null
  failure.value = null
  if (id === undefined) return
  loading.value = true
  try {
    const found = await session.call(() => fetchCall(props.integration, id))
    if (mine === latest) full.value = found
  } catch (error) {
    if (mine === latest) failure.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

// Each request that is shown, from the moment the sheet opens.
watch(
  () => [open.value, props.call?.id] as const,
  async ([opening]) => {
    if (!opening) return
    void load()
    await nextTick()
    if (body.value) body.value.scrollTop = 0
  },
  { immediate: true },
)

const detail = computed(() => full.value?.detail ?? null)
const outcome = computed(() => {
  const status = props.call?.status_code
  return status == null ? 'No answer' : (detail.value?.status_line ?? String(status))
})
/** A 429 is a limit that held the request back, which says nothing of the connection being broken. */
const limited = computed(() => props.call?.status_code === 429)
const times = computed(() =>
  detail.value && props.call ? timings(detail.value, props.call.duration_ms) : [],
)
const answered = computed(() => !!detail.value?.status_line)

const shown = (pair: CallPair) => pair.value ?? 'hidden'

/** `j` and `k` step through the requests while the sheet is open, unless something is being
 * typed. The keyboard is not inside the card when the sheet has just opened, so the keys are
 * heard on the window for as long as it is open. */
function typing(target: EventTarget | null): boolean {
  return target instanceof Element && !!target.closest('input, textarea, select, [contenteditable]')
}

function onKey(event: KeyboardEvent) {
  if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return
  if (event.key === 'j' && props.hasOlder) emit('step', 'older')
  else if (event.key === 'k' && props.hasNewer) emit('step', 'newer')
}

watch(
  open,
  (opening) => {
    if (opening) window.addEventListener('keydown', onKey)
    else window.removeEventListener('keydown', onKey)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <v-dialog
    v-model="open"
    max-width="860"
    scrollable
    :fullscreen="smAndDown"
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card v-if="call" class="api-detail" data-test="call-sheet">
      <header class="api-detail__head">
        <h2 :id="titleId" class="api-detail__title text-title-large" data-test="sheet-title">
          <span class="api-detail__method">{{ call.method }}</span>
          <code>{{ call.path }}</code>
        </h2>
        <span class="api-detail__steps">
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :disabled="!hasNewer"
            aria-label="Newer request"
            title="Newer request (K)"
            data-test="sheet-newer"
            @click="emit('step', 'newer')"
          >
            <v-icon :icon="ChevronUp" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :disabled="!hasOlder"
            aria-label="Older request"
            title="Older request (J)"
            data-test="sheet-older"
            @click="emit('step', 'older')"
          >
            <v-icon :icon="ChevronDown" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            aria-label="Close"
            data-test="sheet-close"
            @click="open = false"
          >
            <v-icon :icon="X" />
          </v-btn>
        </span>
      </header>

      <div ref="body" class="api-detail__body">
        <dl class="api-detail__facts" data-test="sheet-facts">
          <div>
            <dt>Started</dt>
            <dd>
              <time :datetime="call.occurred_at">{{ formatDateTime(call.occurred_at) }}</time>
            </dd>
          </div>
          <div>
            <dt>Result</dt>
            <dd data-test="sheet-result">{{ outcome }}</dd>
          </div>
          <div v-if="connection">
            <dt>Connection</dt>
            <dd data-test="sheet-connection">{{ connection }}</dd>
          </div>
          <div v-if="detail">
            <dt>Made by</dt>
            <dd data-test="sheet-caller">{{ detail.caller ?? 'Not recorded' }}</dd>
          </div>
        </dl>

        <v-alert
          v-if="call.error"
          :type="limited ? 'info' : 'warning'"
          variant="tonal"
          density="compact"
          class="mt-3"
          data-test="sheet-error"
        >
          {{ call.error
          }}<template v-if="limited">. A limit held it back, which isn't a failure.</template>
        </v-alert>

        <LoadError
          v-if="failure"
          :message="failure"
          :loading="loading"
          retry-test-id="sheet-retry"
          class="mt-3"
          @retry="load"
        />
        <v-skeleton-loader
          v-else-if="!full"
          type="article"
          class="mt-3"
          data-test="sheet-loading"
        />
        <v-alert
          v-else-if="!detail"
          type="info"
          variant="tonal"
          density="compact"
          class="mt-3"
          data-test="sheet-old"
        >
          This request was made before AresGate kept more than the method, the path, the status, the
          time and the reason it failed, so the rest was not kept.
        </v-alert>

        <template v-if="detail">
          <section aria-labelledby="sheet-request" class="api-detail__section">
            <h3 id="sheet-request" class="text-title-medium">Request</h3>
            <p class="api-detail__address" data-test="sheet-address">
              <code>{{ fullAddressOf(detail) }}</code>
              <CopyButton :text="addressOf(detail)" label="the address" />
              <CopyButton :text="curlOf(call.method, detail)" label="as a curl command" />
            </p>
            <p class="text-body-medium text-medium-emphasis">
              The credentials are never kept, so a copied curl command has a
              <code>&lt;NAME&gt;</code> where each one goes.
            </p>
            <template v-if="detail.query.length">
              <h4 class="text-label-large mt-3">Query</h4>
              <dl class="api-detail__pairs" data-test="sheet-query">
                <div v-for="pair in detail.query" :key="pair.name + pair.value" data-test="pair">
                  <dt>{{ pair.name }}</dt>
                  <dd :class="{ 'text-medium-emphasis': pair.value === null }">
                    {{ shown(pair) }}
                  </dd>
                </div>
              </dl>
            </template>
            <h4 class="text-label-large mt-3">Headers sent</h4>
            <dl class="api-detail__pairs" data-test="sheet-request-headers">
              <div v-for="pair in detail.request_headers" :key="pair.name" data-test="pair">
                <dt>{{ pair.name }}</dt>
                <dd :class="{ 'text-medium-emphasis': pair.value === null }">{{ shown(pair) }}</dd>
              </div>
            </dl>
          </section>

          <section aria-labelledby="sheet-timing" class="api-detail__section">
            <h3 id="sheet-timing" class="text-title-medium">How long it took</h3>
            <dl class="api-detail__pairs" data-test="sheet-timing">
              <div v-for="time in times" :key="time.label">
                <dt>{{ time.label }}</dt>
                <dd>{{ time.ms }} ms</dd>
              </div>
            </dl>
            <p class="text-body-medium text-medium-emphasis">
              The time to connect and to set up the secure connection is not kept apart, because a
              connection that is already open is reused.
            </p>
          </section>

          <section aria-labelledby="sheet-answer" class="api-detail__section">
            <h3 id="sheet-answer" class="text-title-medium">Answer</h3>
            <p v-if="!answered" class="text-body-medium" data-test="sheet-unanswered">
              No answer came.
            </p>
            <template v-else>
              <dl class="api-detail__pairs" data-test="sheet-answer-facts">
                <div>
                  <dt>Status</dt>
                  <dd>{{ detail.status_line }}</dd>
                </div>
                <div v-if="detail.content_type">
                  <dt>Type</dt>
                  <dd>{{ detail.content_type }}</dd>
                </div>
                <div v-if="detail.size != null">
                  <dt>Size</dt>
                  <dd data-test="sheet-size">
                    {{ formatBytes(detail.size)
                    }}<template v-if="detail.cut">
                      (cut: only what was asked for was read)</template
                    >
                  </dd>
                </div>
                <div v-if="detail.address">
                  <dt>Came from</dt>
                  <dd data-test="sheet-resolved">{{ detail.address }}</dd>
                </div>
              </dl>
              <template v-if="detail.certificate">
                <h4 class="text-label-large mt-3">Certificate it presented</h4>
                <dl class="api-detail__pairs" data-test="sheet-certificate">
                  <div>
                    <dt>Subject</dt>
                    <dd>{{ detail.certificate.subject }}</dd>
                  </div>
                  <div>
                    <dt>Issuer</dt>
                    <dd>{{ detail.certificate.issuer }}</dd>
                  </div>
                  <div>
                    <dt>Fingerprint</dt>
                    <dd class="api-detail__mono">{{ detail.certificate.fingerprint }}</dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd>{{ formatDateTime(detail.certificate.not_after) }}</dd>
                  </div>
                </dl>
              </template>
              <h4 class="text-label-large mt-3">Headers answered</h4>
              <dl class="api-detail__pairs" data-test="sheet-response-headers">
                <div v-for="(pair, index) in detail.response_headers" :key="index" data-test="pair">
                  <dt>{{ pair.name }}</dt>
                  <dd :class="{ 'text-medium-emphasis': pair.value === null }">
                    {{ shown(pair) }}
                  </dd>
                </div>
              </dl>
            </template>
            <h4 class="text-label-large mt-3">
              Start of the answer
              <CopyButton v-if="full?.excerpt" :text="full.excerpt" label="the answer" />
            </h4>
            <pre
              v-if="full?.excerpt"
              class="api-detail__excerpt"
              tabindex="0"
              data-test="sheet-excerpt"
              >{{ full.excerpt }}</pre>
            <p v-else class="text-body-medium text-medium-emphasis" data-test="sheet-no-excerpt">
              No answer was kept. AresGate keeps the start of the answer to a request that failed,
              and of the latest few that worked, and nothing of an answer that is not text.
            </p>
          </section>
        </template>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.api-detail {
  display: flex;
  flex-direction: column;
  max-height: 100%;
}

.api-detail__head {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 1rem 1rem 0.5rem 1.5rem;
}

.api-detail__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.api-detail__method {
  margin-right: 0.5rem;
  font-weight: 600;
}

.api-detail__steps {
  display: flex;
  flex: none;
}

.api-detail__body {
  padding: 0 1.5rem 1.5rem;
  overflow-y: auto;
}

.api-detail__facts,
.api-detail__pairs {
  display: grid;
  margin: 0.5rem 0 0;
  gap: 0.25rem 1rem;
}

.api-detail__facts {
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}

.api-detail__facts dt,
.api-detail__pairs dt {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.8125rem;
}

.api-detail__facts dd,
.api-detail__pairs dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.api-detail__pairs > div {
  display: grid;
  grid-template-columns: minmax(7rem, 11rem) 1fr;
  gap: 0.75rem;
}

@media (width <= 600px) {
  .api-detail__pairs > div {
    grid-template-columns: 1fr;
    gap: 0;
  }
}

.api-detail__section {
  margin-top: 1.5rem;
}

.api-detail__address {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin: 0.5rem 0;
  overflow-wrap: anywhere;
}

.api-detail__address code,
.api-detail__mono,
.api-detail__title code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em;
}

.api-detail__excerpt {
  max-height: 18rem;
  margin: 0.5rem 0 0;
  padding: 0.75rem 1rem;
  overflow: auto;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant), 0.4);
  font-size: 0.8125rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
