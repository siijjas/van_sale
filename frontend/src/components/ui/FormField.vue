<template>
  <label class="block">
    <span v-if="label" class="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-foreground">
      {{ label }}
      <span v-if="required" class="text-danger">*</span>
    </span>
    <slot />
    <span v-if="hint && !error" class="mt-1.5 block text-xs text-muted">{{ hint }}</span>
    <span v-if="error" class="mt-1.5 block text-xs font-medium text-danger">{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
defineProps<{ label?: string; hint?: string; error?: string; required?: boolean }>();
</script>
