<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import { fetchSince, markSeen, type Since } from '@/api/since'
import { formatCount } from '@/format'
import { SEVERITIES } from '@/severity'
import { useSessionStore } from '@/stores/session'

/**
 * What is new since the owner last looked at the dashboard: the incidents that began (by how
 * serious), what the AI cleared and the devices that appeared, each a link to the list it counts.
 * It is the server that remembers when they last looked, so a phone and a computer agree. It says
 * nothing on a first visit or when nothing changed, and never counts what the owner did
 * themselves. Dismissing it, or leaving the dashboard, is looking.
 */
const session = useSessionStore()
const headingId = useId()

const news = ref<Since | null>(null)
const dismissed = ref(false)
/** Whether the owner has been told, so that leaving counts as having looked. */
let shown = false

/** The things that are new, each with the words for it and where to read it. */
const lines = computed(() => {
  const found = news.value
  if (found === null) return []
  const incidents = Object.values(found.incidents).reduce((sum, count) => sum + count, 0)
  const serious = [...SEVERITIES]
    .reverse()
    .filter((level) => found.incidents[level] > 0)
    .map((level) => `${formatCount(found.incidents[level])} ${level}`)
  const all: { key: string; text: string; to: RouteLocationRaw }[] = []
  if (incidents > 0) {
    all.push({
      key: 'incidents',
      text: `${formatCount(incidents)} new ${incidents === 1 ? 'incident' : 'incidents'} (${serious.join(', ')})`,
      // What began since, so the list is what was counted.
      to: { name: 'incidents', query: { view: 'all', q: `began:"${found.since}"` } },
    })
  }
  if (found.cleared_by_ai > 0) {
    all.push({
      key: 'cleared',
      text: `${formatCount(found.cleared_by_ai)} cleared by the AI`,
      to: { name: 'cleared' },
    })
  }
  if (found.new_devices > 0) {
    all.push({
      key: 'devices',
      text: `${formatCount(found.new_devices)} new ${found.new_devices === 1 ? 'device' : 'devices'}`,
      to: { name: 'assets', query: { new: '1' } },
    })
  }
  return all
})

onMounted(async () => {
  try {
    news.value = await session.call(() => fetchSince())
    shown = lines.value.length > 0
  } catch {
    // Not knowing what is new is not a reason to say anything.
  }
})

async function look() {
  dismissed.value = true
  shown = false
  try {
    await session.change((token) => markSeen(token))
  } catch {
    // It is still there next time, which is the honest answer.
  }
}

// Leaving the page is looking at what it said.
onBeforeUnmount(() => {
  if (shown) void session.change((token) => markSeen(token)).catch(() => undefined)
})
</script>

<template>
  <section
    v-if="lines.length && !dismissed"
    class="since"
    :aria-labelledby="headingId"
    data-test="since"
  >
    <div class="since__body">
      <h2 :id="headingId" class="text-title-small">Since you last looked</h2>
      <ul class="since__list">
        <li v-for="line in lines" :key="line.key">
          <router-link :to="line.to" class="since__link" :data-test="`since-${line.key}`">
            {{ line.text }}
          </router-link>
        </li>
      </ul>
    </div>
    <v-btn
      icon
      variant="text"
      size="small"
      aria-label="Dismiss what is new"
      data-test="since-dismiss"
      @click="look"
    >
      <v-icon :icon="X" />
    </v-btn>
  </section>
</template>

<style scoped>
.since {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-inline-start: 4px solid rgb(var(--v-theme-primary));
  border-radius: 0.5rem;
  background: rgb(var(--v-theme-surface));
}

.since h2 {
  margin: 0 0 0.25rem;
}

.since__list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.since__link {
  display: inline-block;
  min-height: 24px;
  color: rgb(var(--v-theme-primary));
  text-underline-offset: 0.2em;
}

.since__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}
</style>
