<template>
  <div class="space-y-6">
    <!-- Fleet hero — same brand slab as the driver dashboard -->
    <div class="relative overflow-hidden rounded-3xl bg-[#0D3F41] p-5 text-white shadow-raised md:p-6">
      <div class="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/15"></div>
      <div class="relative">
        <p class="text-[13px] font-medium text-white/72">{{ greeting }}{{ firstName ? `, ${firstName}` : '' }}</p>
        <p class="mt-3.5 text-[11px] font-bold uppercase tracking-[0.1em] text-[#5FD6D0]">Fleet collected today</p>
        <p class="tnum mt-1 text-[38px] font-semibold leading-none tracking-tightest md:text-5xl">
          {{ currency }} {{ fmt(t?.collections) }}
        </p>
        <div class="mt-3 flex flex-wrap items-center gap-2.5 text-[13px] font-medium text-white/80">
          <span>{{ t?.payments_count || 0 }} payments</span>
          <span class="text-white/40">·</span>
          <span>{{ t?.orders_count || 0 }} orders</span>
          <span class="text-white/40">·</span>
          <span>{{ data?.vans.length || 0 }} vans</span>
        </div>
        <div class="mt-3.5 inline-flex items-center gap-2 rounded-full bg-white/12 px-3 py-1.5 text-xs font-semibold">
          <span class="h-[7px] w-[7px] rounded-full" :class="t?.open_shifts ? 'bg-success' : 'bg-white/50'"></span>
          {{ t?.open_shifts || 0 }} shift{{ t?.open_shifts === 1 ? '' : 's' }} open · {{ t?.closed_shifts || 0 }} closed
        </div>
      </div>
    </div>

    <slot />

    <SkeletonList v-if="loading" :rows="3" height="6rem" />
    <AppAlert v-else-if="error" tone="danger" :message="error" />

    <template v-else-if="data">
      <!-- Today across the fleet -->
      <section>
        <div class="mb-3 flex items-center justify-between">
          <p class="text-xs font-bold uppercase tracking-wider text-muted">Fleet today</p>
          <button class="text-xs font-semibold text-primary" @click="router.push({ name: 'reports' })">Full reports</button>
        </div>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <KpiTile label="Sales" :value="`${currency} ${fmt(t!.sales)}`" :sub="`${t!.orders_count} orders`" icon="cart" tone="primary" />
          <KpiTile label="Collections" :value="`${currency} ${fmt(t!.collections)}`" :sub="`${t!.payments_count} payments`" icon="wallet" tone="success" />
          <KpiTile label="Expenses" :value="`${currency} ${fmt(t!.expenses)}`" :sub="`${t!.expenses_count} entries`" icon="file-text" tone="warning" />
          <KpiTile label="Returns" :value="`${currency} ${fmt(t!.returns)}`" :sub="`${t!.returns_count} credit notes`" icon="rotate-ccw" tone="danger" />
          <KpiTile label="Cash on open shifts" :value="`${currency} ${fmt(t!.expected_cash_open)}`" :sub="`${t!.open_shifts || 0} vans on the road`" icon="banknote" tone="info" />
          <KpiTile label="Avg. order" :value="`${currency} ${fmt(t!.avg_order)}`" :sub="`Net ${currency} ${fmt(t!.net_sales)}`" icon="activity" tone="primary" />
        </div>
      </section>

      <!-- Needs attention -->
      <section v-if="data.alerts.length">
        <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Needs attention · {{ data.alerts.length }}</p>
        <div class="space-y-2">
          <AppAlert
            v-for="(a, i) in visibleAlerts"
            :key="`${a.kind}-${a.reference || a.driver}-${i}`"
            :tone="a.level"
            :title="a.title"
            :message="a.body"
          />
        </div>
        <button v-if="data.alerts.length > ALERT_LIMIT" class="mt-2 text-xs font-semibold text-primary" @click="showAllAlerts = !showAllAlerts">
          {{ showAllAlerts ? 'Show fewer' : `Show all ${data.alerts.length}` }}
        </button>
      </section>

      <!-- Vans -->
      <section>
        <div class="mb-3 flex items-center justify-between">
          <p class="text-xs font-bold uppercase tracking-wider text-muted">Vans</p>
          <button class="text-xs font-semibold text-primary" @click="router.push({ name: 'shift-reports' })">Shift reports</button>
        </div>
        <EmptyState v-if="!data.vans.length" icon="truck" title="No vans yet" description="Assign drivers to a Van Profile to see them here." />
        <div v-else class="grid gap-2.5 md:grid-cols-2">
          <AppCard v-for="v in data.vans" :key="v.driver" padding="sm" :interactive="Boolean(reportRoute(v))" @click="openVan(v)">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate font-semibold text-foreground">{{ v.driver_name }}</p>
                <p class="mt-0.5 truncate text-xs text-muted">{{ v.van_name }}{{ v.delivery_route ? ` · ${v.delivery_route}` : '' }}</p>
              </div>
              <StatusBadge :tone="STATUS[v.shift_status].tone" :dot="true">{{ statusLabel(v) }}</StatusBadge>
            </div>
            <div class="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div class="rounded-xl bg-muted/40 py-1.5">
                <p class="opacity-60">Sales</p>
                <p class="tnum font-semibold text-foreground">{{ fmt(v.sales) }}</p>
              </div>
              <div class="rounded-xl bg-muted/40 py-1.5">
                <p class="opacity-60">Collected</p>
                <p class="tnum font-semibold text-foreground">{{ fmt(v.collections) }}</p>
              </div>
              <div class="rounded-xl bg-muted/40 py-1.5">
                <template v-if="v.shift_status === 'open'">
                  <p class="opacity-60">Cash in hand</p>
                  <p class="tnum font-semibold text-foreground">{{ fmt(v.expected_cash) }}</p>
                </template>
                <template v-else-if="v.shift_status === 'closed'">
                  <p class="opacity-60">Variance</p>
                  <p class="tnum font-semibold" :class="varianceText(v.net_difference)">{{ signed(v.net_difference) }}</p>
                </template>
                <template v-else>
                  <p class="opacity-60">Expenses</p>
                  <p class="tnum font-semibold text-foreground">{{ fmt(v.expenses) }}</p>
                </template>
              </div>
            </div>
          </AppCard>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { ManagerDashboard, ManagerDashboardVan } from '../types';
import { AppAlert, AppCard, EmptyState, KpiTile, SkeletonList, StatusBadge } from './ui';

defineProps<{ greeting: string; firstName: string }>();

const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

const ALERT_LIMIT = 3;
const STATUS = {
  open: { tone: 'success', label: 'Shift open' },
  closed: { tone: 'neutral', label: 'Closed' },
  stale: { tone: 'warning', label: 'Stale shift' },
  none: { tone: 'neutral', label: 'Not started' },
} as const;

const data = ref<ManagerDashboard | null>(null);
const loading = ref(true);
const error = ref('');
const showAllAlerts = ref(false);

const t = computed(() => data.value?.totals);
const visibleAlerts = computed(() => (showAllAlerts.value ? data.value!.alerts : data.value!.alerts.slice(0, ALERT_LIMIT)));

const fmt = (n?: number | null) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const signed = (n: number | null) => (n ? `${n > 0 ? '+' : '−'}${fmt(Math.abs(n))}` : '0.00');
const varianceText = (n: number | null) => (!n ? 'text-foreground' : n > 0 ? 'text-success' : 'text-danger');
const time = (ts: string | null) => {
  const d = ts ? new Date(ts.replace(' ', 'T')) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '';
};
const statusLabel = (v: ManagerDashboardVan) => {
  const at = time(v.shift_since);
  if (v.shift_status === 'open' && at) return `Open since ${at}`;
  if (v.shift_status === 'closed' && at) return `Closed ${at}`;
  return STATUS[v.shift_status].label;
};

const reportRoute = (v: ManagerDashboardVan) => {
  if (v.shift_status === 'open' && v.opening_shift) return { name: 'shift-report-x', query: { opening: v.opening_shift } };
  if (v.shift_status === 'closed' && v.closing_shift) return { name: 'shift-report-y', params: { name: v.closing_shift } };
  return null;
};
const openVan = (v: ManagerDashboardVan) => {
  const to = reportRoute(v);
  if (to) router.push(to);
};

onMounted(async () => {
  try {
    data.value = await api.getManagerDashboard();
  } catch (e: any) {
    error.value = e?.message || 'Could not load the fleet dashboard.';
  } finally {
    loading.value = false;
  }
});
</script>
