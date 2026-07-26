<template>
  <div class="flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm" :class="toneClass">
    <AppIcon :name="icon" :size="18" class="mt-0.5 shrink-0" />
    <div class="min-w-0 flex-1">
      <p v-if="title" class="font-semibold">{{ title }}</p>
      <p :class="title ? 'mt-0.5 opacity-90' : 'font-medium'"><slot>{{ message }}</slot></p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';

const props = withDefaults(
  defineProps<{ tone?: 'info' | 'success' | 'warning' | 'danger'; title?: string; message?: string; icon?: string }>(),
  { tone: 'info' },
);

const icon = computed(
  () => props.icon ?? { info: 'info', success: 'check-circle', warning: 'alert', danger: 'alert' }[props.tone],
);

const toneClass = computed(
  () =>
    ({
      info: 'border-info/25 bg-info/10 text-info',
      success: 'border-success/25 bg-success/10 text-success',
      warning: 'border-warning/30 bg-warning/10 text-warning',
      danger: 'border-danger/25 bg-danger/10 text-danger',
    })[props.tone],
);
</script>
