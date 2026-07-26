<template>
  <WorkspacePage back eyebrow="Close shift" title="End of day" description="Count each payment mode and reconcile against what's expected, then close your shift." width="default">
    <SkeletonList v-if="loading" :rows="3" height="7rem" />

    <div v-else-if="summary" class="space-y-5 pb-28">
      <div class="grid grid-cols-2 gap-3">
        <KpiTile label="Total sales" :value="`${currency} ${fmt(summary.total_sales)}`" icon="cart" tone="primary" />
        <KpiTile label="Collections" :value="`${currency} ${fmt(summary.total_collections)}`" icon="wallet" tone="success" />
        <KpiTile label="Opening float" :value="`${currency} ${fmt(summary.total_opening_float)}`" icon="briefcase" tone="info" />
        <KpiTile label="Expected cash" :value="`${currency} ${fmt(summary.expected_cash)}`" icon="banknote" tone="primary" />
        <KpiTile v-if="summary.total_expenses > 0" class="col-span-2" label="Route expenses" :value="`${currency} ${fmt(summary.total_expenses)}`" icon="file-text" tone="warning" />
      </div>

      <AppCard padding="lg" class="space-y-4">
        <p class="text-sm font-semibold text-foreground">Payment reconciliation</p>

        <div v-for="row in rows" :key="row.mode_of_payment" class="space-y-2 rounded-2xl border border-border p-3">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold text-foreground">{{ row.mode_of_payment }}</span>
            <span
              v-if="diff(row) !== 0"
              class="tnum text-xs font-bold"
              :class="diff(row) > 0 ? 'text-success' : 'text-danger'"
            >{{ diff(row) > 0 ? '+' : '' }}{{ currency }} {{ diff(row).toFixed(2) }}</span>
          </div>
          <div class="grid grid-cols-3 gap-2 text-center text-xs">
            <div class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Opening</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.opening_amount) }}</p>
            </div>
            <div class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Expected</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.expected_amount) }}</p>
            </div>
            <div class="text-left">
              <p class="mb-0.5 opacity-60">Counted</p>
              <BaseInput v-model="row.closing_amount" type="number" inputmode="decimal" :prefix="currency" placeholder="0.00" />
            </div>
          </div>
        </div>

        <div
          v-if="netDifference !== 0"
          class="flex items-center justify-between rounded-2xl border px-4 py-3"
          :class="netDifference > 0 ? 'border-success/25 bg-success/10 text-success' : 'border-danger/25 bg-danger/10 text-danger'"
        >
          <div>
            <p class="text-sm font-semibold">Net variance</p>
            <p class="text-xs opacity-90">{{ netDifference > 0 ? 'More than expected.' : 'Less than expected.' }}</p>
          </div>
          <span class="tnum text-lg font-bold">{{ netDifference > 0 ? '+' : '' }}{{ currency }} {{ netDifference.toFixed(2) }}</span>
        </div>

        <FormField label="Notes" hint="Optional — explain any variance.">
          <BaseTextarea v-model="notes" :rows="2" placeholder="Leave notes for the cashier…" />
        </FormField>
      </AppCard>

      <AppAlert v-if="error" tone="danger" :message="error" />
      <AppAlert v-if="successMsg" tone="success" :message="successMsg" />
    </div>

    <AppAlert v-else-if="error" tone="danger" :message="error" />

    <StickyBar v-if="summary">
      <AppButton size="lg" block icon="check-circle" :loading="submitting" @click="submit">
        {{ submitting ? 'Closing…' : 'Close shift' }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { ShiftClosingSummary, PaymentReconciliationRow } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, KpiTile, FormField, BaseInput, BaseTextarea, SkeletonList, StickyBar } from '../components/ui';

const store = useSessionStore();
const router = useRouter();
const currency = computed(() => store.currencyDisplay);

const loading = ref(true);
const submitting = ref(false);
const error = ref('');
const successMsg = ref('');
const summary = ref<ShiftClosingSummary | null>(null);
const rows = ref<PaymentReconciliationRow[]>([]);
const notes = ref('');

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const diff = (row: PaymentReconciliationRow) => (Number(row.closing_amount) || 0) - row.expected_amount;
const netDifference = computed(() => rows.value.reduce((sum, r) => sum + diff(r), 0));

const load = async () => {
  try {
    summary.value = await api.getShiftClosingSummary();
    rows.value = summary.value.payment_reconciliation.map((r) => ({ ...r }));
  } catch (e: any) {
    error.value = e?.message || 'No open shift to close.';
  } finally {
    loading.value = false;
  }
};

const submit = async () => {
  if (!summary.value) return;
  submitting.value = true;
  error.value = '';
  successMsg.value = '';
  try {
    const payload: PaymentReconciliationRow[] = rows.value.map((r) => ({
      ...r,
      closing_amount: Number(r.closing_amount) || 0,
    }));
    await api.closeShift(summary.value.opening_shift, payload, notes.value);
    successMsg.value = 'Shift closed. Redirecting…';
    setTimeout(() => router.push('/'), 1200);
  } catch (e: any) {
    error.value = e?.message || 'Failed to close shift';
  } finally {
    submitting.value = false;
  }
};

onMounted(load);
</script>
