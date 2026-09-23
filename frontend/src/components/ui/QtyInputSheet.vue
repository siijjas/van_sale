<template>
  <BottomSheet :modelValue="modelValue" :title="title" @update:modelValue="close">
    <div class="space-y-4">
      <!-- Item meta -->
      <div v-if="subtitle || price || maxQty !== undefined" class="flex items-center justify-between rounded-2xl bg-card-muted px-4 py-3">
        <div>
          <p v-if="subtitle" class="tnum text-xs text-muted">{{ subtitle }}</p>
          <p v-if="price" class="tnum mt-0.5 text-sm font-semibold text-foreground">{{ price }}</p>
        </div>
        <div v-if="maxQty !== undefined" class="text-right">
          <p class="text-[10px] font-bold uppercase tracking-[0.08em] text-muted">Available</p>
          <p class="tnum mt-0.5 text-sm font-semibold text-foreground">{{ maxQty }}</p>
        </div>
      </div>

      <!-- Stepper row -->
      <div class="flex items-center gap-2.5">
        <button
          type="button"
          class="flex h-[58px] w-[58px] shrink-0 items-center justify-center rounded-3xl bg-card-muted text-foreground ring-1 ring-inset ring-line transition ease-emphasis active:scale-90 disabled:opacity-40"
          :disabled="localQty <= step"
          @click="localQty = roundQty(Math.max(step, localQty - step))"
        >
          <AppIcon name="minus" :size="20" :stroke-width="2.2" />
        </button>
        <input
          ref="inputRef"
          v-model.number="localQty"
          type="number"
          inputmode="decimal"
          step="any"
          min="0"
          class="tnum h-[58px] w-full rounded-3xl border-0 bg-card-muted text-center text-2xl font-semibold text-foreground shadow-[inset_0_0_0_1.5px_rgb(var(--c-primary))] focus:outline-none focus:ring-0"
          @focus="($event.target as HTMLInputElement).select()"
          @keydown.enter="confirm"
        />
        <button
          type="button"
          class="flex h-[58px] w-[58px] shrink-0 items-center justify-center rounded-3xl bg-primary text-primary-fg shadow-btn transition ease-emphasis active:scale-90 active:brightness-90 active:shadow-none disabled:opacity-40"
          :disabled="maxQty !== undefined && localQty >= maxQty"
          @click="localQty = roundQty(localQty + step)"
        >
          <AppIcon name="plus" :size="20" :stroke-width="2.2" />
        </button>
      </div>

      <AppButton block size="lg" @click="confirm">
        {{ confirmLabel || 'Confirm' }}
      </AppButton>

      <!-- Remove option when editing an existing line -->
      <button
        v-if="initialQty > 0"
        type="button"
        class="w-full py-1.5 text-center text-[13px] font-semibold text-danger"
        @click="remove"
      >
        Remove from order
      </button>
    </div>
  </BottomSheet>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import BottomSheet from './BottomSheet.vue';
import AppButton from './AppButton.vue';
import AppIcon from './AppIcon.vue';

const props = withDefaults(defineProps<{
  modelValue: boolean;
  title: string;
  subtitle?: string;
  price?: string;
  maxQty?: number;
  initialQty?: number;
  confirmLabel?: string;
  step?: number;
}>(), {
  initialQty: 0,
  step: 1,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'confirm', qty: number): void;
}>();

const inputRef = ref<HTMLInputElement | null>(null);
// Default to 1, not `step`: many items use a whole-number-only UOM (Nos, Unit,
// Box, ...), so a fresh "add to order" must start at a safe whole quantity
// regardless of the +/- button increment. Typing a fraction is still always
// possible for items that do support it (e.g. Dozen).
const localQty = ref(props.initialQty || 1);

// Guard against floating-point drift (e.g. 0.1 + 0.2) when stepping.
function roundQty(value: number) {
  return Math.round(value * 1000) / 1000;
}

watch(() => props.modelValue, (open) => {
  if (open) {
    localQty.value = props.initialQty || 1;
    nextTick(() => inputRef.value?.focus());
  }
});

function close() {
  emit('update:modelValue', false);
}

function confirm() {
  const qty = localQty.value > 0 ? localQty.value : 1;
  emit('confirm', qty);
  close();
}

function remove() {
  emit('confirm', 0);
  close();
}
</script>
