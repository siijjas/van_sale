<template>
  <div class="relative flex items-center">
    <span v-if="prefix" class="pointer-events-none absolute left-4 text-base font-semibold text-muted">{{ prefix }}</span>
    <AppIcon v-if="icon" :name="icon" :size="18" class="pointer-events-none absolute left-4 text-subtle" />
    <input
      :value="modelValue"
      :type="type"
      :inputmode="inputmode"
      :placeholder="placeholder"
      :disabled="disabled"
      class="field-input"
      :class="[prefix ? 'pl-9' : '', icon ? 'pl-11' : '', $slots.suffix ? 'pr-12' : '']"
      @input="$emit('update:modelValue', cast(($event.target as HTMLInputElement).value))"
    />
    <span v-if="$slots.suffix" class="absolute right-3 flex items-center">
      <slot name="suffix" />
    </span>
  </div>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';

const props = withDefaults(
  defineProps<{
    modelValue: string | number | null;
    type?: string;
    inputmode?: string;
    placeholder?: string;
    prefix?: string;
    icon?: string;
    disabled?: boolean;
  }>(),
  { type: 'text' },
);

defineEmits<{ (e: 'update:modelValue', value: string | number): void }>();

function cast(v: string): string | number {
  return props.type === 'number' ? (v === '' ? 0 : Number(v)) : v;
}
</script>
