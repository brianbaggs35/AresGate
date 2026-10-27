<script setup lang="ts">
import { CircleCheck, Eye, Plug, Siren } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import HeroSurface from '@/components/HeroSurface.vue'
import type { Posture, PostureState } from '@/dashboard'

/**
 * The first thing on the dashboard: a sentence that says whether anything needs attention, in
 * the biggest type on the page, with the numbers that back it up underneath (the slot). It is
 * never only a color: each state has its own icon, its own label and its own words, and a state
 * that needs someone breathes faster and sends out a ripple, so it is not missed.
 */
defineProps<{
  posture: Posture
  /** Where to go from here, for the states that have somewhere to go. */
  action?: { label: string; to: RouteLocationRaw }
}>()

const LOOKS: Readonly<
  Record<
    PostureState,
    {
      color: string
      icon: NonNullable<IconProps['icon']>
      label: string
      mood: 'calm' | 'urgent' | 'idle'
    }
  >
> = {
  attention: { color: 'error', icon: Siren, label: 'Needs you', mood: 'urgent' },
  watch: { color: 'warning', icon: Eye, label: 'Keep an eye on it', mood: 'calm' },
  calm: { color: 'success', icon: CircleCheck, label: 'All clear', mood: 'calm' },
  setup: { color: 'info', icon: Plug, label: 'Set up', mood: 'idle' },
}
</script>

<template>
  <HeroSurface
    test-id="posture"
    :data-state="posture.state"
    :tone="LOOKS[posture.state].color"
    :icon="LOOKS[posture.state].icon"
    :eyebrow="LOOKS[posture.state].label"
    :title="posture.title"
    :detail="posture.detail"
    :mood="LOOKS[posture.state].mood"
  >
    <template v-if="action" #action>
      <v-btn
        variant="flat"
        size="large"
        :color="LOOKS[posture.state].color"
        :to="action.to"
        data-test="posture-action"
      >
        {{ action.label }}
      </v-btn>
    </template>
    <template v-if="$slots.default" #default>
      <slot />
    </template>
  </HeroSurface>
</template>
