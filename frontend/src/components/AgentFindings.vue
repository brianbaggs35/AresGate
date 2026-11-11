<script setup lang="ts">
import { Lightbulb } from '@lucide/vue'
import { computed } from 'vue'

import type { Finding } from '@/api/agents'
import { CONFIDENCE, reportedFor, severityOf } from '@/agents'
import { citeRoute } from '@/chat'
import SeverityChip from '@/components/SeverityChip.vue'
import { SEVERITIES } from '@/severity'

/**
 * What a run found, the most serious first. Each finding says what it is, why, what to do about
 * it, how sure the agent is, how long it has been reported, and what it is based on, with a link
 * to each incident or integration it names. What the model wrote is shown as plain text and
 * nothing more.
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
        <v-chip
          size="small"
          variant="outlined"
          :color="finding.status === 'ongoing' ? undefined : 'primary'"
          data-test="finding-status"
        >
          {{ finding.status === 'ongoing' ? 'Still open' : 'New' }}
        </v-chip>
        <h3 class="text-title-medium finding__title" data-test="finding-title">
          {{ finding.title }}
        </h3>
      </div>
      <p v-if="finding.detail" class="text-body-large finding__detail" data-test="finding-detail">
        {{ finding.detail }}
      </p>
      <p v-if="finding.action" class="text-body-large finding__action" data-test="finding-action">
        <v-icon :icon="Lightbulb" size="18" aria-hidden="true" />
        <span><strong>What to do:</strong> {{ finding.action }}</span>
      </p>
      <p class="text-body-small text-medium-emphasis finding__meta" data-test="finding-meta">
        <span class="finding__sure" data-test="finding-confidence">
          <v-icon :icon="CONFIDENCE[finding.confidence].icon" size="14" aria-hidden="true" />
          {{ CONFIDENCE[finding.confidence].label }}
        </span>
        <span data-test="finding-history">{{ reportedFor(finding) }}</span>
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

.finding__action {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-primary), 0.1);
  overflow-wrap: anywhere;
}

.finding__action .v-icon {
  margin-top: 0.2rem;
  color: rgb(var(--v-theme-primary));
}

.finding__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  margin: 0.625rem 0 0;
}

.finding__sure {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.finding__cites {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
