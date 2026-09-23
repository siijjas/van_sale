<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.06em]"
    :class="toneClass"
  >
    <span v-if="dot" class="h-1.5 w-1.5 rounded-full bg-current" />
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'primary';

const props = withDefaults(
  defineProps<{ label?: string; tone?: Tone; status?: string; dot?: boolean }>(),
  { dot: true },
);

const STATUS_TONE: Record<string, Tone> = {
  draft: 'neutral',
  submitted: 'info',
  'to deliver and bill': 'info',
  'to bill': 'info',
  'to deliver': 'info',
  completed: 'success',
  paid: 'success',
  closed: 'success',
  cancelled: 'danger',
  overdue: 'danger',
  unpaid: 'warning',
  'partly paid': 'warning',
  return: 'warning',
  'credit note issued': 'success',
};

const resolvedTone = computed<Tone>(() => {
  if (props.tone) return props.tone;
  if (props.status) return STATUS_TONE[props.status.toLowerCase()] ?? 'neutral';
  return 'neutral';
});

const toneClass = computed(
  () =>
    ({
      success: 'bg-success/14 text-success',
      warning: 'bg-warning/16 text-warning',
      danger: 'bg-danger/14 text-danger',
      info: 'bg-info/14 text-info',
      primary: 'bg-primary-soft text-primary',
      neutral: 'bg-card-muted text-muted',
    })[resolvedTone.value],
);
</script>
