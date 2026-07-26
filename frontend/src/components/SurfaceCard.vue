<template>
  <section
    class="rounded-2xl border border-slate-200 bg-white shadow-sm"
    :class="paddingClass"
  >
    <slot />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    padding?: 'none' | 'sm' | 'md' | 'lg';
  }>(),
  {
    padding: 'md',
  },
);

const paddingClass = computed(() => {
  if (props.padding === 'none') return '';
  if (props.padding === 'sm') return 'p-3';
  if (props.padding === 'lg') return 'p-5 md:p-6';
  return 'p-4 md:p-5';
});
</script>