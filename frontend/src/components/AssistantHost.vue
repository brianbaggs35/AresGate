<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

import AssistantPanel from '@/components/AssistantPanel.vue'
import { useAssistantStore } from '@/stores/assistant'

/**
 * Where the assistant's panel is put: in a drawer at the side of a wide screen, which pushes the
 * page aside where there is room for both and covers it where there is not, and in a sheet that
 * rises from the bottom of a phone, with a button to close it, so the bar of places below it is
 * never lost. On the Assistant page itself there is nothing to open: it is the conversation.
 */
const assistant = useAssistantStore()
const route = useRoute()
const { xs: phone, lgAndUp: wide } = useDisplay()

const onItsOwnPage = computed(() => route.name === 'assistant' || route.name === 'assistant-chat')

// Going to the page for the conversation puts the panel away.
watch(onItsOwnPage, (own) => {
  if (own) assistant.hide()
})
</script>

<template>
  <v-bottom-sheet
    v-if="phone"
    v-model="assistant.open"
    aria-label="Assistant"
    data-test="assistant-sheet"
  >
    <v-card class="host__sheet">
      <AssistantPanel />
    </v-card>
  </v-bottom-sheet>
  <v-navigation-drawer
    v-else
    v-model="assistant.open"
    location="end"
    :width="420"
    :temporary="!wide"
    aria-label="Assistant"
    data-test="assistant-drawer"
  >
    <AssistantPanel v-if="assistant.open" />
  </v-navigation-drawer>
</template>

<style scoped>
/* The sheet is as tall as the visible screen allows, which shrinks when a keyboard is up, so the
   box to type in stays above it. */
.host__sheet {
  height: min(85vh, 40rem);
  height: min(85dvh, 40rem);
  border-end-start-radius: 0;
  border-end-end-radius: 0;
}
</style>
