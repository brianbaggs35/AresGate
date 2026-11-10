<script setup lang="ts">
import { computed } from 'vue'

import type { Finding } from '@/api/agents'
import { severityOf } from '@/agents'
import { citeRoute } from '@/chat'
import SeverityChip from '@/components/SeverityChip.vue'
import { SEVERITIES } from '@/severity'

/**
 * What a run found, the most serious first. Each finding says what it is, why, and what it is
 * based on, with a link to each incident or integration it names. What the model wrote is shown
 * as plain text and nothing more.
 */
const props = defineProps<{ findings: readonly Finding[] }>()

const ordered = computed(() =>
  [...props.findings].sort(
    (a, b) =>
      SEVERITIES.indexOf(severityOf(b.severity)) - SEVERITIES.indexOf(severityOf(a.severity)),
  ),
)
</script>

<template>
  <ul class="findings" data-test="agent-findings">
    <li v-for="(finding, at) in ordered" :key="at" class="finding" data-test="finding">
      <div class="finding__head">
        <SeverityChip :severity="severityOf(finding.severity)" />
        <h3 class="text-title-medium finding__title" data-test="finding-title">
          {{ finding.title }}
        </h3>
      </div>
      <p v-if="finding.detail" class="text-body-large finding__detail" data-test="finding-detail">
        {{ finding.detail }}
      </p>
      <div v-if="finding.cites.length" class="finding__cites" data-test="finding-cites">
        <span class="text-label-medium text-medium-emphasis">Based on</span>
        <template v-for="cite in finding.cites" :key="`${cite.kind}-${cite.key}`">
          <v-chip
            size="small"
            variant="tonal"
            :to="citeRoute(cite) ?? undefined"
            data-test="finding-cite"
          >
            {{ cite.label }}
          </v-chip>
        </template>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.findings {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.finding {
  padding: 1rem 1.25rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
}

.finding__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.finding__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.finding__detail {
  margin: 0.5rem 0 0;
  overflow-wrap: anywhere;
}

.finding__cites {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
