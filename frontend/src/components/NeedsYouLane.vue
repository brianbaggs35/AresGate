<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'
import { computed } from 'vue'

import type { Incident } from '@/api/incidents'
import IncidentCard from '@/components/IncidentCard.vue'
import { formatCount } from '@/format'
import type { Judged } from '@/verdicts'

/**
 * The incidents that most need a decision, under the status hero, so the page that says
 * something needs you is also the page where you answer: each is a card that can be judged where
 * it is. Whoever shows the lane says what was done with a verdict (`judged`), and sends it only
 * what needs deciding: when there is nothing, the lane is not shown at all.
 */
const props = defineProps<{
  incidents: readonly Incident[]
  /** How many there are in all, which is more than are shown when the lane is only the first few. */
  total: number
}>()
defineEmits<{ judged: [Judged] }>()

const more = computed(() => props.total > props.incidents.length)
</script>

<template>
  <section class="lane" aria-labelledby="needs-you-title" data-test="needs-you">
    <header class="lane__head">
      <div>
        <h2 id="needs-you-title" class="text-title-large">Needs you</h2>
        <p class="text-body-medium text-medium-emphasis" data-test="needs-you-description">
          {{ formatCount(total) }} open {{ total === 1 ? 'incident' : 'incidents' }}, the most
          serious and surest first. Say what you think of one and AresGate remembers it.
        </p>
      </div>
      <v-btn
        variant="text"
        :append-icon="ArrowRight"
        :to="{ name: 'incidents' }"
        data-test="needs-you-all"
      >
        {{ more ? `See all ${formatCount(total)}` : 'Open Incidents' }}
      </v-btn>
    </header>
    <ul class="lane__list">
      <li v-for="(incident, index) in incidents" :key="incident.id" :style="{ '--rank': index }">
        <IncidentCard :incident="incident" @judged="$emit('judged', $event)" />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.lane {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.lane__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.lane__head h2,
.lane__head p {
  margin: 0;
}

.lane__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* Each card comes in a moment after the one above it, so the eye is led down the list. */
.lane__list > li {
  animation: lane-rise 420ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
  animation-delay: calc(var(--rank, 0) * 70ms + 120ms);
}

@keyframes lane-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
}

/* On a phone three tall cards would push everything else far down the page, so they sit side by
   side and are swiped through, with the next one showing at the edge to say so. The row goes to
   the screen's edges (the page's 16px of space is undone and given back as padding), and one
   card on its own takes the whole width. */
@media (max-width: 599.98px) {
  .lane__list {
    flex-direction: row;
    margin-inline: -16px;
    padding: 2px 16px 0.5rem;
    overflow-x: auto;
    scroll-padding-inline: 16px;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;
  }

  .lane__list > li {
    flex: 0 0 min(88%, 22rem);
    scroll-snap-align: start;
  }

  .lane__list > li:only-child {
    flex-basis: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .lane__list > li {
    animation: none;
  }
}
</style>
