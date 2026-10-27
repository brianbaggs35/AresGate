<script setup lang="ts">
import { Check, Copy, X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref } from 'vue'

/** How long the button shows that it copied, or that it could not, before it is itself again. */
const SHOWN_MS = 2000

/**
 * An icon button that puts a value on the clipboard. It says what it copied, to the eye by
 * its icon and to a screen reader in words, and says so too when the browser would not (a page
 * that is not secure has no clipboard).
 */
const props = defineProps<{
  /** What goes on the clipboard. */
  text: string
  /** What it is, in a word or two, for the button's name: "Copy From". */
  label: string
}>()

const state = ref<'idle' | 'copied' | 'failed'>('idle')
let timer: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    state.value = 'copied'
  } catch {
    state.value = 'failed'
  }
  clearTimeout(timer)
  timer = setTimeout(() => {
    state.value = 'idle'
  }, SHOWN_MS)
}

const icon = computed(() => ({ idle: Copy, copied: Check, failed: X })[state.value])
const said = computed(() => ({ idle: '', copied: 'Copied', failed: "Couldn't copy" })[state.value])

onBeforeUnmount(() => {
  clearTimeout(timer)
})
</script>

<template>
  <span class="copy">
    <v-btn
      icon
      variant="text"
      size="small"
      density="comfortable"
      :color="state === 'failed' ? 'error' : state === 'copied' ? 'success' : undefined"
      :aria-label="`Copy ${label}`"
      :title="`Copy ${label}`"
      data-test="copy"
      @click="copy"
    >
      <v-icon :icon="icon" size="18" />
    </v-btn>
    <output class="copy__said" data-test="copy-said">{{ said }}</output>
  </span>
</template>

<style scoped>
.copy {
  display: inline-flex;
}

/* Said to a screen reader as it changes; the icon says it to the eye. */
.copy__said {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
