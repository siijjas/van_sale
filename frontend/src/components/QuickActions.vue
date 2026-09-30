<template>
  <section>
    <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Quick actions</p>
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
      <button
        v-for="a in actions"
        :key="a.label"
        class="focus-ring flex min-h-touch-xl flex-col items-start gap-3 rounded-3xl border border-line bg-card p-4 text-left shadow-card transition hover:border-line-strong hover:shadow-raised active:scale-[0.97]"
        @click="a.go"
      >
        <span class="flex h-11 w-11 items-center justify-center rounded-2xl" :class="a.accent">
          <AppIcon :name="a.icon" :size="22" />
        </span>
        <span class="text-sm font-bold text-foreground">{{ a.label }}</span>
      </button>
    </div>
  </section>
</template>

<script lang="ts">
export interface QuickAction {
  label: string;
  icon: string;
  accent: string;
  go: () => void;
}
</script>

<script setup lang="ts">
import { AppIcon } from './ui';

defineProps<{ actions: QuickAction[] }>();
</script>
