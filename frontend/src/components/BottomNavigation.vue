<script setup lang="ts">
import { navItems } from '@/navigation'
</script>

<template>
  <v-bottom-navigation tag="nav" aria-label="Main" grow color="primary" border="t" :elevation="0">
    <v-btn
      v-for="item in navItems"
      :key="item.route"
      :to="{ name: item.route }"
      :data-test="`nav-${item.route}`"
    >
      <v-icon :icon="item.icon" />
      <span>{{ item.title }}</span>
    </v-btn>
  </v-bottom-navigation>
</template>
