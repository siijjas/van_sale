<template>
  <component
    :is="interactive ? 'button' : 'div'"
    :type="interactive ? 'button' : undefined"
    class="rounded-3xl bg-card text-left shadow-card transition duration-150 ease-emphasis"
    :class="[
      paddingClass,
      interactive ? 'focus-ring w-full hover:shadow-raised active:scale-[0.994] active:shadow-card' : '',
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
