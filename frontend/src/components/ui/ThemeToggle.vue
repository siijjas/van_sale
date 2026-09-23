<template>
  <button
    type="button"
    class="focus-ring flex h-[38px] w-[38px] items-center justify-center rounded-full bg-card-muted text-muted transition hover:text-foreground active:scale-90"
    :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    @click="toggle"
  >
    <AppIcon :name="isDark ? 'sun' : 'moon'" :size="17" />
  </button>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';
import { useTheme } from '../../composables/useTheme';

const { isDark, toggle } = useTheme();
</script>
