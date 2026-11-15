<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  DEVICE_STATES,
  fetchDeviceIntel,
  type DeviceIntelPage,
  type DeviceState,
} from '@/api/threatCatalog'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatAgo, formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'
import { DEVICE_STATE } from '@/threatIntel'

/**
 * What Fingerbank made of each device on the network: what it is (a phone, a camera, a printer),
 * who made it, what it runs and how sure Fingerbank is, next to what AresGate knows of the device
 * itself. Fingerbank is asked in the background, one device at a time and within its limits, about
 * the devices the owner keeps as assets and the ones in incidents, so looking through them asks it
 * nothing. A device with a private hardware address is listed with the reason it was not asked.
 * Filtered by what Fingerbank made of it, searched by what it is, its name, maker or address.
 * `version` changes when something on the page got an answer, so the list is read again.
 */
const props = defineProps<{ version?: number }>()

const PAGE = 25

const session = useSessionStore()
const page = ref<DeviceIntelPage | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const typed = ref('')
const text = ref('')
const state = ref<DeviceState | null>(null)
const shown = ref(PAGE)

const filtered = computed(() => text.value !== '' || state.value !== null)

/** How many devices the text matches, of every state. */
function kept(found: DeviceIntelPage): number {
  return DEVICE_STATES.reduce((sum, name) => sum + found.counts[name], 0)
}

/** The states to narrow the list to, each with how many devices it has. */
function filters(found: DeviceIntelPage) {
  return [
    { key: null, label: 'All', count: kept(found) },
    ...DEVICE_STATES.map((name) => ({
      key: name,
      label: DEVICE_STATE[name].label,
      count: found.counts[name],
    })),
  ]
}

async function load() {
  loading.value = true
  error.value = null
  try {
    page.value = await session.call(() =>
      fetchDeviceIntel({ q: text.value, state: state.value, limit: shown.value }),
    )
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

function find() {
  text.value = typed.value.trim()
  shown.value = PAGE
  void load()
}

function clear() {
  typed.value = ''
  find()
}

function choose(name: DeviceState | null) {
  state.value = name
  shown.value = PAGE
  void load()
}

function showMore() {
  shown.value += PAGE
  void load()
}

watch(() => props.version, load)
onMounted(load)
</script>

<template>
  <SectionCard
    title="Devices"
    description="What Fingerbank made of each device it was asked about: what it is, who made it and what it runs. AresGate asks in the background, one device at a time and within Fingerbank's limits, about your assets and the devices in incidents, so looking through them asks it nothing. What it learned goes when the device does."
    data-test="threat-devices"
  >
    <LoadError
      v-if="error && !page"
      :message="error"
      :loading="loading"
      retry-test-id="devices-retry"
      data-test="devices-error"
      @retry="load"
    />

    <v-skeleton-loader v-else-if="!page" type="list-item-two-line@3" data-test="devices-loading" />

    <EmptyState
      v-else-if="!kept(page) && !filtered"
      title="No devices identified yet"
      description="Once Fingerbank is connected, AresGate asks it what your assets and the devices in incidents are, and the answers show up here."
      data-test="devices-empty"
    >
      <v-btn :to="{ name: 'integrations' }" variant="tonal" data-test="devices-set-up">
        Go to Integrations
      </v-btn>
    </EmptyState>

    <template v-else>
      <form novalidate class="devices__find" data-test="devices-form" @submit.prevent="find">
        <v-text-field
          v-model="typed"
          label="Find a device"
          placeholder="What it is, its name, maker or address"
          :prepend-inner-icon="Search"
          autocomplete="off"
          spellcheck="false"
          density="comfortable"
          hide-details
          clearable
          data-test="devices-text"
          @click:clear="clear"
        />
        <v-btn type="submit" variant="tonal" :loading="loading" data-test="devices-find">
          Find
        </v-btn>
      </form>

      <fieldset class="devices__filters" data-test="devices-filters">
        <legend class="devices__legend">What Fingerbank made of it</legend>
        <v-btn
          v-for="filter in filters(page)"
          :key="filter.key ?? 'all'"
          :variant="state === filter.key ? 'flat' : 'outlined'"
          :color="state === filter.key ? 'primary' : undefined"
          :aria-pressed="state === filter.key"
          size="small"
          rounded="pill"
          :data-test="`devices-filter-${filter.key ?? 'all'}`"
          @click="choose(filter.key)"
        >
          {{ filter.label }} {{ formatCount(filter.count) }}
        </v-btn>
      </fieldset>

      <v-alert
        v-if="error"
        type="error"
        variant="tonal"
        class="devices__alert"
        data-test="devices-problem"
      >
        {{ error }}
      </v-alert>

      <p
        v-if="!page.items.length"
        class="text-body-medium text-medium-emphasis devices__none"
        data-test="devices-none"
      >
        Nothing kept matches.
      </p>

      <ul v-else class="devices__list" data-test="devices-list">
        <li
          v-for="item in page.items"
          :key="item.device_id"
          class="devices__row"
          :data-state="item.state"
          data-test="devices-row"
        >
          <div class="devices__head">
            <v-chip
              :color="DEVICE_STATE[item.state].color"
              :prepend-icon="DEVICE_STATE[item.state].icon"
              variant="tonal"
              size="small"
              data-test="devices-state"
            >
              {{ DEVICE_STATE[item.state].label }}
            </v-chip>
            <span class="devices__name" data-test="devices-name">
              {{ item.name ?? item.hostname ?? item.mac }}
            </span>
            <v-chip
              v-if="item.score !== null"
              size="x-small"
              variant="outlined"
              data-test="devices-score"
            >
              {{ item.score }}% sure
            </v-chip>
          </div>
          <p
            v-if="item.state !== 'identified'"
            class="text-body-small text-medium-emphasis devices__about"
            data-test="devices-about"
          >
            {{ DEVICE_STATE[item.state].about }}
          </p>
          <p
            v-if="item.path"
            class="text-body-small text-medium-emphasis devices__about"
            data-test="devices-path"
          >
            {{ item.path }}
          </p>
          <dl class="devices__facts text-body-small">
            <template v-if="item.manufacturer">
              <dt class="text-medium-emphasis">Maker</dt>
              <dd data-test="devices-manufacturer">{{ item.manufacturer }}</dd>
            </template>
            <template v-if="item.operating_system">
              <dt class="text-medium-emphasis">Runs</dt>
              <dd data-test="devices-os">{{ item.operating_system }}</dd>
            </template>
            <template v-if="item.vendor">
              <dt class="text-medium-emphasis">Network card</dt>
              <dd data-test="devices-vendor">{{ item.vendor }}</dd>
            </template>
            <template v-if="item.address">
              <dt class="text-medium-emphasis">Address</dt>
              <dd data-test="devices-address">{{ item.address }}</dd>
            </template>
            <dt class="text-medium-emphasis">Hardware address</dt>
            <dd data-test="devices-mac">{{ item.mac }}</dd>
            <dt class="text-medium-emphasis">Seen</dt>
            <dd data-test="devices-seen">{{ formatAgo(item.last_seen_at) }}</dd>
            <dt class="text-medium-emphasis">Asked</dt>
            <dd data-test="devices-checked">
              {{ formatAgo(item.checked_at) }},
              {{ item.reason === 'asset' ? 'as an asset' : 'for an incident' }}
            </dd>
          </dl>
        </li>
      </ul>

      <div v-if="page.total > page.items.length" class="devices__more">
        <v-btn variant="text" :loading="loading" data-test="devices-more" @click="showMore">
          Show more ({{ formatCount(page.total - page.items.length) }} left)
        </v-btn>
      </div>
    </template>
  </SectionCard>
</template>

<style scoped>
.devices__find {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.devices__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

/* Read out as the name of the group, and not shown. */
.devices__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.devices__alert {
  margin-top: 0.75rem;
}

.devices__none {
  margin: 1rem 0 0;
}

.devices__list {
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.devices__row {
  padding: 0.75rem 0.5rem;
}

.devices__row + .devices__row {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.devices__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.devices__name {
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

.devices__about {
  margin: 0.25rem 0 0;
}

.devices__facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.125rem 1rem;
  margin: 0.5rem 0 0;
}

.devices__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.devices__more {
  display: flex;
  justify-content: center;
  margin-top: 0.5rem;
}
</style>
