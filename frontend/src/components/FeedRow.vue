<script setup lang="ts">
import type { Feed, Interface, Placement } from '@/api/interfaces'
import FeedMove from '@/components/FeedMove.vue'
import { formatAgo, formatDateTime } from '@/format'
import { feedName } from '@/interfaces'

/**
 * One feed: where it comes from, what it is called there, when it last reported, and the control
 * that moves it. A feed that hasn't reported for a while is said so in words.
 */
withDefaults(
  defineProps<{
    feed: Feed
    interfaces: readonly Interface[]
    disabled?: boolean
    canCreate?: boolean
  }>(),
  { disabled: false, canCreate: true },
)
defineEmits<{ move: [Placement]; create: [] }>()
</script>

<template>
  <div class="feed" data-test="feed">
    <div class="feed__what">
      <p class="text-title-small feed__name" data-test="feed-name">{{ feedName(feed) }}</p>
      <p class="text-body-medium text-medium-emphasis feed__detail">
        <span v-if="feed.detail" data-test="feed-detail">{{ feed.detail }} · </span>
        <span data-test="feed-connection">{{ feed.connection_label }}</span>
        ·
        <time
          :datetime="feed.last_seen_at"
          :title="formatDateTime(feed.last_seen_at)"
          data-test="feed-seen"
          >Last reported {{ formatAgo(feed.last_seen_at) }}</time
        >
      </p>
    </div>
    <FeedMove
      :feed="feed"
      :interfaces="interfaces"
      :disabled="disabled"
      :can-create="canCreate"
      @move="$emit('move', $event)"
      @create="$emit('create')"
    />
  </div>
</template>

<style scoped>
.feed {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  padding: 0.75rem 0;
}

.feed__what {
  flex: 1 1 14rem;
  min-width: 0;
}

.feed__name,
.feed__detail {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
