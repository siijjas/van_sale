<template>
  <button
    type="button"
    class="focus-ring flex h-10 w-10 items-center justify-center rounded-full border border-line bg-card text-muted transition hover:text-foreground"
    :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    @click="toggle"
  >
    <AppIcon :name="isDark ? 'sun' : 'moon'" :size="18" />
  </button>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';
import { useTheme } from '../../composables/useTheme';

const { isDark, toggle } = useTheme();
</script>
