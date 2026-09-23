<template>
  <div class="flex items-center gap-1 rounded-3xl bg-card-muted p-1">
    <button
      type="button"
      class="focus-ring flex h-touch w-touch items-center justify-center rounded-xl bg-card text-foreground shadow-card transition duration-150 ease-emphasis active:scale-90 active:shadow-none disabled:opacity-40"
      :disabled="modelValue <= min"
      :aria-label="'Decrease'"
      @click="step(-1)"
    >
      <AppIcon name="minus" :size="18" :stroke-width="2.2" />
    </button>
    <span class="tnum w-10 text-center text-base font-semibold text-foreground">{{ modelValue }}</span>
    <button
      type="button"
      class="focus-ring flex h-touch w-touch items-center justify-center rounded-xl bg-primary text-primary-fg shadow-btn transition duration-150 ease-emphasis active:scale-90 active:brightness-90 active:shadow-none disabled:opacity-40"
      :disabled="disableAdd"
      :aria-label="'Increase'"
      @click="step(1)"
    >
      <AppIcon name="plus" :size="18" :stroke-width="2.2" />
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
