<script setup lang="ts">
import { ChevronsLeft, ChevronsRight } from '@lucide/vue'
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

import AppLogo from '@/components/AppLogo.vue'
import NavIcon from '@/components/NavIcon.vue'
import { navGroups } from '@/navigation'
import { useNavigationStore } from '@/stores/navigation'

const display = useDisplay()
const store = useNavigationStore()

// A tablet starts with just the icons, to leave the page room. Whatever a person picks after
// that is remembered, and applies on every screen.
const rail = computed(() => (store.width ? store.width === 'rail' : display.sm.value))
</script>

<template>
  <v-navigation-drawer
    permanent
    :rail="rail"
    :width="264"
    :rail-width="72"
    border="e"
    aria-label="Main"
    class="app-drawer"
  >
    <div class="app-drawer__brand">
      <router-link to="/" class="text-decoration-none text-high-emphasis" aria-label="AresGate">
        <AppLogo :compact="rail" />
      </router-link>
    </div>

    <!-- The list's own role (list) wants list items, and these are links, so it steps aside. -->
    <v-list nav role="presentation" tabindex="-1" class="px-3 app-drawer__list">
      <div
        v-for="group in navGroups()"
        :key="group.key"
        role="group"
        :aria-labelledby="`nav-heading-${group.key}`"
        class="app-drawer__group"
        :data-test="`nav-group-${group.key}`"
      >
        <!-- A rail has no room for the words, so a line divides the groups and a screen reader
             still hears each heading. -->
        <p
          :id="`nav-heading-${group.key}`"
          class="app-drawer__heading text-label-medium"
          :class="{ 'sr-only': rail }"
          data-test="nav-heading"
        >
          {{ group.title }}
        </p>
        <v-list-item
          v-for="item in group.items"
          :key="item.route"
          :to="{ name: item.route }"
          :title="item.title"
          rounded="lg"
          color="primary"
          :tabindex="0"
          :data-test="`nav-${item.route}`"
        >
          <template #prepend>
            <NavIcon :item="item" />
          </template>
          <!-- The link's name is already its title, so a tooltip would only say it twice. -->
          <v-tooltip
            v-if="rail"
            activator="parent"
            location="end"
            :text="item.title"
            aria-hidden="true"
            data-test="menu-tooltip"
          />
        </v-list-item>
      </div>
    </v-list>

    <template #append>
      <div class="app-drawer__footer">
        <v-btn
          :icon="rail ? ChevronsRight : ChevronsLeft"
          variant="text"
          size="small"
          :aria-label="rail ? 'Expand the menu' : 'Collapse the menu'"
          :aria-expanded="!rail"
          data-test="menu-width"
          @click="store.setWidth(rail ? 'full' : 'rail')"
        />
      </div>
    </template>
  </v-navigation-drawer>
</template>

<style scoped>
.app-drawer__group + .app-drawer__group {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.app-drawer__heading {
  margin: 0;
  padding: 0.5rem 1rem 0.25rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  border: 0;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
