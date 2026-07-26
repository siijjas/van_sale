<template>
  <WorkspacePage
    eyebrow="Stock monitor"
    :title="dashboard?.warehouse || driverConfig?.van_warehouse || 'Van warehouse'"
    description="Live van stock with low-stock alerts."
    width="default"
  >
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="refresh(true)">Refresh</AppButton>
    </template>

    <div class="space-y-4 pb-8">
      <AppAlert v-if="offlineSnapshot" tone="warning" message="Showing the last cached snapshot — live data is unavailable." />
      <AppAlert v-if="error" tone="danger" :message="error" />

      <AppAlert v-if="!driverConfig" tone="info" message="No active driver profile is assigned. Configure a profile before opening the stock dashboard." />

      <div v-if="dashboard" class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile label="Items" :value="dashboard.summary.item_count" icon="package" tone="primary" />
        <KpiTile label="Low stock" :value="dashboard.summary.low_stock_count" icon="alert" tone="warning" />
        <KpiTile label="Available" :value="dashboard.summary.total_available_qty.toFixed(0)" icon="boxes" tone="success" />
        <KpiTile label="Reserved" :value="dashboard.summary.total_reserved_qty.toFixed(0)" icon="clock" tone="info" />
      </div>

      <AppCard v-if="dashboard" padding="sm" class="space-y-3">
        <div class="flex items-center justify-between gap-3 px-1">
          <div>
            <p class="text-[11px] font-semibold uppercase tracking-wide text-muted">Source warehouse</p>
            <p class="text-sm font-bold text-foreground">{{ dashboard.source_warehouse }}</p>
          </div>
          <div class="text-right">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-muted">Low threshold</p>
            <p class="text-sm font-bold text-foreground">{{ dashboard.low_stock_threshold }}</p>
          </div>
        </div>
        <SearchBar v-model="search" placeholder="Filter stock by item…" />
      </AppCard>

      <SkeletonList v-if="loading" :rows="4" height="6rem" />
      <EmptyState v-else-if="dashboard && !filteredItems.length" icon="boxes" title="No matches" description="No stock matches the current filter." />

      <div v-else class="space-y-2.5">
        <AppCard v-for="item in filteredItems" :key="item.item_code">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="font-semibold text-foreground">{{ item.item_name }}</p>
              <p class="mt-0.5 text-xs text-muted">{{ item.item_code }} • {{ item.stock_uom }}</p>
            </div>
            <StatusBadge v-if="item.is_low_stock" tone="warning" :dot="false">Low</StatusBadge>
          </div>
          <div class="mt-4 grid grid-cols-3 gap-3">
            <div>
              <p class="text-[11px] uppercase tracking-wide text-muted">Available</p>
              <p class="tnum mt-0.5 font-bold text-foreground">{{ item.actual_qty.toFixed(2) }}</p>
            </div>
            <div>
              <p class="text-[11px] uppercase tracking-wide text-muted">Reserved</p>
              <p class="tnum mt-0.5 font-bold text-foreground">{{ item.reserved_qty.toFixed(2) }}</p>
            </div>
            <div>
              <p class="text-[11px] uppercase tracking-wide text-muted">Projected</p>
              <p class="tnum mt-0.5 font-bold text-foreground">{{ item.projected_qty.toFixed(2) }}</p>
            </div>
          </div>
        </AppCard>
      </div>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import * as api from '../api/frappe';
import type { DriverStockDashboard } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, KpiTile, SearchBar, StatusBadge, SkeletonList, EmptyState } from '../components/ui';

const CACHE_KEY = 'van-sale-driver-stock-cache';

const store = useSessionStore();
const driverConfig = computed(() => store.driverConfig);
const dashboard = ref<DriverStockDashboard | null>(null);
const loading = ref(true);
const error = ref('');
const offlineSnapshot = ref(false);
const search = ref('');

const filteredItems = computed(() => {
  const text = search.value.trim().toLowerCase();
  const items = dashboard.value?.items || [];
  if (!text) return items;
  return items.filter((item) => [item.item_code, item.item_name].some((value) => value.toLowerCase().includes(text)));
});

function readCachedSnapshot() {
  const cached = localStorage.getItem(CACHE_KEY);
  if (!cached) return null;
  try {
    return JSON.parse(cached) as DriverStockDashboard;
  } catch (_error) {
    return null;
  }
}

async function refresh(forceRefresh = false) {
  if (!driverConfig.value?.van_warehouse) {
    dashboard.value = null;
    error.value = 'No active driver profile is assigned to this user.';
    offlineSnapshot.value = false;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = '';
  offlineSnapshot.value = false;
  try {
    const data = await api.getDriverStockDashboard(forceRefresh);
    dashboard.value = data;
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch (err: any) {
    const cached = readCachedSnapshot();
    if (cached) {
      dashboard.value = cached;
      offlineSnapshot.value = true;
    } else {
      error.value = err?.message || 'Failed to load stock dashboard';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(() => refresh(false));
</script>
