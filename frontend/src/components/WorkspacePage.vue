<template>
  <div class="min-h-full bg-background px-4 py-5 md:px-6 md:py-7">
    <div :class="containerClass">
      <div
        v-if="title || description || $slots.actions || back"
        class="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between md:gap-4"
      >
        <div class="flex items-start gap-3">
          <button
            v-if="back"
            type="button"
            class="focus-ring -ml-1 mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line bg-card text-muted transition hover:text-foreground"
            aria-label="Back"
            @click="goBack"
          >
            <AppIcon name="arrow-left" :size="20" />
          </button>
          <div class="min-w-0">
            <p v-if="eyebrow" class="text-[11px] font-bold uppercase tracking-widest text-primary">{{ eyebrow }}</p>
            <h1 v-if="title" class="mt-0.5 truncate text-[22px] font-bold tracking-tight text-foreground md:text-3xl">
              {{ title }}
            </h1>
            <p v-if="description" class="mt-1 max-w-2xl text-sm leading-relaxed text-muted">{{ description }}</p>
          </div>
        </div>
        <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
          <slot name="actions" />
        </div>
      </div>

      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import AppIcon from './ui/AppIcon.vue';

const props = withDefaults(
  defineProps<{
    eyebrow?: string;
    title?: string;
    description?: string;
    width?: 'default' | 'wide' | 'narrow';
    back?: boolean;
  }>(),
  { width: 'wide' },
);

const router = useRouter();
function goBack() {
  router.back();
}

const containerClass = computed(() => {
  if (props.width === 'narrow') return 'mx-auto max-w-2xl space-y-5';
  if (props.width === 'default') return 'mx-auto max-w-4xl space-y-5';
  return 'mx-auto max-w-6xl space-y-5';
});
</script>
