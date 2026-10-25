<script setup lang="ts">
import AppPage from '@/components/AppPage.vue'
import PageHeader from '@/components/PageHeader.vue'
import SettingsNav from '@/components/SettingsNav.vue'
import { settingsSections } from '@/settings'
</script>

<template>
  <AppPage>
    <PageHeader
      title="Settings"
      description="Your account, where you are signed in, what has happened on this install, and how long its data is kept."
    />
    <div class="settings">
      <SettingsNav :sections="settingsSections" />
      <div class="settings__page">
        <router-view />
      </div>
    </div>
  </AppPage>
</template>

<style scoped>
.settings {
  display: grid;
  grid-template-columns: 13rem minmax(0, 1fr);
  gap: 1.5rem 2rem;
  align-items: start;
}

.settings__page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  min-width: 0;
}

/* Below a computer the list is tabs, which go above the page. */
@media (max-width: 959.98px) {
  .settings {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
