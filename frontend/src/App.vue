<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay, useTheme } from 'vuetify'

import AppBar from '@/components/AppBar.vue'
import AppDrawer from '@/components/AppDrawer.vue'
import BottomNavigation from '@/components/BottomNavigation.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import StartupError from '@/components/StartupError.vue'
import { usePaletteStore } from '@/stores/palette'
import { useSessionStore } from '@/stores/session'
import { useThemeStore } from '@/stores/theme'

const theme = useTheme()
const themeStore = useThemeStore()
const session = useSessionStore()
const palette = usePaletteStore()
const route = useRoute()
const router = useRouter()
const { xs: phone } = useDisplay()

watch(
  () => themeStore.preference,
  (preference) => theme.change(preference),
  { immediate: true },
)

// The menu and bars are for someone who is signed in. Setting up and signing in stand alone.
const chrome = computed(() => session.signedIn && !route.meta.public)

// The palette is for someone who is signed in, so signing out puts it away.
watch(chrome, (shown) => {
  if (!shown) palette.open = false
})

/** Ctrl or ⌘ and K opens the palette from anywhere, and closes it again. */
function paletteShortcut(event: KeyboardEvent) {
  if (chrome.value && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    palette.toggle()
  }
}

onMounted(() => {
  window.addEventListener('keydown', paletteShortcut)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', paletteShortcut)
})

// A sign-in that ended while the page was open: back to the sign-in page, and on from there.
watch(
  () => session.expired,
  (expired) => {
    if (expired) void router.replace({ name: 'sign-in', query: { next: route.fullPath } })
  },
)

const retrying = ref(false)

/** Asks the API again, then looks at the page that was asked for as if for the first time. */
async function retry() {
  retrying.value = true
  try {
    await session.restore()
    await router.replace({ path: route.path, query: route.query, hash: route.hash, force: true })
  } finally {
    retrying.value = false
  }
}

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
    <template v-if="chrome">
      <AppDrawer v-if="!phone" />
      <AppBar />
      <CommandPalette v-model="palette.open" />
    </template>
    <v-main id="main-content" tabindex="-1">
      <StartupError v-if="session.error" :message="session.error" :busy="retrying" @retry="retry" />
      <router-view v-else />
    </v-main>
    <BottomNavigation v-if="chrome && phone" />
  </v-app>
</template>
