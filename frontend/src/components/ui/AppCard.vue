<template>
  <component
    :is="interactive ? 'button' : 'div'"
    :type="interactive ? 'button' : undefined"
    class="rounded-3xl border border-line bg-card text-left shadow-card transition"
    :class="[
      paddingClass,
      interactive ? 'focus-ring w-full hover:border-line-strong hover:shadow-raised active:scale-[0.99]' : '',
    ]"
  >
    <slot />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{ padding?: 'none' | 'sm' | 'md' | 'lg'; interactive?: boolean }>(),
  { padding: 'md' },
);

const paddingClass = computed(
  () => ({ none: '', sm: 'p-3.5', md: 'p-4 md:p-5', lg: 'p-5 md:p-6' })[props.padding],
);
</script>
