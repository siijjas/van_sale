<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="modelValue" class="fixed inset-0 z-[100] flex items-end justify-center sm:items-center">
        <div class="absolute inset-0 bg-[rgb(23_26_27/0.55)] backdrop-blur-sm" @click="$emit('update:modelValue', false)" />
        <div
          class="relative w-full max-w-md animate-sheet-up rounded-t-4xl bg-elevated p-5 pb-safe shadow-pop sm:rounded-3xl"
        >
          <div class="mx-auto mb-3.5 h-[5px] w-10 rounded-full bg-line-strong sm:hidden" />
          <div v-if="title" class="mb-4 flex items-center justify-between gap-3">
            <h3 class="text-[17px] font-bold tracking-tight text-foreground">{{ title }}</h3>
            <button
              type="button"
              class="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-card-muted text-muted transition hover:text-foreground"
              @click="$emit('update:modelValue', false)"
            >
              <AppIcon name="x" :size="18" />
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
