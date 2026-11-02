<script setup lang="ts">
import { Search } from '@lucide/vue'
import { onBeforeUnmount, ref, watch } from 'vue'

/** How long after the last key the search is applied, so typing a name is not searching for it
 * letter by letter. */
const PAUSE = 350

/**
 * The search field of the Assets list: words that each have to be in an asset's name, maker,
 * hardware address, an address or the name of a program that lists it. The text is the applied
 * search, which lives in the address of the page; what is typed is applied after a pause, or at
 * once with Enter.
 */
const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [text: string] }>()

const typed = ref(props.modelValue)
let timer: ReturnType<typeof setTimeout> | undefined

// A search that arrives from outside (the back button, a link, "Clear filters") is what is in
// the box. One this field applied itself comes back as the same text and changes nothing.
watch(
  () => props.modelValue,
  (text) => {
    if (text !== typed.value.trim()) typed.value = text
  },
)

function apply(text: string) {
  clearTimeout(timer)
  timer = undefined
  if (text.trim() !== props.modelValue) emit('update:modelValue', text.trim())
}

function type(text: string | null) {
  typed.value = text ?? ''
  clearTimeout(timer)
  timer = setTimeout(() => {
    apply(typed.value)
  }, PAUSE)
}

const field = ref<{ focus: () => void } | null>(null)
defineExpose({ focus: () => field.value?.focus() })

onBeforeUnmount(() => {
  clearTimeout(timer)
})
</script>

<template>
  <v-text-field
    ref="field"
    :model-value="typed"
    type="search"
    label="Search assets"
    placeholder="Name, address, maker or hardware address"
    :prepend-inner-icon="Search"
    clearable
    hide-details
    autocomplete="off"
    spellcheck="false"
    enterkeyhint="search"
    class="asset-search"
    data-test="asset-search"
    @update:model-value="type"
    @keydown.enter="apply(typed)"
    @click:clear="apply('')"
  />
</template>
