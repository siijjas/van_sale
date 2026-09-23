<template>
  <component
    :is="interactive ? 'button' : 'div'"
    :type="interactive ? 'button' : undefined"
    class="relative overflow-hidden rounded-3xl bg-card p-4 text-left shadow-card transition duration-150 ease-emphasis md:p-5"
    :class="interactive ? 'focus-ring w-full hover:shadow-raised active:scale-[0.994] active:shadow-card' : ''"
  >
    <div class="flex items-center justify-between">
      <p class="text-[11px] font-bold uppercase tracking-[0.08em] text-muted">{{ label }}</p>
      <span v-if="icon" class="flex h-[30px] w-[30px] items-center justify-center rounded-xl" :class="accentClass">
        <AppIcon :name="icon" :size="16" />
      </span>
    </div>
    <p class="tnum mt-2 text-[28px] font-semibold leading-none text-foreground md:text-[32px]">{{ value }}</p>
    <p v-if="sub" class="tnum mt-1.5 text-[13px] font-medium text-muted">{{ sub }}</p>
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
      primary: 'bg-primary-soft text-primary',
      success: 'bg-success/14 text-success',
      warning: 'bg-warning/16 text-warning',
      danger: 'bg-danger/14 text-danger',
      info: 'bg-info/14 text-info',
    })[props.tone],
);
</script>
