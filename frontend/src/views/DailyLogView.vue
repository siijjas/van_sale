<template>
  <WorkspacePage back eyebrow="Daily log" :title="title" :description="isPayments ? `Today's collections and payment-mode breakdown.` : `Today's sales activity.`" width="default">
    <SkeletonList v-if="loading" :rows="4" height="5rem" />

    <div v-else class="space-y-4">
      <!-- Payment summary -->
      <AppCard v-if="isPayments && items.length" class="bg-gradient-to-br from-success to-success/80 text-success-fg" padding="lg">
        <p class="text-xs font-semibold uppercase tracking-wide opacity-80">Total collection</p>
        <p class="tnum text-3xl font-bold">{{ currency }} {{ fmt(totalCollection) }}</p>
        <div class="mt-4 grid grid-cols-2 gap-2">
          <div v-for="(amount, mode) in collectionBreakdown" :key="mode" class="rounded-2xl bg-white/15 px-3 py-2">
            <p class="truncate text-xs font-medium opacity-80">{{ mode }}</p>
            <p class="tnum text-sm font-bold">{{ currency }} {{ fmt(amount) }}</p>
          </div>
        </div>
      </AppCard>

      <EmptyState v-if="!items.length" :icon="isPayments ? 'wallet' : 'receipt'" title="Nothing today yet" :description="`No ${isPayments ? 'payments' : 'orders'} recorded for today.`" />

      <div v-else class="space-y-2.5">
        <AppCard v-for="item in items" :key="item.name" interactive @click="openDetail(item)">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate font-bold text-foreground">{{ item.customer_name || item.party_name }}</p>
              <p class="mt-0.5 text-xs text-muted">{{ item.name }}</p>
              <p class="mt-2 text-xs text-subtle">{{ formatDate(item.transaction_date || item.posting_date) }}</p>
            </div>
            <div class="flex flex-col items-end gap-1.5">
              <p class="tnum text-base font-bold text-foreground">{{ currency }} {{ fmt(item.grand_total || item.paid_amount) }}</p>
              <StatusBadge :status="item.status" :dot="false" />
              <template v-if="!isPayments">
                <StatusBadge :tone="invoiceStatus(item).tone" :dot="false">{{ invoiceStatus(item).label }}</StatusBadge>
                <StatusBadge :status="paymentStatus(item).label" :dot="false">{{ paymentStatus(item).label }}</StatusBadge>
              </template>
              <StatusBadge v-if="isPayments && item.mode_of_payment" tone="neutral" :dot="false">{{ item.mode_of_payment }}</StatusBadge>
            </div>
          </div>
        </AppCard>
      </div>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import { getDailyLog } from '../api/frappe';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, StatusBadge, SkeletonList, EmptyState } from '../components/ui';

const route = useRoute();
const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

const type = computed(() => route.params.type as string);
const isPayments = computed(() => type.value === 'payments');
const title = computed(() => (isPayments.value ? "Today's payments" : "Today's orders"));
const doctype = computed(() => (isPayments.value ? 'Payment Entry' : 'Sales Order'));

const items = ref<any[]>([]);
const loading = ref(true);

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const invoiceStatus = (item: any): { label: string; tone: 'success' | 'warning' | 'neutral' } => {
  const perBilled = item.per_billed || 0;
  if (perBilled >= 99.99) return { label: 'Invoiced', tone: 'success' };
  if (perBilled > 0) return { label: 'Partially Invoiced', tone: 'warning' };
  return { label: 'Not Invoiced', tone: 'neutral' };
};

const paymentStatus = (item: any): { label: string } => {
  // Once invoiced, the invoice's own outstanding_amount is the source of
  // truth — a mark-as-paid invoice settles there, not as advance_paid on the
  // Sales Order itself, so an order can be fully paid while advance_paid
  // stays 0.
  const invoicedTotal = item.invoiced_total || 0;
  if (invoicedTotal > 0) {
    const outstanding = item.invoiced_outstanding || 0;
    if (outstanding <= 0.01) return { label: 'Paid' };
    if (outstanding < invoicedTotal - 0.01) return { label: 'Partly Paid' };
    return { label: 'Unpaid' };
  }
  const grandTotal = item.grand_total || 0;
  const advancePaid = item.advance_paid || 0;
  if (grandTotal > 0 && advancePaid >= grandTotal - 0.01) return { label: 'Paid' };
  if (advancePaid > 0) return { label: 'Partly Paid' };
  return { label: 'Unpaid' };
};

const totalCollection = computed(() =>
  isPayments.value ? items.value.reduce((sum, item) => sum + (item.paid_amount || 0), 0) : 0,
);
const collectionBreakdown = computed(() => {
  if (!isPayments.value) return {} as Record<string, number>;
  return items.value.reduce((acc, item) => {
    const mode = item.mode_of_payment || 'Unknown';
    acc[mode] = (acc[mode] || 0) + (item.paid_amount || 0);
    return acc;
  }, {} as Record<string, number>);
});

const fetchLog = async () => {
  loading.value = true;
  items.value = [];
  try {
    items.value = await getDailyLog(doctype.value);
  } finally {
    loading.value = false;
  }
};
onMounted(fetchLog);
watch(() => route.params.type, fetchLog);

const openDetail = (item: any) => {
  if (type.value === 'orders') router.push({ name: 'order-detail', params: { name: item.name } });
  else router.push({ name: 'payment-detail', params: { name: item.name } });
};

const formatDate = (date: string) => (date ? new Date(date).toLocaleDateString() : '');
</script>
