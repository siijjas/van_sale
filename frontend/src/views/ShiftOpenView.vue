<template>
  <WorkspacePage back eyebrow="Open shift" title="Start of day" description="Declare the opening cash float in your van before you begin selling." width="default">
    <SkeletonList v-if="loading" :rows="3" height="4rem" />

    <div v-else class="space-y-5 pb-28">
      <AppCard padding="lg" class="space-y-4">
        <p class="text-sm font-semibold text-foreground">Opening float by payment mode</p>
        <FormField
          v-for="mode in modes"
          :key="mode.name"
          :label="mode.name"
          :hint="mode.name === 'Cash' ? 'Physical cash you are starting the day with.' : 'Opening balance for this mode (optional).'"
        >
          <BaseInput
            v-model="floats[mode.name]"
            type="number"
            inputmode="decimal"
            :prefix="currency"
            placeholder="0.00"
          />
        </FormField>

        <div class="flex items-center justify-between rounded-2xl border border-border bg-muted/40 px-4 py-3">
          <span class="text-sm font-semibold text-foreground">Total opening float</span>
          <span class="tnum text-lg font-bold text-foreground">{{ currency }} {{ totalFloat.toFixed(2) }}</span>
        </div>

        <FormField label="Notes" hint="Optional.">
          <BaseTextarea v-model="notes" :rows="2" placeholder="Anything to note about this shift…" />
        </FormField>
      </AppCard>

      <AppAlert v-if="error" tone="danger" :message="error" />
      <AppAlert v-if="successMsg" tone="success" :message="successMsg" />
    </div>

    <StickyBar v-if="!loading">
      <AppButton size="lg" block icon="play-circle" :loading="submitting" @click="submit">
        {{ submitting ? 'Starting…' : 'Start shift' }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { PaymentMode, ShiftBalanceDetail } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, FormField, BaseInput, BaseTextarea, SkeletonList, StickyBar } from '../components/ui';

const store = useSessionStore();
const router = useRouter();
const currency = computed(() => store.currencyDisplay);

const loading = ref(true);
const submitting = ref(false);
const error = ref('');
const successMsg = ref('');
const modes = ref<PaymentMode[]>([]);
const floats = reactive<Record<string, number | string>>({});
const notes = ref('');

const totalFloat = computed(() =>
  modes.value.reduce((sum, m) => sum + (Number(floats[m.name]) || 0), 0),
);

const load = async () => {
  try {
    // If a shift is already open, send the driver straight to closing.
    const active = await api.getActiveShift();
    if (active) {
      router.replace('/shift/close');
      return;
    }
    modes.value = await api.getPaymentModes();
    modes.value.forEach((m) => { floats[m.name] = ''; });
  } catch (e: any) {
    error.value = e?.message || 'Failed to load payment modes';
  } finally {
    loading.value = false;
  }
};

const submit = async () => {
  submitting.value = true;
  error.value = '';
  successMsg.value = '';
  try {
    const balanceDetails: ShiftBalanceDetail[] = modes.value
      .map((m) => ({ mode_of_payment: m.name, opening_amount: Number(floats[m.name]) || 0 }))
      .filter((r) => r.opening_amount > 0);
    await api.openShift(balanceDetails, notes.value);
    successMsg.value = 'Shift started. Redirecting…';
    setTimeout(() => router.push('/'), 1200);
  } catch (e: any) {
    error.value = e?.message || 'Failed to start shift';
  } finally {
    submitting.value = false;
  }
};

onMounted(load);
</script>
