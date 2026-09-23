<template>
  <div class="flex items-start gap-3 rounded-2xl px-4 py-3 text-sm ring-1 ring-inset" :class="toneClass">
    <AppIcon :name="icon" :size="18" class="mt-0.5 shrink-0" />
    <div class="min-w-0 flex-1">
      <p v-if="title" class="font-semibold">{{ title }}</p>
      <p :class="title ? 'mt-0.5 text-[13px] leading-relaxed opacity-85' : 'text-[13px] font-semibold'">
        <slot>{{ message }}</slot>
      </p>
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
      info: 'bg-info/12 text-info ring-info/25',
      success: 'bg-success/12 text-success ring-success/25',
      warning: 'bg-warning/12 text-warning ring-warning/28',
      danger: 'bg-danger/12 text-danger ring-danger/25',
    })[props.tone],
);
</script>
