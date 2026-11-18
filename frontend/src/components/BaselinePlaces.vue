<script setup lang="ts">
import { ref, watch } from 'vue'

import {
  expectPlace,
  fetchBaselinePlaces,
  forgetPlace,
  type BaselinePlace,
  type BaselinePlaces,
} from '@/api/baselines'
import { errorMessage } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount, formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * The places one device talks to, as networks and ports: the expected ones first, then the most
 * visited. A place can be called expected, so the device going there is never news, or forgotten,
 * so that its next visit is new again. A place the device is yet to go to can be expected too.
 */
const props = defineProps<{ address: string }>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()
const found = ref<BaselinePlaces | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const failure = ref<string | null>(null)
const busy = ref(false)
const forgetting = ref<BaselinePlace | null>(null)
const asking = ref(false)
const network = ref('')
const port = ref('443')
/** Which load is the newest, so the answer for a device that is no longer shown is dropped. */
let latest = 0

const where = (place: BaselinePlace) => {
  const port = place.port === 0 ? 'no port' : `port ${place.port.toString()}`
  return `${place.network}, ${port}`
}

async function load() {
  const mine = ++latest
  loading.value = true
  loadError.value = null
  try {
    const answer = await session.call(() => fetchBaselinePlaces(props.address))
    if (mine === latest) found.value = answer
  } catch (error) {
    if (mine === latest) loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

watch(
  () => props.address,
  () => {
    found.value = null
    failure.value = null
    void load()
  },
  { immediate: true },
)

async function change(act: (token: string) => Promise<unknown>) {
  failure.value = null
  busy.value = true
  try {
    await session.change(act)
    await load()
    emit('changed')
    return true
  } catch (error) {
    failure.value = errorMessage(error)
    return false
  } finally {
    busy.value = false
  }
}

const setExpected = (place: BaselinePlace, expected: boolean) =>
  change((token) =>
    expectPlace(props.address, { network: place.network, port: place.port, expected }, token),
  )

async function add() {
  const added = await change((token) =>
    expectPlace(
      props.address,
      { network: network.value.trim(), port: Number(port.value), expected: true },
      token,
    ),
  )
  if (added) network.value = ''
}

function askToForget(place: BaselinePlace) {
  forgetting.value = place
  asking.value = true
}

async function forget() {
  const place = forgetting.value as BaselinePlace
  await change((token) =>
    forgetPlace(props.address, { network: place.network, port: place.port }, token),
  )
  asking.value = false
}
</script>

<template>
  <SectionCard
    :title="found?.name ?? address"
    description="Where this device talks to on the Internet, as networks (a /24, or a /64 for IPv6) and ports. A place you call expected is never reported as new."
    data-test="baseline-places"
  >
    <LoadError
      v-if="loadError && !found"
      :message="loadError"
      :loading="loading"
      retry-test-id="places-retry"
      data-test="places-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!found" type="list-item-two-line" />
    <template v-else>
      <ul class="places" aria-label="Places" data-test="places-list">
        <li
          v-for="place in found.places"
          :key="`${place.network}/${place.port}`"
          class="places__item"
        >
          <div class="places__what">
            <span class="text-title-small" data-test="place-where">{{ where(place) }}</span>
            <v-chip v-if="place.expected" size="small" color="primary" data-test="place-expected">
              Expected
            </v-chip>
            <span class="text-body-medium text-medium-emphasis">
              Visits: {{ formatCount(place.hits) }}, since
              <time :datetime="place.first_seen_at">{{
                formatDateTime(place.first_seen_at)
              }}</time>, last
              <time :datetime="place.last_seen_at">{{ formatDateTime(place.last_seen_at) }}</time>
            </span>
          </div>
          <div class="places__actions">
            <v-btn
              variant="text"
              :disabled="busy"
              :aria-label="`${place.expected ? 'No longer expect' : 'Expect'} ${where(place)}`"
              data-test="place-expect"
              @click="setExpected(place, !place.expected)"
            >
              {{ place.expected ? 'Not expected' : 'Expect' }}
            </v-btn>
            <v-btn
              variant="text"
              :disabled="busy"
              :aria-label="`Forget ${where(place)}`"
              data-test="place-forget"
              @click="askToForget(place)"
            >
              Forget
            </v-btn>
          </div>
        </li>
      </ul>

      <form class="places__add" novalidate @submit.prevent="add">
        <v-text-field
          v-model="network"
          label="Expect another place"
          hint="A network such as 198.51.100.0/24"
          persistent-hint
          autocomplete="off"
          data-test="place-network"
        />
        <v-text-field
          v-model="port"
          label="Port"
          inputmode="numeric"
          autocomplete="off"
          hint="0 for none"
          persistent-hint
          data-test="place-port"
        />
        <v-btn
          type="submit"
          variant="tonal"
          :disabled="busy || network.trim() === ''"
          data-test="place-add"
        >
          Expect
        </v-btn>
      </form>
      <v-alert
        v-if="failure"
        type="error"
        variant="tonal"
        role="alert"
        class="mt-4"
        data-test="places-failure"
      >
        {{ failure }}
      </v-alert>
    </template>
    <ConfirmDialog
      v-model="asking"
      title="Forget this place?"
      confirm-label="Forget"
      destructive
      :busy="busy"
      @confirm="forget"
    >
      The next time this device goes to this place, it is new again.
    </ConfirmDialog>
  </SectionCard>
</template>

<style scoped>
.places {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.places__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding-block-end: 0.75rem;
  border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.places__item:last-child {
  border-block-end: 0;
}

.places__what {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  min-width: 14rem;
  overflow-wrap: anywhere;
}

.places__actions {
  display: flex;
  gap: 0.25rem;
}

.places__add {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.75rem;
  margin-block-start: 1rem;
}

@media (max-width: 600px) {
  .places__add {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
