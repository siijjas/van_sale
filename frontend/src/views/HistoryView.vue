<template>
  <WorkspacePage eyebrow="Activity" title="Order history" description="Review recent orders and reopen them for follow-up." width="default">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="reload">Refresh</AppButton>
      <AppButton size="sm" icon="plus" @click="$router.push({ name: 'customers', query: { redirect: 'order' } })">New order</AppButton>
    </template>

    <div class="space-y-4">
      <div class="space-y-2.5">
        <SearchBar v-model="search" placeholder="Search by customer or order #…" />
        <div class="grid grid-cols-2 gap-2.5">
          <FormField label="From">
            <input v-model="fromDate" type="date" class="field-input" />
          </FormField>
          <FormField label="To">
            <input v-model="toDate" type="date" class="field-input" />
          </FormField>
        </div>
        <button
          v-if="search || fromDate || toDate"
          type="button"
          class="text-xs font-semibold text-primary"
          @click="clearFilters"
        >
          Clear filters
        </button>
      </div>

      <SkeletonList v-if="loading && !orders.length" :rows="5" />
      <EmptyState v-else-if="!orders.length" icon="receipt" title="No orders found" :description="hasFilters ? 'Try different search terms or dates.' : 'Orders you create will appear here.'">
        <template #action>
          <AppButton icon="plus" @click="$router.push({ name: 'customers', query: { redirect: 'order' } })">Create order</AppButton>
        </template>
      </EmptyState>
      <div v-else class="space-y-2.5">
        <AppCard v-for="order in orders" :key="order.name" interactive @click="openOrder(order.name)">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate font-bold text-foreground">{{ order.customer_name }}</p>
              <p class="mt-0.5 text-xs text-muted">{{ order.name }} • {{ order.transaction_date }}</p>
              <p class="tnum mt-2 text-lg font-bold text-foreground">{{ currency }} {{ fmt(order.grand_total) }}</p>
            </div>
            <StatusBadge :status="order.status" />
          </div>
        </AppCard>
        <AppButton v-if="hasMore" variant="secondary" block :loading="loadingMore" @click="loadMore">Load more</AppButton>
      </div>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { SalesOrder } from '../types';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, StatusBadge, SkeletonList, EmptyState, SearchBar, FormField } from '../components/ui';

const PAGE_LENGTH = 20;

const store = useSessionStore();
const router = useRouter();
const session = computed(() => store.session);
const currency = computed(() => store.currencyDisplay);
const orders = ref<SalesOrder[]>([]);
const loading = ref(true);
const loadingMore = ref(false);
const hasMore = ref(false);

const search = ref('');
const fromDate = ref('');
const toDate = ref('');
const hasFilters = computed(() => !!(search.value || fromDate.value || toDate.value));

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const load = async () => {
  if (!session.value) return;
  loading.value = true;
  try {
    const page = await api.recentOrders(session.value.user, {
      search: search.value,
      fromDate: fromDate.value || undefined,
      toDate: toDate.value || undefined,
      limitStart: 0,
      pageLength: PAGE_LENGTH,
    });
    orders.value = page;
    hasMore.value = page.length === PAGE_LENGTH;
  } finally {
    loading.value = false;
  }
};

const loadMore = async () => {
  if (!session.value) return;
  loadingMore.value = true;
  try {
    const page = await api.recentOrders(session.value.user, {
      search: search.value,
      fromDate: fromDate.value || undefined,
      toDate: toDate.value || undefined,
      limitStart: orders.value.length,
      pageLength: PAGE_LENGTH,
    });
    orders.value = [...orders.value, ...page];
    hasMore.value = page.length === PAGE_LENGTH;
  } finally {
    loadingMore.value = false;
  }
};

const reload = () => load();
const clearFilters = () => {
  search.value = '';
  fromDate.value = '';
  toDate.value = '';
};

onMounted(load);

let filterTimer = window.setTimeout(() => {}, 0);
watch([search, fromDate, toDate], () => {
  clearTimeout(filterTimer);
  filterTimer = window.setTimeout(load, 300);
});

const openOrder = (name: string) => router.push({ name: 'order-detail', params: { name } });
</script>
