<template>
  <div class="flex flex-col items-center justify-center rounded-3xl bg-card/60 px-6 py-9 text-center ring-1 ring-inset ring-line">
    <span class="mb-3.5 flex h-[52px] w-[52px] items-center justify-center rounded-3xl bg-card-muted text-subtle">
      <AppIcon :name="icon" :size="24" :stroke-width="1.8" />
    </span>
    <p class="text-[15px] font-semibold text-foreground">{{ title }}</p>
    <p v-if="description" class="mt-1.5 max-w-[250px] text-[13px] leading-relaxed text-muted">{{ description }}</p>
    <div v-if="$slots.action" class="mt-[18px]">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';
withDefaults(defineProps<{ icon?: string; title: string; description?: string }>(), { icon: 'inbox' });
</script>
