<template>
  <BottomSheet :modelValue="modelValue" :title="title" @update:modelValue="close">
    <div class="space-y-5">
      <!-- Item meta -->
      <div v-if="subtitle || price || maxQty !== undefined" class="flex items-center justify-between rounded-2xl bg-card-muted px-4 py-3">
        <div>
          <p v-if="subtitle" class="text-xs text-muted">{{ subtitle }}</p>
          <p v-if="price" class="mt-0.5 text-sm font-bold text-foreground">{{ price }}</p>
        </div>
        <div v-if="maxQty !== undefined" class="text-right">
          <p class="text-[11px] uppercase tracking-wide text-muted">Available</p>
          <p class="tnum text-sm font-bold text-foreground">{{ maxQty }}</p>
        </div>
      </div>

      <!-- Stepper row -->
      <div class="flex items-center gap-3">
        <button
          type="button"
          class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-line bg-card-muted text-foreground transition active:scale-90 disabled:opacity-40"
          :disabled="localQty <= 1"
          @click="localQty = Math.max(1, localQty - 1)"
        >
          <AppIcon name="minus" :size="20" />
        </button>
        <input
          ref="inputRef"
          v-model.number="localQty"
          type="number"
          inputmode="numeric"
          min="1"
          class="tnum h-14 w-full rounded-2xl border border-line bg-card-muted text-center text-2xl font-bold text-foreground focus:border-primary focus:outline-none"
          @focus="($event.target as HTMLInputElement).select()"
          @keydown.enter="confirm"
        />
        <button
          type="button"
          class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-fg transition active:scale-90 disabled:opacity-40"
          :disabled="maxQty !== undefined && localQty >= maxQty"
          @click="localQty++"
        >
          <AppIcon name="plus" :size="20" />
        </button>
      </div>

      <AppButton block size="lg" @click="confirm">
        {{ confirmLabel || 'Confirm' }}
      </AppButton>

      <!-- Remove option when editing an existing line -->
      <button
        v-if="initialQty > 0"
        type="button"
        class="w-full text-center text-sm font-semibold text-danger"
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
}>(), {
  initialQty: 0,
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'confirm', qty: number): void;
}>();

const inputRef = ref<HTMLInputElement | null>(null);
const localQty = ref(Math.max(1, props.initialQty));

watch(() => props.modelValue, (open) => {
  if (open) {
    localQty.value = Math.max(1, props.initialQty);
    nextTick(() => inputRef.value?.focus());
  }
});

function close() {
  emit('update:modelValue', false);
}

function confirm() {
  const qty = Math.max(1, localQty.value || 1);
  emit('confirm', qty);
  close();
}

function remove() {
  emit('confirm', 0);
  close();
}
</script>
