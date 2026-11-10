<script setup lang="ts">
import { RefreshCw } from '@lucide/vue'
import { computed } from 'vue'

import type { Edge, Run, Step } from '@/api/agents'
import { MAX_ROUNDS, nodeState, shape, type NodeState } from '@/agents'

/**
 * The graph an agent runs, drawn as it is run: each step lit when it is going, ticked when it is
 * done, and the loop back to looking again counted by round. It is the graph LangGraph describes
 * for the run (the arrows come from the API), so a change to what an agent does changes the
 * picture with no change here. It reads left to right on a desktop and top to bottom on a phone.
 */
const props = defineProps<{
  edges: readonly Edge[]
  /** The run being shown, or none to show the graph at rest. */
  run: Pick<Run, 'status' | 'node' | 'rounds'> | null
  steps: readonly Pick<Step, 'node'>[]
}>()

const SAYS: Readonly<Record<NodeState, string>> = {
  waiting: 'Waiting',
  active: 'Working on it',
  done: 'Done',
  skipped: 'Not reached',
}

const drawn = computed(() => shape(props.edges))
const nodes = computed(() =>
  drawn.value.nodes.map((node) => {
    const state = nodeState(node.id, props.run, props.steps)
    return {
      ...node,
      state,
      says: SAYS[state],
      count: props.steps.filter((step) => step.node === node.id).length,
    }
  }),
)
/** Which link is carrying the run now: the one into the step that is going. */
const flowingInto = computed(() => nodes.value.findIndex((node) => node.state === 'active'))
const rounds = computed(() => Math.min(props.run?.rounds ?? 0, MAX_ROUNDS))
</script>

<template>
  <section class="graph" aria-label="How the agent works through a run" data-test="agent-graph">
    <ol class="graph__nodes">
      <template v-for="(node, at) in nodes" :key="node.id">
        <li
          class="node"
          :class="`node--${node.state}`"
          :aria-current="node.state === 'active' ? 'step' : undefined"
          :data-state="node.state"
          data-test="graph-node"
        >
          <span class="node__ring">
            <v-icon :icon="node.icon" size="22" aria-hidden="true" />
          </span>
          <span class="node__text">
            <span class="text-title-small" data-test="graph-label">{{ node.label }}</span>
            <span class="text-body-small text-medium-emphasis node__hint">{{ node.hint }}</span>
            <span class="text-label-small node__state" data-test="graph-state">
              {{ node.says }}<template v-if="node.count > 1"> · {{ node.count }} steps</template>
            </span>
          </span>
        </li>
        <li
          v-if="at < nodes.length - 1"
          class="link"
          :class="{ 'link--live': flowingInto === at + 1 }"
          aria-hidden="true"
        />
      </template>
    </ol>

    <p v-if="drawn.loops.length" class="loop text-body-small" data-test="graph-loop">
      <v-icon :icon="RefreshCw" size="16" aria-hidden="true" />
      <span>Looks again when the AI asks for more, up to {{ MAX_ROUNDS }} rounds.</span>
      <span class="loop__rounds" role="img" :aria-label="`Round ${rounds} of ${MAX_ROUNDS}`">
        <span
          v-for="round in MAX_ROUNDS"
          :key="round"
          class="loop__dot"
          :class="{ 'loop__dot--on': round <= rounds }"
          data-test="graph-round"
        />
      </span>
    </p>
  </section>
</template>

<style scoped>
.graph {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.graph__nodes {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.node {
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  padding: 0.75rem 0.5rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
  background: rgb(var(--v-theme-surface));
  text-align: center;
  transition:
    border-color 0.25s,
    background-color 0.25s;
}

.node__ring {
  display: grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  transition:
    background-color 0.25s,
    color 0.25s;
}

.node__text {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.node__state {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.node--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}

.node--active .node__ring {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  animation: pulse 1.6s ease-out infinite;
}

.node--active .node__state {
  color: rgb(var(--v-theme-primary));
}

.node--done .node__ring {
  background: rgba(var(--v-theme-success), 0.16);
  color: rgb(var(--v-theme-success));
}

.node--done .node__state {
  color: rgb(var(--v-theme-success));
}

.node--skipped {
  opacity: 0.6;
  border-style: dashed;
}

.link {
  position: relative;
  flex: 0 0 1.75rem;
  align-self: center;
  height: 2px;
  background: rgba(var(--v-theme-on-surface), 0.18);
}

.link--live {
  background: repeating-linear-gradient(
    90deg,
    rgb(var(--v-theme-primary)) 0 6px,
    transparent 6px 12px
  );
  background-size: 12px 2px;
  animation: flow 0.7s linear infinite;
}

.loop {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}

.loop__rounds {
  display: inline-flex;
  gap: 0.25rem;
  margin-left: auto;
}

.loop__dot {
  width: 0.625rem;
  height: 0.625rem;
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.4);
  border-radius: 50%;
}

.loop__dot--on {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary));
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.45);
  }

  100% {
    box-shadow: 0 0 0 0.75rem rgba(var(--v-theme-primary), 0);
  }
}

@keyframes flow {
  to {
    background-position: 12px 0;
  }
}

@media (max-width: 599.98px) {
  .graph__nodes {
    flex-direction: column;
  }

  .node {
    flex-direction: row;
    gap: 0.875rem;
    padding: 0.625rem 0.875rem;
    text-align: left;
  }

  .node__ring {
    flex: none;
  }

  .link {
    flex: 0 0 1.25rem;
    width: 2px;
    height: auto;
    margin-left: 1.75rem;
    align-self: flex-start;
  }

  .link--live {
    background: repeating-linear-gradient(
      180deg,
      rgb(var(--v-theme-primary)) 0 6px,
      transparent 6px 12px
    );
    background-size: 2px 12px;
    animation-name: flow-down;
  }

  @keyframes flow-down {
    to {
      background-position: 0 12px;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .node--active .node__ring,
  .link--live {
    animation: none;
  }
}
</style>
