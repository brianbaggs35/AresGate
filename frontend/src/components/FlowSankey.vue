<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Flow, FlowNode } from '@/api/flow'
import ChartFrame from '@/charts/ChartFrame.vue'
import { useElementWidth } from '@/charts/interaction'
import type { ChartTableData, LegendItem } from '@/charts/types'
import { formatCount } from '@/format'
import {
  COLUMN_TITLES,
  COLUMNS,
  isOthers,
  layoutFlow,
  nodeLabel,
  nodeSummary,
  refusedShare,
  related,
} from '@/flow'

/**
 * Where the traffic goes, drawn as three columns joined by bands as thick as the connections they
 * carry: who connected, to which service, and what they reached. The part of a band that the
 * firewall refused is drawn along its top edge in its own color, and every block is also named
 * with how many were refused, so the color is never the only thing saying so. Hovering or
 * focusing a block lights its paths; pressing it (a click, Enter or Space) picks it, which the page
 * answers with the block's details. The same numbers are a table, which `ChartFrame` offers.
 */
const props = defineProps<{
  flow: Flow
  /** The id of the block that is picked, or null. */
  selected: string | null
  loading?: boolean
}>()
const emit = defineEmits<{ select: [id: string | null] }>()

const plot = ref<HTMLElement | null>(null)
const width = useElementWidth(plot, 640)
const hidden = ref<string[]>([])
const hovered = ref<string | null>(null)

/** A tall block is only as many pixels as its share; the picture is as tall as the busiest
 * column needs, so a few blocks aren't stretched thin and many are not squeezed. */
const height = computed(() => {
  const most = Math.max(
    ...COLUMNS.map((column) => props.flow.nodes.filter((node) => node.column === column).length),
  )
  return Math.max(220, most * 42)
})
const layout = computed(() =>
  layoutFlow(props.flow.nodes, props.flow.links, width.value, height.value),
)

const lit = computed(() => {
  const focus = hovered.value ?? props.selected
  return focus ? related(focus, props.flow.links) : null
})
const dim = (ids: readonly string[]) => lit.value !== null && !ids.every((id) => lit.value?.has(id))

/** The length a label can have before it runs into the next column. */
const room = computed(() => Math.max(8, Math.floor((width.value / 3 - 28) / 7)))
function short(text: string): string {
  return text.length > room.value ? `${text.slice(0, room.value - 1)}…` : text
}

const legend = computed<LegendItem[]>(() => [
  { id: 'allowed', label: 'Let through', color: 'var(--chart-1)', shape: 'square' },
  { id: 'blocked', label: 'Refused', color: 'var(--chart-severity-high)', shape: 'square' },
])

const table = computed<ChartTableData>(() => {
  const byId = new Map(props.flow.nodes.map((node) => [node.id, node]))
  return {
    columns: ['From', 'To', 'Connections', 'Refused', 'Share refused'],
    rows: props.flow.links.map((link) => [
      nodeLabel(byId.get(link.source) as FlowNode),
      nodeLabel(byId.get(link.target) as FlowNode),
      formatCount(link.events),
      formatCount(link.blocked),
      `${refusedShare(link.events, link.blocked).toString()}%`,
    ]),
  }
})

function pick(id: string) {
  emit('select', props.selected === id ? null : id)
}

const textX = (column: string, x: number, blockWidth: number) =>
  column === 'destination' ? x - 6 : x + blockWidth + 6
</script>

<template>
  <ChartFrame
    v-model:hidden="hidden"
    title="Where the traffic goes"
    caption="Each band is as thick as the connections it carries. Pick a block to see its details."
    :legend="legend"
    :table="table"
    :empty="flow.nodes.length === 0"
    empty-title="No connections in this window"
    empty-description="Nothing the firewall wrote down matches. Try a longer window or all directions."
    :loading="loading"
  >
    <div ref="plot" class="flow" data-test="flow-chart">
      <div class="flow__heads" aria-hidden="true">
        <span v-for="column in COLUMNS" :key="column" class="text-label-large">
          {{ COLUMN_TITLES[column] }}
        </span>
      </div>
      <svg
        :viewBox="`0 0 ${width} ${height}`"
        :width="width"
        :height="height"
        aria-label="Traffic from who connected, through the service, to what they reached"
        class="flow__svg"
        @mouseleave="hovered = null"
      >
        <g class="flow__bands" aria-hidden="true">
          <g
            v-for="ribbon in layout.ribbons"
            :key="`${ribbon.link.source}>${ribbon.link.target}`"
            :class="{ 'flow__band--dim': dim([ribbon.link.source, ribbon.link.target]) }"
            class="flow__band"
            data-test="flow-band"
          >
            <path v-if="!hidden.includes('allowed')" :d="ribbon.path" class="flow__allowed" />
            <path
              v-if="ribbon.refused && !hidden.includes('blocked')"
              :d="ribbon.refused"
              class="flow__refused"
            />
          </g>
        </g>
        <g
          v-for="placed in layout.nodes"
          :key="placed.node.id"
          class="flow__node"
          :class="{
            'flow__node--picked': selected === placed.node.id,
            'flow__node--dim': dim([placed.node.id]),
          }"
          role="button"
          tabindex="0"
          :aria-pressed="selected === placed.node.id"
          :aria-label="nodeSummary(placed.node)"
          :data-test="`flow-node-${placed.node.id}`"
          @click="pick(placed.node.id)"
          @keydown.enter.prevent="pick(placed.node.id)"
          @keydown.space.prevent="pick(placed.node.id)"
          @mouseenter="hovered = placed.node.id"
          @focus="hovered = placed.node.id"
          @blur="hovered = null"
        >
          <rect
            :x="placed.x"
            :y="placed.y"
            :width="placed.width"
            :height="placed.height"
            rx="2"
            :class="isOthers(placed.node) ? 'flow__block flow__block--others' : 'flow__block'"
          />
          <!-- A larger target than the block, so a thin one can still be pressed. -->
          <rect
            :x="placed.x - 4"
            :y="placed.y - 3"
            :width="placed.width + 8"
            :height="placed.height + 6"
            fill="transparent"
          />
          <text
            :x="textX(placed.node.column, placed.x, placed.width)"
            :y="placed.y + Math.max(placed.height / 2, 9)"
            :text-anchor="placed.node.column === 'destination' ? 'end' : 'start'"
            class="flow__label"
            dominant-baseline="middle"
          >
            {{ short(nodeLabel(placed.node)) }}
            <tspan class="flow__count">{{ formatCount(placed.node.events) }}</tspan>
          </text>
        </g>
      </svg>
    </div>
  </ChartFrame>
</template>

<style scoped>
.flow {
  width: 100%;
}

.flow__heads {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin-bottom: 0.5rem;
  color: rgb(var(--v-theme-on-surface-variant, var(--v-theme-on-surface)));
}

.flow__heads span:nth-child(2) {
  text-align: center;
}

.flow__heads span:nth-child(3) {
  text-align: end;
}

.flow__svg {
  display: block;
  max-width: 100%;
  overflow: visible;
}

.flow__allowed {
  fill: var(--chart-1);
  fill-opacity: 0.32;
  transition: fill-opacity 0.15s;
}

.flow__refused {
  fill: var(--chart-severity-high);
  fill-opacity: 0.75;
  transition: fill-opacity 0.15s;
}

.flow__band--dim .flow__allowed,
.flow__band--dim .flow__refused {
  fill-opacity: 0.06;
}

.flow__block {
  fill: var(--chart-1);
}

.flow__block--others {
  fill: var(--chart-other);
}

.flow__node {
  cursor: pointer;
  outline: none;
  transition: opacity 0.15s;
}

.flow__node--dim {
  opacity: 0.35;
}

.flow__node:focus-visible .flow__block,
.flow__node--picked .flow__block {
  stroke: rgb(var(--v-theme-on-surface));
  stroke-width: 2;
}

.flow__label {
  font-size: 0.75rem;
  fill: rgb(var(--v-theme-on-surface));
  paint-order: stroke;
  stroke: rgb(var(--v-theme-surface));
  stroke-width: 3px;
  stroke-linejoin: round;
}

.flow__count {
  fill: rgb(var(--v-theme-on-surface-variant, var(--v-theme-on-surface)));
  font-variant-numeric: tabular-nums;
}

@media (prefers-reduced-motion: reduce) {
  .flow__allowed,
  .flow__refused,
  .flow__node {
    transition: none;
  }
}
</style>
