<template>
  <div class="flex gap-1 rounded-2xl border border-line bg-card-muted p-1">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="focus-ring flex-1 rounded-xl px-3 py-2.5 text-sm font-semibold transition"
      :class="
        modelValue === opt.value
          ? 'bg-card text-foreground shadow-sm'
          : 'text-muted hover:text-foreground'
      "
      @click="$emit('update:modelValue', opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ modelValue: string; options: { value: string; label: string }[] }>();
defineEmits<{ (e: 'update:modelValue', value: string): void }>();
</script>
