<script setup lang="ts">
import type { IconProps } from 'vuetify'

/**
 * The first thing on a page that has something to say: a sentence in the biggest type on the page,
 * with a ring and a glow in the color of its answer, and the numbers that back it up underneath
 * (the default slot). The ring is a full circle, or as much of one as `level` says, with an icon
 * or whatever the `center` slot holds inside it. Whoever uses it supplies the words, and makes sure
 * the answer is never only a color: it comes with an icon or a figure, and an eyebrow to name it.
 * Screen readers hear a change politely, because the page asks again every half minute. The
 * motion (the ring drawing itself, the glow breathing, a slow sweep behind) is decoration that
 * stops for people who ask their system for less of it.
 */
withDefaults(
  defineProps<{
    /** A theme color: the color of the answer. */
    tone: string
    /** The small word above the sentence that names what kind of answer it is. */
    eyebrow: string
    title: string
    detail?: string
    /** What goes in the ring, unless the `center` slot is used. */
    icon?: NonNullable<IconProps['icon']>
    /** How much of the ring is drawn, from 0 to 100. */
    level?: number
    /** `urgent` breathes faster and sends out a ripple so that it is not missed, and `idle` is a
     * dashed ring that does nothing. */
    mood?: 'calm' | 'urgent' | 'idle'
    /** What the parts are called to a test: this one, `-eyebrow`, `-title` and `-detail`. */
    testId: string
  }>(),
  { detail: undefined, icon: undefined, level: 100, mood: 'calm' },
)
</script>

<template>
  <section
    class="hero"
    :style="{ '--tone': `var(--v-theme-${tone})` }"
    :data-mood="mood"
    :data-test="testId"
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
          <circle
            class="hero__arc"
            cx="50"
            cy="50"
            r="44"
            pathLength="100"
            :style="{ strokeDashoffset: 100 - level }"
          />
        </svg>
        <slot name="center">
          <v-icon v-if="icon" :icon="icon" :color="tone" size="36" />
        </slot>
      </div>
      <output class="hero__text">
        <span class="hero__eyebrow" :data-test="`${testId}-eyebrow`">{{ eyebrow }}</span>
        <span class="hero__title" :data-test="`${testId}-title`">{{ title }}</span>
        <span v-if="detail" class="hero__detail text-body-large" :data-test="`${testId}-detail`">{{
          detail
        }}</span>
      </output>
      <div v-if="$slots.action" class="hero__action">
        <slot name="action" />
      </div>
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

.hero[data-mood='idle'] .hero__sweep {
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
.hero[data-mood='urgent'] .hero__arc {
  animation:
    hero-draw 1100ms cubic-bezier(0.2, 0.7, 0.2, 1) both,
    hero-breathe 1.8s ease-in-out 1100ms infinite;
}

.hero[data-mood='urgent'] .hero__ring::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid rgb(var(--tone));
  border-radius: 50%;
  opacity: 0;
  animation: hero-ripple 2.4s ease-out 1100ms infinite;
}

.hero[data-mood='idle'] .hero__arc {
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

/* It draws from nothing to wherever the ring was told to stop. */
@keyframes hero-draw {
  from {
    stroke-dashoffset: 100;
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
  .hero[data-mood='urgent'] .hero__arc,
  .hero__sweep,
  .hero[data-mood='urgent'] .hero__ring::after {
    animation: none;
  }
}
</style>
