<script setup lang="ts">
import { ExternalLink, ShieldAlert } from '@lucide/vue'

import type { CvssSeverity, Vulnerability } from '@/api/incidents'
import { formatDate } from '@/format'

/**
 * The CVEs an incident names, and what the National Vulnerability Database says of each: how
 * severe the vulnerability is by the CVSS score, whether CISA has seen it exploited, what kind of
 * weakness it is and what it is. The score rates the vulnerability, not the attack: a severe CVE
 * that was only probed is a different thing from one that was exploited.
 */
defineProps<{ vulnerabilities: Vulnerability[] }>()

const COLORS: Record<CvssSeverity, string> = {
  NONE: 'default',
  LOW: 'info',
  MEDIUM: 'warning',
  HIGH: 'error',
  CRITICAL: 'error',
}

const WORDS: Record<CvssSeverity, string> = {
  NONE: 'None',
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  CRITICAL: 'Critical',
}

function unsettled(item: Vulnerability): string {
  if (item.state === 'pending') return 'NVD has not been asked about it yet.'
  if (item.state === 'unknown') {
    return 'NVD has no record of it yet, so how severe it is is not known.'
  }
  const status = item.status ? ` (${item.status})` : ''
  return `NVD has not scored it yet${status}.`
}
</script>

<template>
  <div data-test="vulnerabilities">
    <ul class="vulnerabilities__list">
      <li
        v-for="item in vulnerabilities"
        :key="item.id"
        class="vulnerabilities__item"
        :data-test="`vulnerability-${item.id}`"
      >
        <div class="vulnerabilities__head">
          <h3 class="text-title-medium vulnerabilities__id">{{ item.id }}</h3>
          <v-chip
            v-if="item.severity && item.score !== null"
            :color="COLORS[item.severity]"
            size="small"
            variant="tonal"
            data-test="vulnerability-score"
          >
            CVSS {{ item.cvss_version }}: {{ item.score.toFixed(1) }}, {{ WORDS[item.severity] }}
          </v-chip>
          <v-chip
            v-if="item.exploited"
            color="error"
            size="small"
            variant="flat"
            data-test="vulnerability-exploited"
          >
            <v-icon :icon="ShieldAlert" size="16" start aria-hidden="true" />
            Exploited in the wild
          </v-chip>
          <v-chip
            v-if="item.status === 'Rejected'"
            size="small"
            variant="outlined"
            data-test="vulnerability-rejected"
          >
            Rejected by NVD
          </v-chip>
        </div>

        <p
          v-if="item.state !== 'found' || item.score === null"
          class="text-body-medium text-medium-emphasis"
          data-test="vulnerability-unsettled"
        >
          {{ unsettled(item) }}
        </p>
        <p v-if="item.description" class="text-body-medium" data-test="vulnerability-description">
          {{ item.description }}
        </p>

        <dl class="vulnerabilities__facts text-body-medium">
          <template v-if="item.exploited">
            <dt>On CISA's list since</dt>
            <dd data-test="vulnerability-since">
              {{ item.exploited_on ? formatDate(item.exploited_on) : 'a date CISA has not given' }}
            </dd>
            <template v-if="item.required_action">
              <dt>CISA says to</dt>
              <dd data-test="vulnerability-action">
                {{ item.required_action
                }}<template v-if="item.action_due">
                  Due {{ formatDate(item.action_due) }}.</template
                >
              </dd>
            </template>
          </template>
          <template v-if="item.weaknesses.length">
            <dt>Weakness</dt>
            <dd data-test="vulnerability-weaknesses">{{ item.weaknesses.join(', ') }}</dd>
          </template>
          <template v-if="item.vector">
            <dt>Vector</dt>
            <dd class="vulnerabilities__vector" data-test="vulnerability-vector">
              {{ item.vector }}
            </dd>
          </template>
          <template v-if="item.published_at">
            <dt>Published</dt>
            <dd>{{ formatDate(item.published_at.slice(0, 10)) }}</dd>
          </template>
        </dl>

        <a
          class="text-body-medium vulnerabilities__link"
          :href="item.link"
          target="_blank"
          rel="noopener noreferrer"
          data-test="vulnerability-link"
        >
          See it at NVD
          <v-icon :icon="ExternalLink" size="16" aria-hidden="true" />
        </a>
      </li>
    </ul>
    <p class="text-body-small text-medium-emphasis vulnerabilities__notice" data-test="nvd-notice">
      This product uses data from the NVD API but is not endorsed or certified by the NVD.
    </p>
  </div>
</template>

<style scoped>
.vulnerabilities__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.vulnerabilities__item {
  padding: 0.875rem 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.vulnerabilities__item p {
  margin: 0.5rem 0 0;
}

.vulnerabilities__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.vulnerabilities__id {
  margin: 0;
}

.vulnerabilities__facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.25rem 1rem;
  margin: 0.75rem 0 0;
}

.vulnerabilities__facts dt {
  opacity: 0.75;
}

.vulnerabilities__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.vulnerabilities__vector {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8125rem;
}

.vulnerabilities__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.75rem;
}

.vulnerabilities__notice {
  margin: 1rem 0 0;
}
</style>
