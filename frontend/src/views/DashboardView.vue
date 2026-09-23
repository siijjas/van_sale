<template>
  <WorkspacePage width="default">
    <div class="space-y-6">
      <!-- Greeting + hero collection KPI — flat brand slab, identical in both themes -->
      <div class="relative overflow-hidden rounded-3xl bg-[#0D3F41] p-5 text-white shadow-raised md:p-6">
        <div class="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/15"></div>
        <div class="relative">
          <p class="text-[13px] font-medium text-white/72">{{ greeting }}{{ firstName ? `, ${firstName}` : '' }}</p>
          <p class="mt-3.5 text-[11px] font-bold uppercase tracking-[0.1em] text-[#5FD6D0]">Collected today</p>
          <p class="tnum mt-1 text-[38px] font-semibold leading-none tracking-tightest md:text-5xl">
            {{ currency }} {{ fmt(dailySummary?.payments.total) }}
          </p>
          <div class="mt-3 flex items-center gap-2.5 text-[13px] font-medium text-white/80">
            <span>{{ dailySummary?.payments.count || 0 }} payments</span>
            <span class="text-white/40">·</span>
            <span>{{ dailySummary?.sales_orders.count || 0 }} orders</span>
            <span v-if="driverConfig?.delivery_route" class="text-white/40">·</span>
            <span v-if="driverConfig?.delivery_route">{{ driverConfig.delivery_route }}</span>
          </div>
          <div v-if="activeShift" class="mt-3.5 inline-flex items-center gap-2 rounded-full bg-white/12 px-3 py-1.5 text-xs font-semibold">
            <span class="h-[7px] w-[7px] rounded-full bg-success"></span>
            Shift open{{ shiftSince ? ` since ${shiftSince}` : '' }}
          </div>
        </div>
      </div>

      <AppAlert v-if="setupMessage" tone="warning" :message="setupMessage" />

      <!-- Quick actions -->
      <section>
        <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Quick actions</p>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
          <button
            v-for="a in actions"
            :key="a.label"
            class="focus-ring flex min-h-touch-xl flex-col items-start gap-3 rounded-3xl border border-line bg-card p-4 text-left shadow-card transition hover:border-line-strong hover:shadow-raised active:scale-[0.97]"
            @click="a.go"
          >
            <span class="flex h-11 w-11 items-center justify-center rounded-2xl" :class="a.accent">
              <AppIcon :name="a.icon" :size="22" />
            </span>
            <span class="text-sm font-bold text-foreground">{{ a.label }}</span>
          </button>
        </div>
      </section>

      <!-- Today's performance -->
      <section>
        <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Today's performance</p>
        <div class="grid grid-cols-2 gap-3">
          <KpiTile
            label="Sales"
            :value="dailySummary?.sales_orders.count || 0"
            :sub="`${currency} ${fmt(dailySummary?.sales_orders.total)}`"
            icon="cart"
            tone="primary"
            interactive
            @click="$router.push({ name: 'daily-log', params: { type: 'orders' } })"
          />
          <KpiTile
            label="Collections"
            :value="dailySummary?.payments.count || 0"
            :sub="`${currency} ${fmt(dailySummary?.payments.total)}`"
            icon="wallet"
            tone="success"
            interactive
            @click="$router.push({ name: 'daily-log', params: { type: 'payments' } })"
          />
        </div>
      </section>

      <!-- Recent activity -->
      <section>
        <div class="mb-3 flex items-center justify-between">
          <p class="text-xs font-bold uppercase tracking-wider text-muted">Recent activity</p>
          <button class="text-xs font-semibold text-primary" @click="$router.push({ name: 'history' })">View all</button>
        </div>
        <SkeletonList v-if="loading" :rows="3" />
        <EmptyState v-else-if="!orders.length" icon="receipt" title="No orders yet today" description="New orders you create will show up here." />
        <div v-else class="space-y-2.5">
          <AppCard
            v-for="order in orders"
            :key="order.name"
            padding="sm"
            interactive
            @click="openOrder(order.name)"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate font-semibold text-foreground">{{ order.customer_name }}</p>
                <p class="mt-0.5 text-xs text-muted">{{ order.name }}</p>
              </div>
              <div class="text-right">
                <p class="tnum text-sm font-bold text-foreground">{{ currency }} {{ fmt(order.grand_total) }}</p>
                <StatusBadge class="mt-1" :status="order.status" :dot="false" />
              </div>
            </div>
          </AppCard>
        </div>
      </section>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import * as api from '../api/frappe';
import type { SalesOrder, ActiveShift } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppAlert, AppIcon, KpiTile, StatusBadge, SkeletonList, EmptyState } from '../components/ui';

const store = useSessionStore();
const router = useRouter();
const route = useRoute();
const session = computed(() => store.session);
const driverConfig = computed(() => store.driverConfig);
const currency = computed(() => store.currencyDisplay);

const firstName = computed(() => session.value?.full_name?.split(' ')[0] || '');
const greeting = computed(() => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
});

const setupMessage = computed(() => {
  if (driverConfig.value) return '';
  if (route.query.setup === 'driver-profile') {
    return session.value?.is_manager
      ? 'Create and activate a driver profile before opening stock tools.'
      : 'Your account has no active driver profile yet. Ask a manager to assign one before using stock tools.';
  }
  return '';
});

const actions = computed(() => {
  const list = [
    { label: 'New Order', icon: 'cart', accent: 'bg-primary/12 text-primary', go: () => router.push({ name: 'customers', query: { redirect: 'order' } }) },
    { label: 'Payment', icon: 'wallet', accent: 'bg-success/12 text-success', go: () => router.push({ name: 'customers', query: { redirect: 'payment' } }) },
  ];
  if (driverConfig.value || store.isManager) {
    list.push({ label: 'Load Stock', icon: 'truck', accent: 'bg-warning/15 text-warning', go: () => router.push({ name: 'stock-transfer' }) });
  }
  list.push(
    { label: 'Return', icon: 'rotate-ccw', accent: 'bg-danger/12 text-danger', go: () => router.push({ name: 'customers', query: { redirect: 'return' } }) },
    { label: 'Expense', icon: 'file-text', accent: 'bg-info/12 text-info', go: () => router.push({ name: 'expenses' }) },
  );
  if (activeShift.value) {
    list.push({ label: 'Close Shift', icon: 'check-circle', accent: 'bg-primary/12 text-primary', go: () => router.push({ name: 'shift-close' }) });
  } else {
    list.push({ label: 'Open Shift', icon: 'play-circle', accent: 'bg-success/12 text-success', go: () => router.push({ name: 'shift-open' }) });
  }
  return list;
});

const orders = ref<SalesOrder[]>([]);
const dailySummary = ref<{ sales_orders: { count: number; total: number }; payments: { count: number; total: number } } | null>(null);
const activeShift = ref<ActiveShift | null>(null);
const loading = ref(true);

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shiftSince = computed(() => {
  const ts = activeShift.value?.period_start;
  if (!ts) return '';
  const d = new Date(ts.replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
});

onMounted(async () => {
  if (!session.value) return;
  try {
    const [ordersData, summaryData, shiftData] = await Promise.all([
      api.recentOrders(session.value.user),
      api.getDailySummary(),
      api.getActiveShift().catch(() => null),
    ]);
    orders.value = ordersData;
    dailySummary.value = summaryData;
    activeShift.value = shiftData;
  } finally {
    loading.value = false;
  }
});

const openOrder = (name: string) => router.push({ name: 'order-detail', params: { name } });
</script>
