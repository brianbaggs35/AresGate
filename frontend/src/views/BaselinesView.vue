<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  fetchBaselineInterfaces,
  fetchBaselineTalkers,
  type BaselineInterfaces,
  type BaselineTalkers,
} from '@/api/baselines'
import { errorMessage } from '@/api/client'
import AppPage from '@/components/AppPage.vue'
import BaselineInterface from '@/components/BaselineInterface.vue'
import BaselinePlaces from '@/components/BaselinePlaces.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount, formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Baselines: what AresGate has learned is normal here. Which hours of the day each interface is
 * busy in, so that a burst at night is told from an evening, and where each device usually talks
 * to, so that a first visit somewhere new is told from a routine one. What is learned can be
 * corrected: a place can be called expected, or forgotten. The device whose places are open is in
 * the address of the page.
 */
const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const interfaces = ref<BaselineInterfaces | null>(null)
const talkers = ref<BaselineTalkers | null>(null)
const interfacesError = ref<string | null>(null)
const talkersError = ref<string | null>(null)
const loading = ref(false)

const device = computed(() => {
  const value = route.query.device
  return typeof value === 'string' && value !== '' ? value : null
})

async function loadInterfaces() {
  try {
    interfaces.value = await session.call(fetchBaselineInterfaces)
    interfacesError.value = null
  } catch (error) {
    interfacesError.value = errorMessage(error)
  }
}

async function loadTalkers() {
  try {
    talkers.value = await session.call(fetchBaselineTalkers)
    talkersError.value = null
  } catch (error) {
    talkersError.value = errorMessage(error)
  }
}

async function load() {
  loading.value = true
  await Promise.all([loadInterfaces(), loadTalkers()])
  loading.value = false
}

onMounted(load)

function open(address: string | null) {
  void router.replace({ query: address ? { device: address } : {} })
}
</script>

<template>
  <AppPage class="baselines">
    <PageHeader
      title="Baselines"
      description="What AresGate has learned is normal on your network: how busy each connection is at each hour of the day, and where each device usually talks to. Something far outside it is reported."
    >
      <template #actions>
        <v-btn
          variant="text"
          :prepend-icon="RefreshCw"
          :loading="loading"
          data-test="refresh"
          @click="load"
        >
          Refresh
        </v-btn>
      </template>
    </PageHeader>

    <SectionCard
      title="Traffic by hour of the day"
      description="The middle of what each interface carries in each hour, learned from the interface counters. An hour that carries far more than that is reported."
    >
      <LoadError
        v-if="interfacesError && !interfaces"
        :message="interfacesError"
        :loading="loading"
        retry-test-id="interfaces-retry"
        data-test="interfaces-error"
        @retry="loadInterfaces"
      />
      <v-skeleton-loader v-else-if="!interfaces" type="article" />
      <p
        v-else-if="!interfaces.counted"
        class="text-body-large text-medium-emphasis"
        data-test="interfaces-uncounted"
      >
        No interface counters are collected yet. Connect your firewall under Integrations, and
        AresGate learns from how much each interface carries.
      </p>
      <p
        v-else-if="interfaces.series.length === 0"
        class="text-body-large text-medium-emphasis"
        data-test="interfaces-learning"
      >
        Still learning. It takes about {{ formatCount(interfaces.weeks) }} weeks of counters, and at
        least {{ formatCount(interfaces.min_hours) }} readings of an hour of the day, before it says
        what is usual for that hour.
      </p>
      <div v-else class="baselines__charts" data-test="interfaces-list">
        <BaselineInterface
          v-for="item in interfaces.series"
          :key="`${item.interface}/${item.direction}`"
          :series="item"
        />
      </div>
    </SectionCard>

    <SectionCard
      title="Where devices talk to"
      description="The places each device on your network reaches on the Internet. Once a device has been watched for a while, a place it has never been to is reported."
    >
      <LoadError
        v-if="talkersError && !talkers"
        :message="talkersError"
        :loading="loading"
        retry-test-id="talkers-retry"
        data-test="talkers-error"
        @retry="loadTalkers"
      />
      <v-skeleton-loader v-else-if="!talkers" type="list-item-two-line" />
      <p
        v-else-if="talkers.items.length === 0"
        class="text-body-large text-medium-emphasis"
        data-test="talkers-empty"
      >
        Nothing is learned yet. Places are learned from the connections your firewall writes down.
      </p>
      <template v-else>
        <p class="text-body-medium text-medium-emphasis" data-test="talkers-rule">
          A device is judged once it has been watched for
          {{ formatCount(talkers.watched_days) }} days and talks to
          {{ formatCount(talkers.min_places) }} places. Until then a new place is only learned. A
          place nobody went to for {{ formatCount(talkers.forget_days) }} days is forgotten, unless
          you expect it.
        </p>
        <ul class="talkers" aria-label="Devices" data-test="talkers-list">
          <li v-for="item in talkers.items" :key="item.address">
            <v-btn
              block
              variant="text"
              class="talkers__item"
              :aria-pressed="device === item.address"
              :aria-label="`Places of ${item.name ?? item.address}`"
              data-test="talker"
              @click="open(device === item.address ? null : item.address)"
            >
              <span class="talkers__who">
                <span class="text-title-small" data-test="talker-name">{{
                  item.name ?? item.address
                }}</span>
                <span v-if="item.name" class="text-body-medium text-medium-emphasis">{{
                  item.address
                }}</span>
              </span>
              <span class="talkers__facts text-body-medium text-medium-emphasis">
                Places: {{ formatCount(item.places) }}
                <template v-if="item.expected">
                  ({{ formatCount(item.expected) }} expected)</template
                >, last
                <time :datetime="item.last_seen_at">{{ formatDateTime(item.last_seen_at) }}</time>
              </span>
              <v-chip
                size="small"
                :color="item.judged ? 'primary' : undefined"
                data-test="talker-state"
              >
                {{ item.judged ? 'Judged' : 'Learning' }}
              </v-chip>
            </v-btn>
          </li>
        </ul>
        <p
          v-if="talkers.total > talkers.items.length"
          class="text-body-medium text-medium-emphasis"
        >
          Only the devices with the most places are listed:
          {{ formatCount(talkers.items.length) }} of {{ formatCount(talkers.total) }}.
        </p>
      </template>
    </SectionCard>

    <BaselinePlaces v-if="device" :address="device" @changed="loadTalkers" />
  </AppPage>
</template>

<style scoped>
.baselines__charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr));
  gap: 1rem;
}

.talkers {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0.75rem 0;
  padding: 0;
  list-style: none;
}

.talkers__item {
  height: auto;
  min-height: 3.5rem;
  padding-block: 0.5rem;
  text-transform: none;
  letter-spacing: normal;
}

.talkers__item :deep(.v-btn__content) {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  text-align: start;
  white-space: normal;
}

.talkers__who {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 10rem;
}
</style>
