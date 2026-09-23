<template>
  <label class="block">
    <span v-if="label" class="mb-[7px] flex items-center gap-1.5 text-[13px] font-semibold text-foreground">
      {{ label }}
      <span v-if="required" class="text-danger">*</span>
    </span>
    <slot />
    <span v-if="hint && !error" class="mt-[7px] block text-xs text-muted">{{ hint }}</span>
    <span v-if="error" class="mt-[7px] block text-xs font-medium text-danger">{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
defineProps<{ label?: string; hint?: string; error?: string; required?: boolean }>();
</script>
