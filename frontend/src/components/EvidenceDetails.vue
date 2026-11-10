<script setup lang="ts">
import { ArrowDownToLine, ArrowUpFromLine, Crosshair, Tag, Terminal } from '@lucide/vue'
import { computed } from 'vue'

import type { Evidence } from '@/api/incidents'
import { APP_ICON, HOST_ICON, namedByKind, namedLook, volumesOf } from '@/evidence'

/**
 * What one program said of an alert besides who, where and when, in the same layout for every
 * program: the machine and the application, the rule's own facts, the ATT&CK technique it was
 * matched to, what it named, how much traffic it was and the log line it came from. Whatever the
 * program left out is not shown, so a program that says little takes little room.
 */
const props = defineProps<{ evidence: Evidence }>()

const volumes = computed(() => volumesOf(props.evidence.traffic))
const named = computed(() => namedByKind(props.evidence.named))
</script>

<template>
  <div class="evidence" data-test="evidence">
    <div v-if="evidence.host || evidence.app" class="evidence__about">
      <v-chip
        v-if="evidence.host"
        size="small"
        variant="tonal"
        :prepend-icon="HOST_ICON"
        data-test="evidence-host"
      >
        {{ evidence.host }}
      </v-chip>
      <v-chip
        v-if="evidence.app"
        size="small"
        variant="tonal"
        :prepend-icon="APP_ICON"
        data-test="evidence-app"
      >
        {{ evidence.app }}
      </v-chip>
    </div>

    <dl v-if="evidence.facts.length" class="evidence__facts" data-test="evidence-facts">
      <div v-for="fact in evidence.facts" :key="fact.label" class="evidence__fact">
        <dt class="text-label-large text-medium-emphasis">{{ fact.label }}</dt>
        <dd class="text-body-large">{{ fact.value }}</dd>
      </div>
    </dl>

    <ul v-if="evidence.mitre.length" class="evidence__techniques" data-test="evidence-mitre">
      <li v-for="item in evidence.mitre" :key="item.id" class="evidence__technique">
        <v-icon :icon="Crosshair" size="18" aria-hidden="true" />
        <span class="text-body-large">
          <b>{{ item.id }}</b>
          {{ item.technique }}
          <span v-if="item.tactic" class="text-medium-emphasis">({{ item.tactic }})</span>
        </span>
      </li>
    </ul>

    <div
      v-for="[kind, items] in named"
      :key="kind"
      class="evidence__named"
      data-test="evidence-named"
    >
      <h4 class="text-label-large text-medium-emphasis">
        <v-icon :icon="namedLook(kind).icon" size="16" aria-hidden="true" />
        {{ items.length === 1 ? namedLook(kind).label : namedLook(kind).plural }}
      </h4>
      <ul class="evidence__values">
        <li v-for="item in items" :key="item.value" class="text-body-large">
          {{ item.value }}
        </li>
      </ul>
    </div>

    <div v-if="volumes.length" class="evidence__volumes" data-test="evidence-traffic">
      <figure v-for="volume in volumes" :key="volume.label" class="evidence__volume">
        <figcaption class="text-label-large text-medium-emphasis">{{ volume.label }}</figcaption>
        <div class="evidence__split" aria-hidden="true">
          <span class="evidence__out" :style="{ width: `${volume.outShare.toString()}%` }" />
        </div>
        <p class="text-body-medium evidence__sides">
          <span>
            <v-icon :icon="ArrowUpFromLine" size="16" aria-hidden="true" />
            <span class="sr-only">Sent: </span>{{ volume.outText }}
          </span>
          <span>
            <v-icon :icon="ArrowDownToLine" size="16" aria-hidden="true" />
            <span class="sr-only">Received: </span>{{ volume.inText }}
          </span>
        </p>
      </figure>
    </div>

    <div v-if="evidence.tags.length" class="evidence__tags" data-test="evidence-tags">
      <v-icon :icon="Tag" size="16" aria-hidden="true" />
      <v-chip v-for="tag in evidence.tags" :key="tag" size="small" variant="outlined">
        {{ tag }}
      </v-chip>
    </div>

    <figure v-if="evidence.excerpt" class="evidence__log" data-test="evidence-excerpt">
      <figcaption class="text-label-large text-medium-emphasis">
        <v-icon :icon="Terminal" size="16" aria-hidden="true" /> The log line
      </figcaption>
      <code class="text-body-medium">{{ evidence.excerpt }}</code>
    </figure>
  </div>
</template>

<style scoped>
.evidence {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.evidence__about,
.evidence__tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.evidence__facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0;
}

.evidence__fact {
  min-width: 0;
}

.evidence__fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.evidence__techniques,
.evidence__values {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.evidence__technique {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.evidence__named h4 {
  margin: 0 0 0.25rem;
  font-weight: inherit;
}

.evidence__values li {
  overflow-wrap: anywhere;
}

.evidence__volumes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 1rem;
}

.evidence__volume {
  margin: 0;
}

/* Outgoing is the filled part of a bar that is the whole of what the flow carried. */
.evidence__split {
  height: 0.5rem;
  margin: 0.375rem 0;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(var(--v-theme-secondary), 0.35);
}

.evidence__out {
  display: block;
  height: 100%;
  background: rgb(var(--v-theme-primary));
}

.evidence__sides {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0;
}

.evidence__log {
  margin: 0;
}

.evidence__log code {
  display: block;
  margin-top: 0.25rem;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
