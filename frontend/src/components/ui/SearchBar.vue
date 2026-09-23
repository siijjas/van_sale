<template>
  <div class="relative">
    <AppIcon name="search" :size="19" class="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-subtle" />
    <input
      :value="modelValue"
      :placeholder="placeholder"
      inputmode="search"
      class="field-input pl-11 pr-12"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <button
      v-if="modelValue"
      type="button"
      class="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full text-subtle transition hover:bg-card-muted hover:text-foreground"
      @click="$emit('update:modelValue', '')"
    >
      <AppIcon name="x" :size="18" />
    </button>
  </div>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';

withDefaults(defineProps<{ modelValue: string; placeholder?: string }>(), {
  placeholder: 'Search…',
});
defineEmits<{ (e: 'update:modelValue', value: string): void }>();
</script>
