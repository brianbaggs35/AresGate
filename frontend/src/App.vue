<script setup lang="ts">
import { watch } from 'vue'
import { useDisplay, useTheme } from 'vuetify'

import AppBar from '@/components/AppBar.vue'
import AppDrawer from '@/components/AppDrawer.vue'
import BottomNavigation from '@/components/BottomNavigation.vue'
import { useThemeStore } from '@/stores/theme'

const theme = useTheme()
const themeStore = useThemeStore()
const { xs: phone } = useDisplay()

watch(
  () => themeStore.preference,
  (preference) => theme.change(preference),
  { immediate: true },
)

/** A link to #main-content would change the address, so it moves focus there instead. */
function skipToContent() {
  document.getElementById('main-content')?.focus()
}
</script>

<template>
  <v-app>
    <a href="#main-content" class="skip-link" data-test="skip-link" @click.prevent="skipToContent">
      Skip to the page
    </a>
    <AppDrawer v-if="!phone" />
    <AppBar />
    <v-main id="main-content" tabindex="-1">
      <router-view />
    </v-main>
    <BottomNavigation v-if="phone" />
  </v-app>
</template>
