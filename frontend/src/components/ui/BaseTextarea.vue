<template>
  <textarea
    :value="modelValue"
    :rows="rows"
    :placeholder="placeholder"
    :disabled="disabled"
    class="field-input resize-none py-3 leading-relaxed"
    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
  />
</template>

<script setup lang="ts">
withDefaults(defineProps<{ modelValue: string; placeholder?: string; rows?: number; disabled?: boolean }>(), {
  rows: 3,
});
defineEmits<{ (e: 'update:modelValue', value: string): void }>();
</script>
