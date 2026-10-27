<script setup lang="ts">
import { ChevronDown, ChevronUp, Search, X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchLog, type LogDetail, type LogEvent } from '@/api/logs'
import CopyButton from '@/components/CopyButton.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import RawRecord from '@/components/RawRecord.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { useKeyboardReturn } from '@/dialog'
import { fieldsOf } from '@/logs'
import { useSessionStore } from '@/stores/session'

/**
 * One event in a sheet that slides in from the side (the whole screen on a phone): what it says,
 * the incident AresGate filed it into, every field with a button to copy it or to look for
 * others like it, and the record the integration sent, pretty-printed. The list behind it
 * stays where it was, and `j` and `k` (or the arrows at the top) go to the next older or newer
 * event without closing it.
 */
const props = defineProps<{
  /** The event as the list has it, which is on screen at once; the rest is asked for. */
  event: LogEvent | null
  /** Whether there is an older event in the list to go to, and a newer one. */
  hasOlder: boolean
  hasNewer: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{
  /** A term for the search that finds events like this one. */
  search: [term: string]
  step: [direction: 'older' | 'newer']
}>()

const session = useSessionStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const detail = ref<LogDetail | null>(null)
const failure = ref<string | null>(null)
const body = ref<HTMLElement | null>(null)
/** Which load is the newest, so the answer for an event that has been stepped past is dropped. */
let latest = 0

async function load() {
  const mine = ++latest
  const cursor = props.event?.cursor
  detail.value = null
  failure.value = null
  if (!cursor) return
  try {
    const found = await session.call(() => fetchLog(cursor))
    if (mine === latest) detail.value = found
  } catch (error) {
    if (mine === latest) failure.value = errorMessage(error)
  }
}

// Each event that is shown, from the moment the sheet opens.
watch(
  () => [open.value, props.event?.cursor] as const,
  async ([opening]) => {
    if (!opening) return
    void load()
    await nextTick()
    if (body.value) body.value.scrollTop = 0
  },
  { immediate: true },
)

// Read only where there is an event to show.
const fields = computed(() => fieldsOf(props.event as LogEvent))
/** The addresses the event names, once each, to look for others with. */
const addresses = computed(() =>
  [...new Set([props.event?.src_address, props.event?.dst_address])].filter(
    (address): address is string => !!address,
  ),
)

/** `j` and `k` step through the events while the sheet is open. The keyboard is not inside the
 * card when the sheet has just opened (the dialog's own box has it), so the keys are heard on the
 * window for as long as the sheet is open. */
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
    content-class="log-drawer"
    transition="slide-x-reverse-transition"
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card v-if="event" class="log-drawer__card" data-test="log-drawer">
      <header class="log-drawer__head">
        <SeverityChip :severity="event.severity" />
        <span class="log-drawer__where text-body-medium text-medium-emphasis">
          {{ event.source_name }} · {{ event.kind }}
        </span>
        <span class="log-drawer__steps">
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :disabled="!hasNewer"
            aria-label="Newer event"
            title="Newer event (K)"
            data-test="drawer-newer"
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
            aria-label="Older event"
            title="Older event (J)"
            data-test="drawer-older"
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
            data-test="drawer-close"
            @click="open = false"
          >
            <v-icon :icon="X" />
          </v-btn>
        </span>
      </header>

      <div ref="body" class="log-drawer__body">
        <h2 :id="titleId" class="log-drawer__title text-title-large" data-test="drawer-title">
          {{ event.summary }}
        </h2>

        <v-alert
          v-if="failure"
          type="error"
          variant="tonal"
          density="compact"
          data-test="drawer-error"
        >
          {{ failure }}
          <template #append>
            <v-btn variant="text" size="small" data-test="drawer-retry" @click="load">
              Try again
            </v-btn>
          </template>
        </v-alert>

        <router-link
          v-if="detail?.incident"
          :to="{ name: 'incident', params: { id: detail.incident.id } }"
          class="log-drawer__incident"
          data-test="drawer-incident"
        >
          <span class="text-label-large text-medium-emphasis">Filed in an incident</span>
          <span class="text-title-medium">{{ detail.incident.title }}</span>
          <span class="log-drawer__chips">
            <SeverityChip :severity="detail.incident.severity" />
            <IncidentStatusChip :status="detail.incident.status" />
          </span>
        </router-link>
        <p
          v-else-if="detail"
          class="text-body-medium text-medium-emphasis"
          data-test="drawer-no-incident"
        >
          Not part of an incident.
        </p>

        <dl class="log-drawer__fields">
          <div
            v-for="field in fields"
            :key="field.id"
            class="log-drawer__field"
            :data-test="`field-${field.id}`"
          >
            <dt class="text-body-medium text-medium-emphasis">{{ field.name }}</dt>
            <dd class="text-body-large">
              <span class="log-drawer__value">{{ field.value }}</span>
              <span class="log-drawer__actions">
                <CopyButton :text="field.copy ?? field.value" :label="field.name" />
                <v-btn
                  v-if="field.term"
                  icon
                  variant="text"
                  size="small"
                  density="comfortable"
                  :aria-label="`Show events with ${field.name.toLowerCase()} ${field.value}`"
                  :title="`Show events with ${field.name.toLowerCase()} ${field.value}`"
                  :data-test="`find-${field.id}`"
                  @click="emit('search', field.term)"
                >
                  <v-icon :icon="Search" size="18" />
                </v-btn>
              </span>
            </dd>
          </div>
        </dl>

        <ul v-if="addresses.length" class="log-drawer__links" data-test="drawer-addresses">
          <li v-for="address in addresses" :key="address">
            <router-link :to="{ name: 'logs', query: { q: `address:${address}` } }">
              All events with {{ address }}
            </router-link>
          </li>
        </ul>

        <v-skeleton-loader v-if="!detail && !failure" type="paragraph" data-test="drawer-loading" />
        <RawRecord v-else-if="detail" :raw="detail.raw" />
      </div>
    </v-card>
  </v-dialog>
</template>

<!-- The dialog's own box is outside the component, so it is shaped here: a sheet at the right,
  the width of the screen on a phone. -->
<style>
.v-dialog > .v-overlay__content.log-drawer {
  width: min(100%, 36rem);
  max-width: 100%;
  height: 100%;
  max-height: 100%;
  margin: 0;
  inset-block: 0;
  inset-inline: auto 0;
}

@media (prefers-reduced-motion: reduce) {
  .v-dialog > .v-overlay__content.log-drawer {
    transition: none;
  }
}
</style>

<style scoped>
.log-drawer__card {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 0;
  padding-bottom: env(safe-area-inset-bottom);
}

.log-drawer__head {
  display: flex;
  align-items: center;
  gap: 0.5rem 0.75rem;
  padding: 0.75rem 0.75rem 0.75rem 1.25rem;
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant));
}

.log-drawer__where {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-drawer__steps {
  display: flex;
  margin-inline-start: auto;
}

.log-drawer__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  overflow-y: auto;
}

.log-drawer__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.log-drawer__incident {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  color: inherit;
  text-decoration: none;
}

.log-drawer__incident:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.log-drawer__incident:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.log-drawer__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.log-drawer__fields {
  margin: 0;
}

.log-drawer__field {
  display: grid;
  grid-template-columns: 7rem minmax(0, 1fr);
  align-items: center;
  gap: 0.25rem 0.75rem;
  min-height: 2.5rem;
  padding: 0.125rem 0;
}

.log-drawer__field + .log-drawer__field {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.log-drawer__field dd {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin: 0;
}

.log-drawer__value {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.log-drawer__links {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.log-drawer__links a {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  color: rgb(var(--v-theme-primary));
}

/* Where there is a pointer, the buttons for a value wait until it is looked at. */
@media (hover: hover) {
  .log-drawer__actions {
    opacity: 0;
  }

  .log-drawer__field:hover .log-drawer__actions,
  .log-drawer__field:focus-within .log-drawer__actions {
    opacity: 1;
  }
}

@media (max-width: 599.98px) {
  .log-drawer__field {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
