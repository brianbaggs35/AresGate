<script setup lang="ts">
import { Ellipsis } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { bottomBar, navItems, type NavItem } from '@/navigation'

/**
 * The menu of a phone, along the bottom. Only so many places fit in it, so the rest are behind a
 * "More" button that opens them in a sheet; More is marked as the one that is open while the page
 * is one of the places in it.
 */
const { items = navItems } = defineProps<{ items?: readonly NavItem[] }>()
const { bar, more } = bottomBar(items)
const route = useRoute()
const router = useRouter()

const sheet = ref(false)
/** A place is open when the page belongs to the same top route, whichever of its pages it is. */
const inMore = computed(() =>
  more.some((item) => router.resolve({ name: item.route }).matched[0] === route.matched[0]),
)
</script>

<template>
  <v-bottom-navigation tag="nav" aria-label="Main" grow color="primary" border="t" :elevation="0">
    <v-btn
      v-for="item in bar"
      :key="item.route"
      :to="{ name: item.route }"
      :data-test="`nav-${item.route}`"
    >
      <v-icon :icon="item.icon" />
      <span>{{ item.title }}</span>
    </v-btn>
    <v-btn
      v-if="more.length"
      :active="inMore"
      :aria-current="inMore ? 'true' : undefined"
      aria-haspopup="dialog"
      :aria-expanded="sheet"
      data-test="nav-more"
      @click="sheet = true"
    >
      <v-icon :icon="Ellipsis" />
      <span>More</span>
    </v-btn>
  </v-bottom-navigation>

  <v-bottom-sheet v-if="more.length" v-model="sheet" aria-label="More places">
    <v-card class="more" data-test="more-sheet">
      <v-list nav role="presentation" class="px-3 py-2">
        <v-list-item
          v-for="item in more"
          :key="item.route"
          :to="{ name: item.route }"
          :prepend-icon="item.icon"
          :title="item.title"
          rounded="lg"
          color="primary"
          :data-test="`nav-${item.route}`"
          @click="sheet = false"
        />
      </v-list>
    </v-card>
  </v-bottom-sheet>
</template>

<style scoped>
.more {
  padding-bottom: env(safe-area-inset-bottom);
  border-end-start-radius: 0;
  border-end-end-radius: 0;
}
</style>
