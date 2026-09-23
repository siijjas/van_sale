<template>
  <component
    :is="to ? 'RouterLink' : 'button'"
    :to="to"
    :type="to ? undefined : type"
    :disabled="!to && (disabled || loading)"
    class="focus-ring inline-flex select-none items-center justify-center gap-2 rounded-2xl font-semibold
           transition duration-150 ease-emphasis active:scale-[0.98]
           disabled:pointer-events-none disabled:opacity-40"
    :class="[variantClass, sizeClass, block ? 'w-full' : '']"
  >
    <AppIcon v-if="loading" name="refresh" :size="iconSize" class="animate-spin" />
    <AppIcon v-else-if="icon" :name="icon" :size="iconSize" />
    <span v-if="$slots.default"><slot /></span>
    <AppIcon v-if="trailingIcon && !loading" :name="trailingIcon" :size="iconSize" />
  </component>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import AppIcon from './AppIcon.vue';

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'warning' | 'subtle';
    size?: 'sm' | 'md' | 'lg';
    block?: boolean;
    icon?: string;
    trailingIcon?: string;
    loading?: boolean;
    disabled?: boolean;
    type?: 'button' | 'submit' | 'reset';
    to?: string | object;
  }>(),
  { variant: 'primary', size: 'md', type: 'button' },
);

// Pressed = tonal darken + shadow collapse (physical), not just a scale.
const variantClass = computed(
  () =>
    ({
      primary: 'bg-primary text-primary-fg shadow-btn hover:brightness-110 active:brightness-90 active:shadow-none',
      success: 'bg-success text-success-fg shadow-btn hover:brightness-110 active:brightness-90 active:shadow-none',
      warning: 'bg-warning text-warning-fg shadow-btn hover:brightness-110 active:brightness-90 active:shadow-none',
      danger: 'bg-danger text-danger-fg shadow-btn hover:brightness-110 active:brightness-90 active:shadow-none',
      secondary:
        'bg-card text-foreground shadow-card ring-1 ring-inset ring-line-strong hover:bg-card-muted active:bg-card-muted active:shadow-none',
      subtle: 'bg-card-muted text-foreground hover:brightness-[0.97] active:brightness-95',
      ghost: 'text-muted hover:bg-card-muted hover:text-foreground',
    })[props.variant],
);

const sizeClass = computed(
  () =>
    ({
      sm: 'min-h-touch px-4 text-[13px]',
      md: 'min-h-touch-lg px-5 text-[15px]',
      lg: 'min-h-touch-xl px-6 text-base',
    })[props.size],
);

const iconSize = computed(() => (props.size === 'sm' ? 15 : props.size === 'lg' ? 20 : 18));
</script>
