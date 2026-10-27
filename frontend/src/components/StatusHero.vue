<script setup lang="ts">
import { CircleCheck, Eye, Plug, Siren } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import type { Posture, PostureState } from '@/dashboard'

/**
 * The first thing on the dashboard: a sentence that says whether anything needs attention, in
 * the biggest type on the page, with a ring and a glow in the color of the answer, and the
 * numbers that back it up underneath (the slot). It is never only a color: each state has its
 * own icon, its own label and its own words. Screen readers hear a change politely, because the
 * page asks again every half minute. The motion (the ring drawing itself, the glow breathing, a
 * slow sweep behind) is decoration that stops for people who ask their system for less of it.
 */
defineProps<{
  posture: Posture
  /** Where to go from here, for the states that have somewhere to go. */
  action?: { label: string; to: RouteLocationRaw }
}>()

const LOOKS: Readonly<
  Record<PostureState, { color: string; icon: NonNullable<IconProps['icon']>; label: string }>
> = {
  attention: { color: 'error', icon: Siren, label: 'Needs you' },
  watch: { color: 'warning', icon: Eye, label: 'Keep an eye on it' },
  calm: { color: 'success', icon: CircleCheck, label: 'All clear' },
  setup: { color: 'info', icon: Plug, label: 'Set up' },
}
</script>

<template>
  <section
    class="hero"
    :style="{ '--tone': `var(--v-theme-${LOOKS[posture.state].color})` }"
    :data-state="posture.state"
    data-test="posture"
  >
    <div class="hero__backdrop" aria-hidden="true">
      <svg class="hero__rings" viewBox="0 0 400 400" focusable="false">
        <circle cx="200" cy="200" r="60" />
        <circle cx="200" cy="200" r="110" />
        <circle cx="200" cy="200" r="160" />
        <circle cx="200" cy="200" r="198" />
        <path d="M200 0V400M0 200H400" />
      </svg>
      <span class="hero__sweep" />
    </div>

    <div class="hero__body">
      <div class="hero__ring" aria-hidden="true">
        <svg viewBox="0 0 100 100" focusable="false">
          <circle class="hero__track" cx="50" cy="50" r="44" />
          <circle class="hero__arc" cx="50" cy="50" r="44" pathLength="100" />
        </svg>
        <v-icon :icon="LOOKS[posture.state].icon" :color="LOOKS[posture.state].color" size="36" />
      </div>
      <output class="hero__text">
        <span class="hero__eyebrow" data-test="posture-eyebrow">{{
          LOOKS[posture.state].label
        }}</span>
        <span class="hero__title" data-test="posture-title">{{ posture.title }}</span>
        <span class="hero__detail text-body-large" data-test="posture-detail">{{
          posture.detail
        }}</span>
      </output>
      <v-btn
        v-if="action"
        class="hero__action"
        variant="flat"
        size="large"
        :color="LOOKS[posture.state].color"
        :to="action.to"
        data-test="posture-action"
      >
        {{ action.label }}
      </v-btn>
    </div>

    <div v-if="$slots.default" class="hero__vitals">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.hero {
  --hairline: rgba(var(--tone), 0.22);

  position: relative;
  overflow: hidden;
  container-type: inline-size;
  border: 1px solid rgba(var(--tone), 0.35);
  border-radius: 20px;
  background:
    radial-gradient(120% 160% at 0% 0%, rgba(var(--tone), 0.16), transparent 60%),
    rgb(var(--v-theme-surface));
  box-shadow: 0 24px 60px -40px rgba(var(--tone), 0.6);
  animation: hero-rise 500ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

/* The ring and the sweep sit behind everything, at the end of the card the words are not. */
.hero__backdrop {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hero__rings {
  position: absolute;
  top: 50%;
  right: -5rem;
  width: 22rem;
  height: 22rem;
  transform: translateY(-50%);
  fill: none;
  stroke: rgb(var(--tone));
  stroke-width: 1;
  opacity: 0.16;
}

.hero__sweep {
  position: absolute;
  top: 50%;
  right: -5rem;
  width: 22rem;
  height: 22rem;
  border-radius: 50%;
  background: conic-gradient(from 0deg, rgba(var(--tone), 0.28), transparent 28%);
  mask-image: radial-gradient(circle, #000 35%, transparent 70%);
  transform: translateY(-50%) rotate(0deg);
  opacity: 0.55;
  animation: hero-sweep 14s linear infinite;
}

.hero[data-state='setup'] .hero__sweep {
  display: none;
}

.hero__body {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 1rem 1.25rem;
  padding: 1.25rem;
}

.hero__ring {
  position: relative;
  display: grid;
  place-items: center;
  width: 4.5rem;
  height: 4.5rem;
}

.hero__ring svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  fill: none;
}

.hero__track {
  stroke: rgba(var(--tone), 0.18);
  stroke-width: 5;
}

.hero__arc {
  stroke: rgb(var(--tone));
  stroke-width: 5;
  stroke-linecap: round;
  stroke-dasharray: 100;
  animation:
    hero-draw 1100ms cubic-bezier(0.2, 0.7, 0.2, 1) both,
    hero-breathe 4s ease-in-out 1100ms infinite;
}

/* A state that needs someone breathes faster, and sends out a ripple, so it is not missed. */
.hero[data-state='attention'] .hero__arc {
  animation:
    hero-draw 1100ms cubic-bezier(0.2, 0.7, 0.2, 1) both,
    hero-breathe 1.8s ease-in-out 1100ms infinite;
}

.hero[data-state='attention'] .hero__ring::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid rgb(var(--tone));
  border-radius: 50%;
  opacity: 0;
  animation: hero-ripple 2.4s ease-out 1100ms infinite;
}

.hero[data-state='setup'] .hero__arc {
  stroke-dasharray: 6 5;
  animation: none;
}

.hero__text {
  display: block;
  min-width: 0;
}

.hero__eyebrow {
  display: block;
  margin-bottom: 0.25rem;
  color: rgb(var(--tone));
  font-size: 0.75rem;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero__title {
  display: block;
  font-size: clamp(1.5rem, 1.1rem + 1.7vw, 2.25rem);
  font-weight: 650;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.hero__detail {
  display: block;
  margin-top: 0.25rem;
  opacity: 0.8;
}

.hero__action {
  grid-column: 1 / -1;
  justify-self: start;
}

.hero__vitals {
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--hairline);
  background: rgba(var(--v-theme-surface), 0.55);
}

/* The vitals are put in by whoever shows the hero, so they are reached through the slot. */
.hero__vitals > :deep(*) {
  border-inline-start: 1px solid var(--hairline);
}

.hero__vitals > :deep(:nth-child(odd)) {
  border-inline-start: 0;
}

.hero__vitals > :deep(:nth-child(n + 3)) {
  border-top: 1px solid var(--hairline);
}

@container (min-width: 640px) {
  .hero__body {
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 1.5rem;
    padding: 1.75rem 2rem;
  }

  .hero__ring {
    width: 5.5rem;
    height: 5.5rem;
  }

  .hero__action {
    grid-column: 3;
    justify-self: end;
  }
}

@container (min-width: 900px) {
  .hero__vitals {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .hero__vitals > :deep(:nth-child(n + 2)) {
    border-inline-start: 1px solid var(--hairline);
  }

  .hero__vitals > :deep(:nth-child(n + 3)) {
    border-top: 0;
  }
}

@keyframes hero-rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}

@keyframes hero-draw {
  from {
    stroke-dashoffset: 100;
  }

  to {
    stroke-dashoffset: 0;
  }
}

@keyframes hero-breathe {
  0%,
  100% {
    filter: drop-shadow(0 0 3px rgba(var(--tone), 0.35));
  }

  50% {
    filter: drop-shadow(0 0 9px rgba(var(--tone), 0.9));
  }
}

@keyframes hero-ripple {
  from {
    opacity: 0.55;
    transform: scale(1);
  }

  to {
    opacity: 0;
    transform: scale(1.45);
  }
}

@keyframes hero-sweep {
  to {
    transform: translateY(-50%) rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero,
  .hero__arc,
  .hero[data-state='attention'] .hero__arc,
  .hero__sweep,
  .hero[data-state='attention'] .hero__ring::after {
    animation: none;
  }
}
</style>
