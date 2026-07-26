<template>
  <div class="flex flex-col items-center justify-center rounded-3xl border border-dashed border-line bg-card/50 px-6 py-12 text-center">
    <span class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-card-muted text-subtle">
      <AppIcon :name="icon" :size="26" />
    </span>
    <p class="text-base font-semibold text-foreground">{{ title }}</p>
    <p v-if="description" class="mt-1 max-w-xs text-sm text-muted">{{ description }}</p>
    <div v-if="$slots.action" class="mt-5">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';
withDefaults(defineProps<{ icon?: string; title: string; description?: string }>(), { icon: 'inbox' });
</script>
