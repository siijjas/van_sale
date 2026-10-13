<template>
  <WorkspacePage back eyebrow="Close shift" title="End of day" description="Count each payment mode and reconcile against what's expected (opening float + collections − expenses − deposits), then close your shift." width="default">
    <SkeletonList v-if="loading" :rows="3" height="7rem" />

    <div v-else-if="summary" class="space-y-5 pb-28">
      <AppAlert
        v-if="summary.is_stale || !isOwnShift"
        tone="warning"
        :title="closingTitle"
        :message="summary.is_stale
          ? 'This shift was never closed. It closes as that day: the figures below are that day\'s sales, collections and expenses. Count the cash that belongs to it.'
          : 'You are closing this shift on the driver\'s behalf. The closing records that you closed it.'"
      />
      <AppAlert
        v-if="summary.draft_orders.length"
        tone="warning"
        :title="`${summary.draft_orders.length} draft order${summary.draft_orders.length === 1 ? '' : 's'} not submitted`"
      >
        Drafts are not counted in this closing. Submit or discard them first, or close anyway and the closing will note them.
        <ul class="mt-2 space-y-1">
          <li v-for="d in summary.draft_orders" :key="d.name">
            <button type="button" class="font-semibold underline underline-offset-2" @click="router.push({ name: 'order-detail', params: { name: d.name } })">{{ d.name }}</button>
            <span class="opacity-90"> · {{ d.customer_name || d.customer }} · {{ currency }} {{ fmt(d.grand_total) }}</span>
          </li>
        </ul>
      </AppAlert>
      <AppAlert
        v-if="outsideCount"
        tone="info"
        title="Activity before this shift opened"
        :message="`${outsideText} on ${shiftDay(summary.shift_date)} before the shift opened and on no other closing. They are not in this closing's totals.`"
      />

      <AppAlert
        v-if="summary.blind"
        tone="info"
        title="Blind count"
        message="Count each payment mode and enter what you actually have. Your profile hides the expected amounts; your manager sees the difference on the closing report."
      />

      <div class="grid grid-cols-2 gap-3">
        <KpiTile label="Total sales" :value="`${currency} ${fmt(summary.total_sales)}`" :sub="`${qty(summary.total_quantity)} units · tax ${currency} ${fmt(summary.total_taxes)}`" icon="cart" tone="primary" />
        <KpiTile label="Collections" :value="`${currency} ${fmt(summary.total_collections)}`" icon="wallet" tone="success" />
        <KpiTile label="Opening float" :value="`${currency} ${fmt(summary.total_opening_float)}`" icon="briefcase" tone="info" />
        <KpiTile v-if="!summary.blind" label="Expected cash" :value="`${currency} ${fmt(summary.expected_cash ?? 0)}`" icon="banknote" tone="primary" />
        <KpiTile v-if="summary.total_expenses > 0" :class="summary.total_deposits > 0 ? '' : 'col-span-2'" label="Expenses paid" :value="`${currency} ${fmt(summary.total_expenses)}`" icon="file-text" tone="warning" />
        <KpiTile v-if="summary.total_deposits > 0" :class="summary.total_expenses > 0 ? '' : 'col-span-2'" label="Deposited to office" :value="`${currency} ${fmt(summary.total_deposits)}`" icon="banknote" tone="info" />
      </div>

      <AppCard padding="lg" class="space-y-4">
        <p class="text-sm font-semibold text-foreground">Payment reconciliation</p>

        <div v-for="row in rows" :key="row.mode_of_payment" class="space-y-2 rounded-2xl border border-border p-3">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold text-foreground">{{ row.mode_of_payment }}</span>
            <span
              v-if="!summary.blind && diff(row) !== 0"
              class="tnum text-xs font-bold"
              :class="diff(row) > 0 ? 'text-success' : 'text-danger'"
            >{{ diff(row) > 0 ? '+' : '' }}{{ currency }} {{ diff(row).toFixed(2) }}</span>
          </div>
          <div class="grid gap-2 text-center text-xs" :class="summary.blind ? 'grid-cols-2' : 'grid-cols-3'">
            <div class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Opening</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.opening_amount) }}</p>
            </div>
            <div v-if="!summary.blind" class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Expected</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.expected_amount ?? 0) }}</p>
            </div>
            <div class="text-left">
              <p class="mb-0.5 opacity-60">Counted</p>
              <BaseInput v-model="row.closing_amount" type="number" inputmode="decimal" :prefix="currency" placeholder="0.00" />
            </div>
          </div>
        </div>

        <div
          v-if="!summary.blind && netDifference !== 0"
          class="flex items-center justify-between rounded-2xl border px-4 py-3"
          :class="varianceStatus === 'Within Tolerance'
            ? 'border-warning/25 bg-warning/10 text-warning'
            : netDifference > 0 ? 'border-success/25 bg-success/10 text-success' : 'border-danger/25 bg-danger/10 text-danger'"
        >
          <div>
            <p class="text-sm font-semibold">Net variance · {{ varianceStatus }}</p>
            <p class="text-xs opacity-90">
              {{ netDifference > 0 ? 'More than expected.' : 'Less than expected.' }}
              <template v-if="summary.variance_tolerance">
                {{ varianceStatus === 'Within Tolerance' ? 'Within' : 'Beyond' }} the {{ currency }} {{ fmt(summary.variance_tolerance) }} tolerance.
              </template>
              <template v-else>Your manager will see this flagged.</template>
            </p>
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
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { ShiftClosingSummary, PaymentReconciliationRow, VarianceStatus } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, KpiTile, FormField, BaseInput, BaseTextarea, SkeletonList, StickyBar } from '../components/ui';

const store = useSessionStore();
const router = useRouter();
const route = useRoute();
const currency = computed(() => store.currencyDisplay);

const loading = ref(true);
const submitting = ref(false);
const error = ref('');
const successMsg = ref('');
const summary = ref<ShiftClosingSummary | null>(null);
const rows = ref<PaymentReconciliationRow[]>([]);
const notes = ref('');

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (n?: number) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
const diff = (row: PaymentReconciliationRow) => (Number(row.closing_amount) || 0) - (row.expected_amount ?? 0);
const netDifference = computed(() => rows.value.reduce((sum, r) => sum + diff(r), 0));
// Mirrors shift closing's variance_status (flag only; closing is never blocked).
const varianceStatus = computed<VarianceStatus>(() => {
  const d = Math.abs(netDifference.value);
  if (d < 0.005) return 'Balanced';
  return d <= (summary.value?.variance_tolerance || 0) + 0.005 ? 'Within Tolerance' : 'Exceeds Tolerance';
});
const outsideCount = computed(() => {
  const o = summary.value?.outside_window;
  return o ? o.orders_count + o.payments_count : 0;
});
const outsideText = computed(() => {
  const o = summary.value!.outside_window;
  const parts: string[] = [];
  if (o.orders_count) parts.push(`${o.orders_count} order${o.orders_count === 1 ? '' : 's'} (${currency.value} ${fmt(o.orders_total)})`);
  if (o.payments_count) parts.push(`${o.payments_count} payment${o.payments_count === 1 ? '' : 's'} (${currency.value} ${fmt(o.payments_total)})`);
  return parts.join(' and ') + (o.orders_count + o.payments_count === 1 ? ' was made' : ' were made');
});
const isOwnShift = computed(() => !summary.value || summary.value.driver === store.session?.user);
const shiftDay = (s: string) =>
  new Date(`${s}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
const closingTitle = computed(() => {
  const s = summary.value!;
  const who = isOwnShift.value ? 'Your' : `${s.driver_name}'s`;
  return s.is_stale ? `${who} shift from ${shiftDay(s.shift_date)} is still open` : `Closing ${s.driver_name}'s shift`;
});

const load = async () => {
  try {
    // ?opening= lets a manager close a specific driver's shift (from the fleet dashboard).
    summary.value = await api.getShiftClosingSummary((route.query.opening as string) || undefined);
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
    const closed = await api.closeShift(summary.value.opening_shift, payload, notes.value);
    successMsg.value = 'Shift closed. Opening the closing report…';
    setTimeout(() => router.replace({ name: 'closing-report', params: { name: closed.name } }), 1200);
  } catch (e: any) {
    error.value = e?.message || 'Failed to close shift';
  } finally {
    submitting.value = false;
  }
};

onMounted(load);
</script>
