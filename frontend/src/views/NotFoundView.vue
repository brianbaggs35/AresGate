<template>
  <v-container class="py-8" max-width="720">
    <v-empty-state
      headline="Page not found"
      text="That page doesn't exist."
      action-text="Back to the dashboard"
      to="/"
      data-test="not-found"
    />
  </v-container>
</template>
