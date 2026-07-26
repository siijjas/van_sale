<template>
  <component
    :is="interactive ? 'button' : 'div'"
    :type="interactive ? 'button' : undefined"
    class="relative overflow-hidden rounded-3xl border border-line bg-card p-4 text-left shadow-card transition md:p-5"
    :class="interactive ? 'focus-ring w-full hover:border-line-strong hover:shadow-raised active:scale-[0.99]' : ''"
  >
    <div class="flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-muted">{{ label }}</p>
      <span v-if="icon" class="flex h-8 w-8 items-center justify-center rounded-xl" :class="accentClass">
        <AppIcon :name="icon" :size="16" />
      </span>
    </div>
    <p class="tnum mt-2 text-2xl font-bold text-foreground md:text-3xl">{{ value }}</p>
    <p v-if="sub" class="tnum mt-0.5 text-sm font-medium text-muted">{{ sub }}</p>
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    sub?: string;
    icon?: string;
    tone?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
    interactive?: boolean;
  }>(),
  { tone: 'primary' },
);

const accentClass = computed(
  () =>
    ({
      primary: 'bg-primary/12 text-primary',
      success: 'bg-success/12 text-success',
      warning: 'bg-warning/15 text-warning',
      danger: 'bg-danger/12 text-danger',
      info: 'bg-info/12 text-info',
    })[props.tone],
);
</script>
