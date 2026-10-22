<script setup lang="ts">
import { computed } from 'vue'
import { encode } from 'uqr'

const props = defineProps<{ text: string; label: string }>()

/** The white margin a scanner needs around the code, in modules, as the QR standard asks. */
const QUIET_ZONE = 4

const matrix = computed(() => encode(props.text, { ecc: 'M', border: 0 }))
const size = computed(() => matrix.value.size + 2 * QUIET_ZONE)

/** The dark squares as one path, a run of them to each stroke. */
const dark = computed(() =>
  matrix.value.data
    .flatMap((row, y) => {
      const runs: string[] = []
      for (let x = 0; x < row.length; x++) {
        if (!row[x]) continue
        const start = x
        while (row[x + 1]) x++
        runs.push(`M${start + QUIET_ZONE} ${y + QUIET_ZONE}h${x - start + 1}v1h${start - x - 1}z`)
      }
      return runs
    })
    .join(''),
)
</script>

<template>
  <!-- Black on white whatever the theme, which is what scanners read. -->
  <svg
    class="qr-code"
    role="img"
    :aria-label="label"
    :viewBox="`0 0 ${size} ${size}`"
    shape-rendering="crispEdges"
  >
    <rect :width="size" :height="size" fill="#fff" />
    <path :d="dark" fill="#000" />
  </svg>
</template>

<style scoped>
.qr-code {
  display: block;
  width: 12rem;
  max-width: 100%;
  height: auto;
  border-radius: 0.5rem;
}
</style>
