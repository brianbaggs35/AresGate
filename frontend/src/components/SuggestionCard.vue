<script setup lang="ts">
import { Check, EyeOff, Pencil } from '@lucide/vue'
import { computed } from 'vue'

import type { Feed, Suggestion } from '@/api/interfaces'
import { feedName, roleInfo } from '@/interfaces'

/**
 * A guess at where some feeds belong, with the reason for it, for the owner to decide: confirm it,
 * change it first, or set the feeds aside (a guess that joins an interface that is already there cannot be changed, only moved feed by feed). Nothing happens until one of them is pressed. It names
 * the interface the feeds would join, and says when that interface is yet to be made.
 */
const props = defineProps<{
  suggestion: Suggestion
  /** The feeds it names, as they are listed now. */
  feeds: readonly Feed[]
  /** Another change is under way. */
  busy?: boolean
}>()
defineEmits<{ confirm: []; change: []; ignore: [] }>()

const role = computed(() => roleInfo(props.suggestion.role))
</script>

<template>
  <v-card class="suggestion" data-test="suggestion">
    <div class="suggestion__main">
      <div class="suggestion__title">
        <h3 class="text-title-medium" data-test="suggestion-name">{{ suggestion.name }}</h3>
        <v-chip :prepend-icon="role.icon" size="small" variant="tonal">{{ role.label }}</v-chip>
        <v-chip v-if="suggestion.interface_id === null" size="small" variant="outlined">
          New
        </v-chip>
      </div>
      <p class="text-body-large suggestion__reason" data-test="suggestion-reason">
        {{ suggestion.reason }}
      </p>
      <ul class="suggestion__feeds" aria-label="Feeds">
        <li v-for="feed in feeds" :key="feed.id" data-test="suggestion-feed">
          <v-chip size="small" variant="outlined">{{ feedName(feed) }}</v-chip>
        </li>
      </ul>
    </div>
    <div class="suggestion__actions">
      <v-btn
        color="primary"
        variant="flat"
        :prepend-icon="Check"
        :disabled="busy"
        data-test="suggestion-confirm"
        @click="$emit('confirm')"
      >
        Confirm
      </v-btn>
      <v-btn
        v-if="suggestion.interface_id === null"
        variant="tonal"
        :prepend-icon="Pencil"
        :disabled="busy"
        data-test="suggestion-change"
        @click="$emit('change')"
      >
        Change
      </v-btn>
      <v-btn
        variant="text"
        :prepend-icon="EyeOff"
        :disabled="busy"
        data-test="suggestion-ignore"
        @click="$emit('ignore')"
      >
        Ignore
      </v-btn>
    </div>
  </v-card>
</template>

<style scoped>
.suggestion {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
}

.suggestion__main {
  flex: 1 1 18rem;
  min-width: 0;
}

.suggestion__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.suggestion__title h3 {
  margin: 0;
  overflow-wrap: anywhere;
}

.suggestion__reason {
  margin: 0.25rem 0 0.5rem;
}

.suggestion__feeds {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.suggestion__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
