<script setup lang="ts">
import { Check, Crosshair, Minus, Tag } from '@lucide/vue'
import { computed } from 'vue'

import type { Insights } from '@/api/incidents'
import CountedBars from '@/components/CountedBars.vue'
import SectionCard from '@/components/SectionCard.vue'
import { APP_ICON, HOST_ICON, namedByKind, namedLook } from '@/evidence'
import { formatCount } from '@/format'

/**
 * What the connected programs, between them, knew of the incident, drawn so it is seen at a
 * glance: who reported how much and what each added (the more programs are connected, the more
 * there is here), the ATT&CK techniques its alerts were matched to, the machines and applications
 * they were about and what they named. An alert two programs reported is counted once.
 */
const props = defineProps<{ insights: Insights }>()

const techniques = computed(() =>
  props.insights.techniques.map((item) => ({
    label: `${item.id} ${item.technique}`,
    hint: item.tactic || undefined,
    count: item.count,
  })),
)
const hosts = computed(() =>
  props.insights.hosts.map(({ value, count }) => ({ label: value, count })),
)
const apps = computed(() =>
  props.insights.apps.map(({ value, count }) => ({ label: value, count })),
)
const named = computed(() =>
  namedByKind(props.insights.named).map(([kind, items]) => ({
    kind,
    ...namedLook(kind),
    items: items.map(({ value, count }) => ({ label: value, count })),
  })),
)
</script>

<template>
  <SectionCard
    title="What the programs saw"
    description="What each connected program told us beyond the basics, added up once for every alert. The more programs are connected, the more there is."
    data-test="insights-card"
  >
    <ul class="insights__programs" data-test="insight-programs">
      <li v-for="program in insights.programs" :key="program.source" class="insights__program">
        <div class="insights__who">
          <h3 class="text-title-medium" data-test="insight-program-name">
            {{ program.source_name }}
          </h3>
          <span class="text-body-medium text-medium-emphasis tabular-nums">
            {{ formatCount(program.reports) }}
            {{ program.reports === 1 ? 'alert' : 'alerts' }}
          </span>
        </div>
        <ul v-if="program.adds.length" class="insights__adds" data-test="insight-adds">
          <li v-for="add in program.adds" :key="add" class="text-body-medium">
            <v-icon :icon="Check" size="16" color="success" aria-hidden="true" />
            {{ add }}
          </li>
        </ul>
        <p v-else class="text-body-medium text-medium-emphasis" data-test="insight-basics">
          <v-icon :icon="Minus" size="16" aria-hidden="true" />
          Only the basics: what, where and when.
        </p>
      </li>
    </ul>

    <div class="insights__grid">
      <section v-if="techniques.length" data-test="insight-techniques">
        <h3 class="text-title-medium insights__heading">
          <v-icon :icon="Crosshair" size="20" aria-hidden="true" /> MITRE ATT&amp;CK techniques
        </h3>
        <CountedBars :items="techniques" />
      </section>

      <section v-if="hosts.length" data-test="insight-hosts">
        <h3 class="text-title-medium insights__heading">
          <v-icon :icon="HOST_ICON" size="20" aria-hidden="true" /> Machines it was about
        </h3>
        <CountedBars :items="hosts" />
      </section>

      <section v-if="apps.length" data-test="insight-apps">
        <h3 class="text-title-medium insights__heading">
          <v-icon :icon="APP_ICON" size="20" aria-hidden="true" /> Applications
        </h3>
        <CountedBars :items="apps" />
      </section>

      <section v-for="group in named" :key="group.kind" :data-test="`insight-named-${group.kind}`">
        <h3 class="text-title-medium insights__heading">
          <v-icon :icon="group.icon" size="20" aria-hidden="true" /> {{ group.plural }}
        </h3>
        <CountedBars :items="group.items" />
      </section>

      <section v-if="insights.tags.length" data-test="insight-tags">
        <h3 class="text-title-medium insights__heading">
          <v-icon :icon="Tag" size="20" aria-hidden="true" /> Groups and categories
        </h3>
        <div class="insights__tags">
          <v-chip v-for="tag in insights.tags" :key="tag.value" variant="outlined" size="small">
            {{ tag.value }}
            <span class="insights__tag-count tabular-nums">{{ formatCount(tag.count) }}</span>
          </v-chip>
        </div>
      </section>
    </div>
  </SectionCard>
</template>

<style scoped>
.insights__programs {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
  margin: 0 0 1.5rem;
  padding: 0;
  list-style: none;
}

.insights__program {
  padding: 0.875rem 1rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}

.insights__who {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.insights__who h3,
.insights__program p {
  margin: 0;
}

.insights__adds {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.insights__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.75rem;
}

.insights__heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.75rem;
}

.insights__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.insights__tag-count {
  margin-left: 0.5rem;
  opacity: 0.75;
}

@container (min-width: 900px) {
  .insights__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1.75rem 2.5rem;
  }
}
</style>
