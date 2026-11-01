<script setup lang="ts">
import { computed } from 'vue'

import type { Feed, Interface, Placement } from '@/api/interfaces'
import { feedName, roleInfo } from '@/interfaces'

/**
 * Moves one feed: to any of the interfaces, to the side as not wanted, or back to not placed.
 * It does not move anything itself; whoever shows it hears what was chosen. Choosing a new
 * interface asks for one to be made.
 */
const props = withDefaults(
  defineProps<{
    feed: Feed
    interfaces: readonly Interface[]
    disabled?: boolean
    /** Offers to make a new interface for the feed. */
    canCreate?: boolean
  }>(),
  { disabled: false, canCreate: true },
)
const emit = defineEmits<{ move: [Placement]; create: [] }>()

const SET_ASIDE = 'set-aside'
const NOT_PLACED = 'not-placed'
const NEW = 'new'

const items = computed(() => [
  ...props.interfaces.map((item) => ({
    value: item.id,
    title: item.name,
    props: { subtitle: roleInfo(item.role).label },
  })),
  ...(props.canCreate
    ? [
        {
          value: NEW,
          title: 'A new interface…',
          props: { subtitle: 'Name it and choose its role' },
        },
      ]
    : []),
  { value: SET_ASIDE, title: 'Set aside', props: { subtitle: 'Leave it out of everything' } },
  { value: NOT_PLACED, title: 'Not placed yet', props: { subtitle: 'Decide later' } },
])

/** What the list that opens is called. The select would point it at a label this one doesn't
 * show, so it is named directly. */
const listProps = computed<Record<string, unknown>>(() => ({
  'aria-labelledby': undefined,
  'aria-label': `Places for ${feedName(props.feed)}`,
}))

const current = computed(() => {
  if (props.feed.ignored) return SET_ASIDE
  return props.feed.interface_id ?? NOT_PLACED
})

function choose(value: number | string) {
  if (value === current.value) return
  if (value === NEW) emit('create')
  else if (value === SET_ASIDE) emit('move', { ignored: true })
  else if (value === NOT_PLACED) emit('move', { interface_id: null, ignored: false })
  else emit('move', { interface_id: value as number })
}
</script>

<template>
  <v-select
    :model-value="current"
    :items="items"
    :aria-label="`Where ${feedName(feed)} belongs`"
    :list-props="listProps"
    density="compact"
    variant="outlined"
    hide-details
    :disabled="disabled"
    class="feed-move"
    data-test="feed-move"
    @update:model-value="choose"
  />
</template>

<style scoped>
.feed-move {
  min-width: 13rem;
  max-width: 18rem;
}
</style>
