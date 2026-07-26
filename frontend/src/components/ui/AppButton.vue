<template>
  <component
    :is="to ? 'RouterLink' : 'button'"
    :to="to"
    :type="to ? undefined : type"
    :disabled="!to && (disabled || loading)"
    class="focus-ring inline-flex select-none items-center justify-center gap-2 rounded-2xl font-semibold transition active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50"
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

const variantClass = computed(
  () =>
    ({
      primary: 'bg-primary text-primary-fg shadow-sm hover:opacity-90',
      success: 'bg-success text-success-fg shadow-sm hover:opacity-90',
      warning: 'bg-warning text-warning-fg shadow-sm hover:opacity-90',
      danger: 'bg-danger text-danger-fg shadow-sm hover:opacity-90',
      secondary: 'border border-line-strong bg-card text-foreground shadow-sm hover:bg-card-muted',
      subtle: 'bg-card-muted text-foreground hover:bg-line',
      ghost: 'text-muted hover:bg-card-muted hover:text-foreground',
    })[props.variant],
);

const sizeClass = computed(
  () =>
    ({
      sm: 'min-h-touch px-3.5 text-sm',
      md: 'min-h-touch-lg px-5 text-[15px]',
      lg: 'min-h-touch-xl px-6 text-base',
    })[props.size],
);

const iconSize = computed(() => (props.size === 'sm' ? 16 : props.size === 'lg' ? 22 : 18));
</script>
