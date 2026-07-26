<template>
  <WorkspacePage eyebrow="Activity" title="Order history" description="Review recent orders and reopen them for follow-up." width="default">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="reload">Refresh</AppButton>
      <AppButton size="sm" icon="plus" @click="$router.push({ name: 'customers', query: { redirect: 'order' } })">New order</AppButton>
    </template>

    <SkeletonList v-if="loading" :rows="5" />
    <EmptyState v-else-if="!orders.length" icon="receipt" title="No orders found" description="Orders you create will appear here.">
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
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import type { SalesOrder } from '../types';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, StatusBadge, SkeletonList, EmptyState } from '../components/ui';

const store = useSessionStore();
const router = useRouter();
const session = computed(() => store.session);
const currency = computed(() => store.currencyDisplay);
const orders = ref<SalesOrder[]>([]);
const loading = ref(true);

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const load = async () => {
  if (!session.value) return;
  loading.value = true;
  orders.value = await api.recentOrders(session.value.user);
  loading.value = false;
};
const reload = () => load();
onMounted(load);

const openOrder = (name: string) => router.push({ name: 'order-detail', params: { name } });
</script>
