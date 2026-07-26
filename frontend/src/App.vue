<template>
  <RouterView v-if="route.meta.public" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
</template>

<script setup lang="ts">
import { useRoute, RouterView } from 'vue-router';
import AppShell from './components/AppShell.vue';
import { useTheme } from './composables/useTheme';

const route = useRoute();
// Initialise the theme singleton + system-preference listener at app root.
useTheme();
</script>
