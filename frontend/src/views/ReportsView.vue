<template>
  <WorkspacePage back eyebrow="Manager" title="Reports" description="Sales, collections, cash and stock movement across the fleet." width="wide">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="load">Refresh</AppButton>
      <AppButton variant="secondary" size="sm" icon="printer" :disabled="!report" @click="print">Print</AppButton>
    </template>

    <!-- Filters: one row above everything they drive -->
    <AppCard padding="sm" class="mb-5 space-y-3">
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="p in PRESETS"
          :key="p.value"
          type="button"
          class="focus-ring rounded-full px-3 py-1.5 text-xs font-semibold transition"
          :class="preset === p.value ? 'bg-primary text-primary-fg' : 'bg-card-muted text-muted hover:text-foreground'"
          @click="setPreset(p.value)"
        >{{ p.label }}</button>
      </div>
      <div class="grid grid-cols-2 gap-2 md:grid-cols-4">
        <FormField label="From">
          <BaseInput v-model="fromDate" type="date" @update:model-value="preset = 'custom'" />
        </FormField>
        <FormField label="To">
          <BaseInput v-model="toDate" type="date" @update:model-value="preset = 'custom'" />
        </FormField>
        <FormField label="Van">
          <BaseSelect v-model="vanProfile">
            <option value="">All vans</option>
            <option v-for="v in fleet?.vans || []" :key="v.van_profile" :value="v.van_profile">{{ v.van_name }}</option>
          </BaseSelect>
        </FormField>
        <FormField label="Driver">
          <BaseSelect v-model="driver">
            <option value="">All drivers</option>
            <option v-for="d in driverOptions" :key="d.driver" :value="d.driver">{{ d.driver_name }}</option>
          </BaseSelect>
        </FormField>
      </div>
    </AppCard>

    <SegmentedControl v-model="tab" :options="TABS" class="mb-5" />

    <SkeletonList v-if="loading && !report" :rows="4" height="6rem" />
    <AppAlert v-else-if="error" tone="danger" :message="error" />

    <div v-else-if="report" class="space-y-5 pb-8" :class="{ 'opacity-60': loading }">
      <p class="text-xs text-muted">
        {{ periodLabel }} · compared with {{ rangeLabel(report.period.previous_from, report.period.previous_to) }}
      </p>

      <!-- ── Overview ─────────────────────────────────────────── -->
      <template v-if="tab === 'overview'">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <KpiTile label="Sales" :value="money(t.sales)" :sub="deltaText('sales')" icon="cart" tone="primary" />
          <KpiTile label="Collections" :value="money(t.collections)" :sub="deltaText('collections')" icon="wallet" tone="success" />
          <KpiTile label="Expenses" :value="money(t.expenses)" :sub="deltaText('expenses')" icon="file-text" tone="warning" />
          <KpiTile label="Net cash" :value="money(t.net_cash)" :sub="deltaText('net_cash')" icon="banknote" tone="info" />
          <KpiTile label="Returns" :value="money(t.returns)" :sub="`${t.returns_count} credit notes · ${pct(t.return_rate)} of sales`" icon="rotate-ccw" tone="danger" />
          <KpiTile label="Avg. order" :value="money(t.avg_order)" :sub="`${t.orders_count} orders · ${deltaText('avg_order')}`" icon="activity" tone="primary" />
        </div>

        <AppCard v-if="report.daily.length > 1" padding="lg">
          <p class="mb-3 text-sm font-semibold text-foreground">Daily sales and collections</p>
          <TrendChart :rows="report.daily" :currency="currency" />
        </AppCard>

        <AppCard v-if="insights.length" padding="lg" class="space-y-3">
          <p class="text-sm font-semibold text-foreground">Insights</p>
          <div v-for="i in insights" :key="i.title" class="flex gap-3">
            <AppIcon :name="INSIGHT_ICON[i.level]" :size="16" class="mt-0.5 shrink-0" :class="INSIGHT_TEXT[i.level]" />
            <div>
              <p class="text-sm font-semibold text-foreground">{{ i.title }}</p>
              <p class="text-xs text-muted">{{ i.body }}</p>
            </div>
          </div>
        </AppCard>

        <AppCard padding="lg">
          <p class="mb-3 text-sm font-semibold text-foreground">Compared with the previous period</p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="text-xs text-muted">
                <tr>
                  <th class="pb-2 text-left font-semibold">Metric</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">This period</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">Previous</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">Change</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in report.comparison" :key="c.metric" class="border-t border-line">
                  <td class="py-2 text-foreground">{{ c.label }}</td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right text-foreground">{{ c.metric === 'orders_count' ? c.current : fmt(c.current) }}</td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right text-muted">{{ c.metric === 'orders_count' ? c.previous : fmt(c.previous) }}</td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right font-semibold" :class="deltaClass(c)">{{ formatDelta(c.delta_pct, c.delta) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>
      </template>

      <!-- ── Drivers ──────────────────────────────────────────── -->
      <template v-else-if="tab === 'drivers'">
        <EmptyState v-if="!report.by_driver.length" icon="users" title="No drivers" description="No driver matches these filters." />
        <AppCard v-for="d in report.by_driver" :key="d.driver" padding="lg" class="space-y-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate font-bold text-foreground">{{ d.driver_name }}</p>
              <p class="truncate text-xs text-muted">{{ d.van_name }}{{ d.delivery_route ? ` · ${d.delivery_route}` : '' }}</p>
            </div>
            <div class="text-right">
              <p class="tnum font-bold text-foreground">{{ money(d.sales) }}</p>
              <p class="text-xs text-muted">{{ pct(share(d.sales, t.sales)) }} of sales</p>
            </div>
          </div>
          <div class="h-1.5 overflow-hidden rounded-full bg-card-muted">
            <div class="h-full rounded-full bg-primary" :style="{ width: `${share(d.sales, maxDriverSales)}%` }"></div>
          </div>
          <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs md:grid-cols-4">
            <p class="flex justify-between"><span class="text-muted">Orders</span><span class="tnum font-semibold text-foreground">{{ d.orders_count }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Avg. order</span><span class="tnum font-semibold text-foreground">{{ fmt(d.avg_order) }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Returns</span><span class="tnum font-semibold text-foreground">{{ fmt(d.returns) }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Collected</span><span class="tnum font-semibold text-foreground">{{ fmt(d.collections) }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Expenses</span><span class="tnum font-semibold text-foreground">{{ fmt(d.expenses) }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Net cash</span><span class="tnum font-semibold text-foreground">{{ fmt(d.net_cash) }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Shifts</span><span class="tnum font-semibold text-foreground">{{ d.shifts_count }}</span></p>
            <p class="flex justify-between"><span class="text-muted">Variance</span><span class="tnum font-semibold" :class="signClass(d.variance)">{{ signed(d.variance) }}</span></p>
          </div>
        </AppCard>
      </template>

      <!-- ── Items ────────────────────────────────────────────── -->
      <template v-else-if="tab === 'items'">
        <AppCard padding="lg" class="space-y-3">
          <p class="text-sm font-semibold text-foreground">By item group</p>
          <p v-if="!report.item_groups.length" class="text-sm text-muted">Nothing sold in this period.</p>
          <div v-for="g in report.item_groups" :key="g.item_group" class="space-y-1">
            <div class="flex items-center justify-between text-sm">
              <span class="text-foreground">{{ g.item_group }} <span class="text-xs text-subtle">· {{ g.items }} items</span></span>
              <span class="tnum shrink-0 whitespace-nowrap font-semibold text-foreground">{{ money(g.net_amount) }}</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-card-muted">
              <div class="h-full rounded-full bg-primary" :style="{ width: `${share(g.net_amount, report.item_groups[0].net_amount)}%` }"></div>
            </div>
          </div>
        </AppCard>

        <AppCard padding="lg" class="space-y-3">
          <div>
            <p class="text-sm font-semibold text-foreground">Items</p>
            <p class="text-xs text-muted">Net of returns, in stock UOM. Amounts are after order discounts, before tax.</p>
          </div>
          <p v-if="!report.items.length" class="text-sm text-muted">Nothing sold in this period.</p>
          <div class="overflow-x-auto">
            <table v-if="report.items.length" class="w-full text-sm">
              <thead class="text-xs text-muted">
                <tr>
                  <th class="pb-2 text-left font-semibold">Item</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">Sold</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">Returned</th>
                  <th class="whitespace-nowrap pb-2 pl-3 text-right font-semibold">Net amount</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="i in visibleItems" :key="i.item_code" class="border-t border-line">
                  <td class="py-2">
                    <p class="text-foreground">{{ i.item_name || i.item_code }}</p>
                    <p class="text-xs text-subtle">{{ i.item_code }}</p>
                  </td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right text-foreground">{{ qty(i.sold_qty) }}<p class="text-xs text-muted">{{ i.uom }}</p></td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right" :class="i.returned_qty ? 'text-danger' : 'text-subtle'">{{ qty(i.returned_qty) }}</td>
                  <td class="tnum whitespace-nowrap py-2 pl-3 text-right font-semibold text-foreground">{{ fmt(i.net_amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <button v-if="report.items.length > ITEM_LIMIT" class="text-xs font-semibold text-primary" @click="showAllItems = !showAllItems">
            {{ showAllItems ? 'Show top items only' : `Show all ${report.items.length} items` }}
          </button>
        </AppCard>

        <AppCard padding="lg" class="space-y-2">
          <p class="mb-1 text-sm font-semibold text-foreground">Top customers</p>
          <p v-if="!report.customers.length" class="text-sm text-muted">No orders in this period.</p>
          <div v-for="c in report.customers" :key="c.customer" class="flex items-center justify-between gap-3 text-sm">
            <span class="min-w-0 truncate text-foreground">{{ c.customer_name || c.customer }} <span class="text-xs text-subtle">· {{ c.orders_count }} orders</span></span>
            <span class="tnum shrink-0 whitespace-nowrap font-semibold text-foreground">{{ money(c.sales) }}</span>
          </div>
        </AppCard>
      </template>

      <!-- ── Cash ─────────────────────────────────────────────── -->
      <template v-else-if="tab === 'cash'">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <KpiTile label="Collections" :value="money(t.collections)" :sub="`${t.payments_count} payments`" icon="wallet" tone="success" />
          <KpiTile label="Expenses" :value="money(t.expenses)" :sub="`${t.expenses_count} entries`" icon="file-text" tone="warning" />
          <KpiTile label="Net cash" :value="money(t.net_cash)" sub="Collections − expenses" icon="banknote" tone="info" />
          <KpiTile label="Cash variance" :value="signedMoney(t.variance)" :sub="`${t.variance_shifts} of ${t.shifts_count} shifts off`" icon="alert" :tone="t.variance < 0 ? 'danger' : 'primary'" />
        </div>

        <div class="grid gap-5 md:grid-cols-2">
          <AppCard padding="lg" class="space-y-3">
            <p class="text-sm font-semibold text-foreground">Collections by mode</p>
            <p v-if="!report.collections_by_mode.length" class="text-sm text-muted">No collections.</p>
            <div v-for="m in report.collections_by_mode" :key="m.mode_of_payment" class="space-y-1">
              <div class="flex items-center justify-between text-sm">
                <span class="min-w-0 truncate text-foreground">{{ m.mode_of_payment }} <span class="text-xs text-subtle">· {{ m.count }}</span></span>
                <span class="tnum shrink-0 whitespace-nowrap font-semibold text-foreground">{{ money(m.amount) }}</span>
              </div>
              <div class="h-1.5 overflow-hidden rounded-full bg-card-muted">
                <div class="h-full rounded-full bg-primary" :style="{ width: `${share(m.amount, t.collections)}%` }"></div>
              </div>
            </div>
          </AppCard>

          <AppCard padding="lg" class="space-y-3">
            <p class="text-sm font-semibold text-foreground">Expenses by type</p>
            <p v-if="!report.expenses_by_type.length" class="text-sm text-muted">No expenses.</p>
            <div v-for="e in report.expenses_by_type" :key="e.expense_type" class="space-y-1">
              <div class="flex items-center justify-between text-sm">
                <span class="text-foreground">{{ e.expense_type }} <span class="text-xs text-subtle">· {{ e.count }}</span></span>
                <span class="tnum shrink-0 whitespace-nowrap font-semibold text-foreground">{{ money(e.amount) }}</span>
              </div>
              <div class="h-1.5 overflow-hidden rounded-full bg-card-muted">
                <div class="h-full rounded-full bg-primary" :style="{ width: `${share(e.amount, t.expenses)}%` }"></div>
              </div>
            </div>
          </AppCard>
        </div>
      </template>

      <!-- ── Shifts ───────────────────────────────────────────── -->
      <template v-else-if="tab === 'shifts'">
        <EmptyState v-if="!report.shifts.length" icon="receipt" title="No closed shifts" description="No shift was closed in this period." />
        <AppCard
          v-for="s in report.shifts"
          :key="s.name"
          padding="sm"
          interactive
          @click="router.push({ name: 'shift-report-y', params: { name: s.name } })"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate font-semibold text-foreground">{{ s.driver_name }} · {{ shortDate(s.shift_date) }}</p>
              <p class="mt-0.5 truncate text-xs text-muted">{{ s.van_name ? `${s.van_name} · ` : '' }}Sales {{ fmt(s.total_sales) }} · Collected {{ fmt(s.total_collections) }}</p>
            </div>
            <div class="shrink-0 text-right">
              <p class="tnum text-sm font-bold" :class="signClass(s.net_difference)">{{ signed(s.net_difference) }}</p>
              <p class="text-xs text-muted">{{ Math.abs(s.net_difference) >= 0.005 ? 'variance' : 'balanced' }}</p>
            </div>
          </div>
        </AppCard>
      </template>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { FleetOptions, FleetTotals, PeriodComparisonRow, PeriodReport } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import TrendChart from '../components/TrendChart.vue';
import { printPeriodReport } from '../utils/printPeriodReport';
import {
  AppAlert, AppButton, AppCard, AppIcon, BaseInput, BaseSelect, EmptyState, FormField, KpiTile, SegmentedControl, SkeletonList,
} from '../components/ui';

type Preset = 'today' | 'yesterday' | 'last7' | 'month' | 'last_month' | 'custom';
type Tab = 'overview' | 'drivers' | 'items' | 'cash' | 'shifts';

const PRESETS: { value: Preset; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'last7', label: 'Last 7 days' },
  { value: 'month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'custom', label: 'Custom' },
];
const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: 'Overview' },
  { value: 'drivers', label: 'Drivers' },
  { value: 'items', label: 'Items' },
  { value: 'cash', label: 'Cash' },
  { value: 'shifts', label: 'Shifts' },
];
const ITEM_LIMIT = 15;
const INSIGHT_ICON = { positive: 'check-circle', warning: 'alert', info: 'info' } as const;
const INSIGHT_TEXT = { positive: 'text-success', warning: 'text-warning', info: 'text-info' } as const;

const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

// Local calendar dates, not UTC — toISOString() would shift the day near midnight.
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

const preset = ref<Preset>('month');
const fromDate = ref('');
const toDate = ref('');
const driver = ref('');
const vanProfile = ref('');
const tab = ref<Tab>('overview');
const fleet = ref<FleetOptions | null>(null);
const report = ref<PeriodReport | null>(null);
const loading = ref(false);
const error = ref('');
const showAllItems = ref(false);

const setPreset = (p: Preset) => {
  preset.value = p;
  const today = new Date();
  const ranges: Record<Exclude<Preset, 'custom'>, [Date, Date]> = {
    today: [today, today],
    yesterday: [addDays(today, -1), addDays(today, -1)],
    last7: [addDays(today, -6), today],
    month: [new Date(today.getFullYear(), today.getMonth(), 1), today],
    last_month: [new Date(today.getFullYear(), today.getMonth() - 1, 1), new Date(today.getFullYear(), today.getMonth(), 0)],
  };
  if (p === 'custom') return;
  [fromDate.value, toDate.value] = ranges[p].map(iso);
};
setPreset('month');

const driverOptions = computed(() =>
  (fleet.value?.drivers || []).filter((d) => !vanProfile.value || d.van_profile === vanProfile.value),
);
watch(vanProfile, () => {
  if (driver.value && !driverOptions.value.some((d) => d.driver === driver.value)) driver.value = '';
});

const t = computed(() => report.value!.totals);
const maxDriverSales = computed(() => Math.max(0, ...(report.value?.by_driver || []).map((d) => d.sales)));
const visibleItems = computed(() => (showAllItems.value ? report.value!.items : report.value!.items.slice(0, ITEM_LIMIT)));

const fmt = (n?: number | null) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (n?: number | null) => `${currency.value} ${fmt(n)}`;
const qty = (n: number) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
const pct = (n: number) => `${Math.round(n || 0)}%`;
const share = (part: number, whole: number) => (whole > 0 ? Math.max(0, Math.min(100, (part / whole) * 100)) : 0);
const signed = (n: number) => (Math.abs(n) < 0.005 ? '0.00' : `${n > 0 ? '+' : '−'}${fmt(Math.abs(n))}`);
const signedMoney = (n: number) => (Math.abs(n) < 0.005 ? money(0) : `${n > 0 ? '+' : '−'}${money(Math.abs(n))}`);
const signClass = (n: number) => (Math.abs(n) < 0.005 ? 'text-foreground' : n > 0 ? 'text-success' : 'text-danger');
const parseDate = (s: string) => new Date(`${s}T00:00:00`);
const shortDate = (s: string) => parseDate(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const rangeLabel = (a: string, b: string) => (a === b ? shortDate(a) : `${shortDate(a)} – ${shortDate(b)}`);
const periodLabel = computed(() => (report.value ? rangeLabel(report.value.period.from_date, report.value.period.to_date) : ''));

const formatDelta = (p: number | null, delta: number) => {
  if (p === null) return Math.abs(delta) < 0.005 ? '—' : 'new';
  if (Math.abs(p) > 999) return p > 0 ? '>+999%' : '<−999%';
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${Math.abs(p).toFixed(Math.abs(p) < 10 ? 1 : 0)}%`;
};
// Up is good for everything except spending and returns.
const LOWER_IS_BETTER = new Set<keyof FleetTotals>(['expenses', 'returns']);
const deltaClass = (c: PeriodComparisonRow) => {
  if (Math.abs(c.delta) < 0.005) return 'text-muted';
  const good = LOWER_IS_BETTER.has(c.metric) ? c.delta < 0 : c.delta > 0;
  return good ? 'text-success' : 'text-danger';
};
const deltaText = (metric: keyof FleetTotals) => {
  const c = report.value?.comparison.find((r) => r.metric === metric);
  return c ? `${formatDelta(c.delta_pct, c.delta)} vs previous` : '';
};

type Insight = { level: 'positive' | 'warning' | 'info'; title: string; body: string };
const insights = computed<Insight[]>(() => {
  const r = report.value;
  if (!r) return [];
  const out: Insight[] = [];
  const tt = r.totals;
  const active = r.by_driver.filter((d) => d.sales > 0);
  if (active.length > 1) {
    const top = active[0];
    out.push({ level: 'positive', title: `${top.driver_name} led sales`, body: `${money(top.sales)} — ${pct(share(top.sales, tt.sales))} of the fleet's sales, over ${top.orders_count} orders.` });
  }
  if (tt.sales > 0) {
    const ratio = (tt.collections / tt.sales) * 100;
    out.push({
      level: ratio < 80 ? 'warning' : 'info',
      title: 'Collections against sales',
      body: `Collected ${pct(ratio)} of the period's sales value.${ratio < 80 ? ' Credit is building up — check customer balances.' : ''}`,
    });
  }
  if (tt.returns > 0) {
    out.push({
      level: tt.return_rate >= 10 ? 'warning' : 'info',
      title: 'Returns',
      body: `${money(tt.returns)} returned across ${tt.returns_count} credit notes — ${pct(tt.return_rate)} of sales.${tt.return_rate >= 10 ? ' That is high; review the return reasons.' : ''}`,
    });
  }
  if (tt.collections > 0 && tt.expenses > tt.collections * 0.2) {
    out.push({ level: 'warning', title: 'Expenses are high', body: `Route expenses of ${money(tt.expenses)} are ${pct((tt.expenses / tt.collections) * 100)} of collections.` });
  }
  if (tt.variance_shifts > 0) {
    out.push({
      level: 'warning',
      title: 'Cash variances',
      body: `${tt.variance_shifts} of ${tt.shifts_count} closed shifts did not balance, netting ${signedMoney(tt.variance)}. See the Shifts tab.`,
    });
  }
  const busiest = [...r.daily].sort((a, b) => b.sales - a.sales)[0];
  if (r.daily.length > 1 && busiest?.sales > 0) {
    out.push({ level: 'info', title: 'Busiest day', body: `${shortDate(busiest.date)} with ${money(busiest.sales)} in sales.` });
  }
  if (r.items[0]?.net_amount > 0) {
    const top = r.items[0];
    out.push({ level: 'info', title: 'Top item', body: `${top.item_name || top.item_code}: ${qty(top.net_qty)} ${top.uom} for ${money(top.net_amount)}.` });
  }
  return out;
});

let requestId = 0;
const load = async () => {
  if (!fromDate.value || !toDate.value) return;
  const id = ++requestId;
  loading.value = true;
  error.value = '';
  try {
    const data = await api.getPeriodReport(fromDate.value, toDate.value, driver.value || undefined, vanProfile.value || undefined);
    if (id === requestId) report.value = data;
  } catch (e: any) {
    if (id === requestId) error.value = e?.message || 'Could not load the report.';
  } finally {
    if (id === requestId) loading.value = false;
  }
};

const print = () => {
  if (!report.value) return;
  const van = fleet.value?.vans.find((v) => v.van_profile === vanProfile.value)?.van_name;
  const drv = fleet.value?.drivers.find((d) => d.driver === driver.value)?.driver_name;
  printPeriodReport(report.value, {
    currency: currency.value,
    periodLabel: periodLabel.value,
    previousLabel: rangeLabel(report.value.period.previous_from, report.value.period.previous_to),
    scope: [van || 'All vans', drv || 'All drivers'].join(' · '),
    formatDelta,
  });
};

watch([fromDate, toDate, driver, vanProfile], load);
onMounted(async () => {
  load();
  try {
    fleet.value = await api.getFleet();
  } catch {
    // Filters just stay at "All" — the report itself still loads.
  }
});
</script>
