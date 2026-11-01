<script setup lang="ts">
import { useId } from 'vue'

import { ROLES, type Role } from '@/api/interfaces'
import { roleInfo } from '@/interfaces'

/**
 * Chooses what a part of the network is for, from cards that each say what the role means in a
 * sentence, so nobody has to know what a DMZ is. They are ordinary radio buttons underneath, so
 * the arrow keys move between them and a screen reader hears them as one group.
 */
const role = defineModel<Role>({ required: true })

const group = useId()
</script>

<template>
  <fieldset class="roles" data-test="role-picker">
    <legend class="text-title-small roles__legend">What is it for?</legend>
    <div class="roles__grid">
      <label
        v-for="key in ROLES"
        :key="key"
        class="role"
        :class="{ 'role--chosen': role === key }"
        :data-test="`role-card-${key}`"
      >
        <input v-model="role" type="radio" class="role__input" :name="group" :value="key" />
        <v-icon :icon="roleInfo(key).icon" size="22" />
        <span class="role__label text-title-small">{{ roleInfo(key).label }}</span>
        <span class="role__text text-body-small text-medium-emphasis">
          {{ roleInfo(key).description }}
        </span>
      </label>
    </div>
  </fieldset>
</template>

<style scoped>
.roles {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.roles__legend {
  margin-bottom: 0.5rem;
  padding: 0;
}

.roles__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.5rem;
}

.role {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 0.125rem 0.625rem;
  padding: 0.75rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.75rem;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background-color 0.15s;
}

.role:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.role--chosen {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
}

.role:has(.role__input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* The radio button is there for the keyboard and screen readers; the card is what is seen. */
.role__input {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  margin: 0;
  opacity: 0;
}

.role__text {
  grid-column: 1 / -1;
}

@media (prefers-reduced-motion: reduce) {
  .role {
    transition: none;
  }
}
</style>
