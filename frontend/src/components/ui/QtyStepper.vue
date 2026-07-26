<template>
  <div class="flex items-center gap-1 rounded-2xl border border-line bg-card-muted p-1">
    <button
      type="button"
      class="focus-ring flex h-11 w-11 items-center justify-center rounded-xl bg-card text-foreground shadow-sm transition active:scale-90 disabled:opacity-40"
      :disabled="modelValue <= min"
      :aria-label="'Decrease'"
      @click="step(-1)"
    >
      <AppIcon name="minus" :size="18" />
    </button>
    <span class="tnum w-9 text-center text-base font-bold text-foreground">{{ modelValue }}</span>
    <button
      type="button"
      class="focus-ring flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-fg shadow-sm transition active:scale-90 disabled:opacity-40"
      :disabled="disableAdd"
      :aria-label="'Increase'"
      @click="step(1)"
    >
      <AppIcon name="plus" :size="18" />
    </button>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{ modelValue: number; min?: number; disableAdd?: boolean }>(),
  { min: 0 },
);
const emit = defineEmits<{ (e: 'change', delta: number): void }>();
function step(delta: number) {
  emit('change', delta);
}
</script>
