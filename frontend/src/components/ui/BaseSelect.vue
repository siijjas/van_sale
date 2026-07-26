<template>
  <div class="relative">
    <select
      :value="modelValue"
      :disabled="disabled"
      class="field-input appearance-none pr-11"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
      <slot />
    </select>
    <AppIcon name="chevron-down" :size="18" class="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-subtle" />
  </div>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';

defineProps<{ modelValue: string | number | null; placeholder?: string; disabled?: boolean }>();
defineEmits<{ (e: 'update:modelValue', value: string): void }>();
</script>
