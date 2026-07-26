<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="modelValue" class="fixed inset-0 z-[100] flex items-end justify-center sm:items-center">
        <div class="absolute inset-0 bg-slate-950/50 backdrop-blur-sm" @click="$emit('update:modelValue', false)" />
        <div
          class="relative w-full max-w-md animate-sheet-up rounded-t-3xl border border-line bg-elevated p-5 pb-safe shadow-pop sm:rounded-3xl"
        >
          <div class="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line-strong sm:hidden" />
          <div v-if="title" class="mb-4 flex items-center justify-between">
            <h3 class="text-lg font-bold text-foreground">{{ title }}</h3>
            <button
              type="button"
              class="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-card-muted"
              @click="$emit('update:modelValue', false)"
            >
              <AppIcon name="x" :size="20" />
            </button>
          </div>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import AppIcon from './AppIcon.vue';
defineProps<{ modelValue: boolean; title?: string }>();
defineEmits<{ (e: 'update:modelValue', value: boolean): void }>();
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
