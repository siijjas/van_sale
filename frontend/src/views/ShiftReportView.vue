<template>
  <WorkspacePage back :eyebrow="isSummary ? 'Open shift' : 'Closed shift'" :title="isSummary ? 'Shift summary' : 'Closing report'" :description="description" width="default">
    <template #actions>
      <AppButton v-if="isSummary" variant="secondary" size="sm" icon="refresh" :loading="loading" @click="load">Refresh</AppButton>
      <AppButton v-if="report" variant="secondary" size="sm" icon="printer" @click="printPdf">Print</AppButton>
    </template>

    <SkeletonList v-if="loading && !report" :rows="4" height="6rem" />

    <div v-else-if="report" class="space-y-5 pb-8">
      <AppAlert v-if="isSummary" tone="info" message="Interim report. Your shift is still open, so these figures will change until you close it." />

      <AppCard padding="sm">
        <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <div><dt class="text-muted">Driver</dt><dd class="font-semibold text-foreground">{{ report.shift.driver_name || report.shift.driver }}</dd></div>
          <div v-if="report.shift.van_profile"><dt class="text-muted">Van</dt><dd class="font-semibold text-foreground">{{ report.shift.van_profile }}</dd></div>
          <div><dt class="text-muted">Opened</dt><dd class="tnum font-semibold text-foreground">{{ formatDateTime(report.shift.period_start) }}</dd></div>
          <div><dt class="text-muted">{{ isSummary ? 'As of' : 'Closed' }}</dt><dd class="tnum font-semibold text-foreground">{{ formatDateTime(isSummary ? report.generated_at : report.shift.period_end) }}</dd></div>
        </dl>
      </AppCard>

      <div class="grid grid-cols-2 gap-3">
        <KpiTile label="Sales" :value="`${currency} ${fmt(t.total_sales)}`" :sub="`${t.sales_orders_count} orders`" icon="cart" tone="primary" />
        <KpiTile label="Collections" :value="`${currency} ${fmt(t.total_collections)}`" :sub="`${t.payments_count} payments`" icon="wallet" tone="success" />
        <KpiTile label="Expenses" :value="`${currency} ${fmt(t.total_expenses)}`" :sub="`${t.expenses_count} entries`" icon="file-text" tone="warning" />
        <KpiTile label="Expected cash" :value="`${currency} ${fmt(t.expected_cash)}`" :sub="`Float ${currency} ${fmt(t.total_opening_float)}`" icon="banknote" tone="info" />
      </div>

      <div
        v-if="!isSummary && t.net_difference !== undefined"
        class="flex items-center justify-between rounded-2xl border px-4 py-3"
        :class="varianceClass(t.net_difference)"
      >
        <div>
          <p class="text-sm font-semibold">Net variance</p>
          <p class="text-xs opacity-90">{{ t.net_difference === 0 ? 'Counted matches expected.' : t.net_difference > 0 ? 'More than expected.' : 'Less than expected.' }}</p>
        </div>
        <span class="tnum text-lg font-bold">{{ signed(t.net_difference) }}</span>
      </div>

      <!-- Sales -->
      <AppCard padding="lg" class="space-y-2">
        <p class="mb-1 text-sm font-semibold text-foreground">Sales</p>
        <div v-for="line in salesLines" :key="line.label" class="flex items-center justify-between text-sm">
          <span class="text-muted">{{ line.label }} <span class="text-subtle">· {{ line.count }}</span></span>
          <span class="tnum font-semibold text-foreground">{{ line.negative && line.amount ? '−' : '' }}{{ currency }} {{ fmt(line.amount) }}</span>
        </div>
        <div class="flex items-center justify-between border-t border-line pt-2 text-sm">
          <span class="font-semibold text-foreground">Net invoiced</span>
          <span class="tnum font-bold text-foreground">{{ currency }} {{ fmt(t.net_invoiced) }}</span>
        </div>
      </AppCard>

      <!-- Collections by mode -->
      <AppCard padding="lg" class="space-y-2">
        <p class="mb-1 text-sm font-semibold text-foreground">Collections by mode</p>
        <p v-if="!report.collections.length" class="text-sm text-muted">No collections.</p>
        <div v-for="c in report.collections" :key="c.mode_of_payment" class="flex items-center justify-between text-sm">
          <span class="min-w-0 truncate text-muted">{{ c.mode_of_payment }} <span class="text-subtle">· {{ c.count }}</span></span>
          <span class="tnum font-semibold text-foreground">{{ currency }} {{ fmt(c.amount) }}</span>
        </div>
      </AppCard>

      <!-- Cash reconciliation -->
      <AppCard padding="lg" class="space-y-3">
        <p class="text-sm font-semibold text-foreground">Cash reconciliation</p>
        <div v-for="row in report.payment_reconciliation" :key="row.mode_of_payment" class="space-y-2 rounded-2xl border border-border p-3">
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold text-foreground">{{ row.mode_of_payment }}</span>
            <span v-if="row.difference" class="tnum text-xs font-bold" :class="row.difference > 0 ? 'text-success' : 'text-danger'">{{ signed(row.difference) }}</span>
          </div>
          <div class="grid gap-2 text-center text-xs" :class="isSummary ? 'grid-cols-2' : 'grid-cols-3'">
            <div class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Opening</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.opening_amount) }}</p>
            </div>
            <div class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Expected</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.expected_amount) }}</p>
            </div>
            <div v-if="!isSummary" class="rounded-xl bg-muted/40 py-1.5">
              <p class="opacity-60">Counted</p>
              <p class="tnum font-semibold text-foreground">{{ fmt(row.closing_amount ?? 0) }}</p>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- Expenses -->
      <AppCard padding="lg" class="space-y-2">
        <p class="mb-1 text-sm font-semibold text-foreground">Expenses</p>
        <p v-if="!report.expenses.length" class="text-sm text-muted">No expenses.</p>
        <div v-for="e in report.expenses" :key="e.name" class="flex items-start justify-between gap-3 text-sm">
          <div class="min-w-0">
            <p class="text-foreground">{{ e.expense_type }}</p>
            <p v-if="e.notes" class="truncate text-xs text-muted">{{ e.notes }}</p>
          </div>
          <span class="tnum font-semibold text-foreground">{{ currency }} {{ fmt(e.amount) }}</span>
        </div>
      </AppCard>

      <!-- Items -->
      <AppCard padding="lg" class="space-y-3">
        <div>
          <p class="text-sm font-semibold text-foreground">Items</p>
          <p class="text-xs text-muted">In stock UOM. Amounts net of order discounts, before tax.</p>
        </div>
        <p v-if="!report.items.length" class="text-sm text-muted">No items sold or returned.</p>
        <div v-for="i in report.items" :key="i.item_code" class="flex items-start justify-between gap-3 border-t border-line pt-3 first-of-type:border-0 first-of-type:pt-0">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-foreground">{{ i.item_name || i.item_code }}</p>
            <p class="tnum text-xs text-muted">
              Sold {{ qty(i.sold_qty) }}<template v-if="i.returned_qty"> · Returned {{ qty(i.returned_qty) }}</template>
            </p>
          </div>
          <div class="shrink-0 text-right">
            <p class="tnum text-sm font-bold text-foreground">{{ qty(i.net_qty) }} {{ i.uom }}</p>
            <p class="tnum text-xs text-muted">{{ currency }} {{ fmt(i.sold_amount - i.returned_amount) }}</p>
          </div>
        </div>
      </AppCard>

      <AppCard v-if="report.shift.notes" padding="lg">
        <p class="mb-1 text-sm font-semibold text-foreground">Notes</p>
        <p class="whitespace-pre-line text-sm text-muted">{{ report.shift.notes }}</p>
      </AppCard>
    </div>

    <div v-else class="space-y-4">
      <AppAlert tone="danger" :message="error || 'Report unavailable.'" />
      <AppButton v-if="isSummary" variant="secondary" icon="play-circle" @click="router.push({ name: 'shift-open' })">Open a shift</AppButton>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { ShiftReport } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, KpiTile, SkeletonList } from '../components/ui';

const route = useRoute();
const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

const isSummary = computed(() => route.name === 'shift-summary');
const report = ref<ShiftReport | null>(null);
const loading = ref(true);
const error = ref('');

const t = computed(() => report.value!.totals);
const description = computed(() =>
  isSummary.value
    ? 'Everything on your open shift so far. Running it does not close the shift.'
    : report.value
      ? `Final figures for the shift on ${formatDate(report.value.shift.shift_date)}.`
      : 'Final figures for a closed shift.',
);
const salesLines = computed(() => [
  { label: 'Sales orders', count: t.value.sales_orders_count, amount: t.value.total_sales, negative: false },
  { label: 'Sales invoices', count: t.value.invoices_count, amount: t.value.invoiced_total, negative: false },
  { label: 'Returns', count: t.value.returns_count, amount: t.value.returns_total, negative: true },
]);

const fmt = (n?: number | null) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (n: number) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
const signed = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${currency.value} ${fmt(Math.abs(n))}`;
const varianceClass = (n: number) =>
  n === 0
    ? 'border-border bg-muted/40 text-foreground'
    : n > 0
      ? 'border-success/25 bg-success/10 text-success'
      : 'border-danger/25 bg-danger/10 text-danger';
const parseTs = (ts: string | null) => (ts ? new Date(ts.replace(' ', 'T')) : null);
const formatDateTime = (ts: string | null) => {
  const d = parseTs(ts);
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '—';
};
const formatDate = (s: string) => {
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    report.value = isSummary.value
      ? await api.getShiftSummary((route.query.opening as string) || undefined)
      : await api.getClosingReport(route.params.name as string);
  } catch (e: any) {
    report.value = null;
    error.value = e?.message || 'Could not load the report.';
  } finally {
    loading.value = false;
  }
};

const printPdf = () => {
  if (!report.value) return;
  if (isSummary.value) api.downloadPdf('Van Shift Opening', report.value.shift.opening_shift, 'Van Shift Summary');
  else api.downloadPdf('Van Shift Closing', report.value.shift.closing_shift!, 'Van Shift Closing Report');
};

watch(() => route.fullPath, load, { immediate: true });
</script>
