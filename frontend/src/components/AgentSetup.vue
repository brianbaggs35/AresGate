<script setup lang="ts">
import { CircleAlert, CircleCheck } from '@lucide/vue'
import { useId } from 'vue'

import type { Template } from '@/api/agents'

/**
 * What a kind of agent needs in order to be useful, and whether each is there: a check with a
 * word as well as an icon, and, for what is missing, what to do and a link to where. Under it,
 * the steps to set the kind up from the start, folded away once someone knows them.
 */
defineProps<{ template: Template }>()

const titleId = useId()
</script>

<template>
  <section class="setup" :aria-labelledby="titleId" data-test="agent-setup">
    <h3 :id="titleId" class="text-title-small" data-test="setup-title">
      {{ template.ready ? 'Everything it needs is set up' : 'It needs a little setup first' }}
    </h3>

    <ul v-if="template.checks.length" class="setup__checks">
      <li
        v-for="check in template.checks"
        :key="check.key"
        class="setup__check"
        data-test="setup-check"
      >
        <v-icon
          :icon="check.ok ? CircleCheck : CircleAlert"
          :color="check.ok ? 'success' : 'warning'"
          size="20"
          aria-hidden="true"
        />
        <div>
          <span class="text-body-medium">{{ check.text }}</span>
          <span class="sr-only">{{ check.ok ? ': ready' : ': missing' }}</span>
          <p v-if="!check.ok" class="text-body-small text-medium-emphasis setup__fix">
            {{ check.fix }}
            <RouterLink :to="check.link" data-test="setup-link">Set it up</RouterLink>
          </p>
        </div>
      </li>
    </ul>

    <details v-if="template.setup.length" class="setup__steps" data-test="setup-steps">
      <summary class="text-label-large">How to set it up</summary>
      <ol class="text-body-medium">
        <li v-for="(step, at) in template.setup" :key="at" data-test="setup-step">{{ step }}</li>
      </ol>
    </details>
  </section>
</template>

<style scoped>
.setup {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.setup h3 {
  margin: 0;
}

.setup__checks {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.setup__check {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
}

.setup__fix {
  margin: 0.125rem 0 0;
}

.setup__steps summary {
  cursor: pointer;
}

.setup__steps ol {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}

.setup__steps li + li {
  margin-top: 0.25rem;
}
</style>
