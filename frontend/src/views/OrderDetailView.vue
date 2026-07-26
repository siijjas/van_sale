<template>
  <WorkspacePage back eyebrow="Order detail" :title="order ? order.name : 'Sales Order'" :description="order ? order.customer_name : 'Inspect order lines and actions.'" width="default">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="reload">Refresh</AppButton>
    </template>

    <SkeletonList v-if="loading" :rows="3" height="6rem" />
    <AppAlert v-else-if="error" tone="danger" :message="error" />

    <div v-else-if="order" class="space-y-4 pb-28">
      <!-- Summary -->
      <AppCard>
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-[11px] font-bold uppercase tracking-wide text-muted">Customer</p>
            <p class="truncate text-lg font-bold text-foreground">{{ order.customer_name }}</p>
            <p class="text-xs text-muted">{{ order.customer }} • {{ order.transaction_date }}</p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <StatusBadge :status="order.status" />
            <StatusBadge :tone="docTone(order.docstatus)" :dot="false">{{ docLabel(order.docstatus) }}</StatusBadge>
          </div>
        </div>
        <div class="mt-4 space-y-2 border-t border-line pt-4">
          <div class="flex items-center justify-between text-base font-bold text-foreground">
            <span>Grand total</span><span class="tnum">{{ currency }} {{ fmt(order.grand_total) }}</span>
          </div>
          <div class="flex items-center justify-between text-xs text-muted">
            <span>Company</span><span>{{ order.company || '—' }}</span>
          </div>
          <div class="flex items-center justify-between text-xs text-muted">
            <span>Price list</span><span>{{ order.selling_price_list || '—' }}</span>
          </div>
        </div>
      </AppCard>

      <!-- Items -->
      <AppCard padding="none">
        <div class="border-b border-line px-4 py-3 text-xs font-bold uppercase tracking-wider text-muted">
          Items ({{ order.items.length }})
        </div>
        <div class="divide-y divide-line">
          <div v-for="line in order.items" :key="line.item_code" class="flex items-start justify-between gap-3 p-4">
            <div class="min-w-0">
              <p class="font-semibold text-foreground">{{ line.item_name }}</p>
              <p class="text-xs text-muted">{{ line.item_code }}<span v-if="line.stock_uom"> • {{ line.stock_uom }}</span></p>
              <p v-if="line.delivery_date" class="mt-1 text-[11px] text-subtle">Delivery {{ line.delivery_date }}</p>
            </div>
            <div class="shrink-0 text-right">
              <p class="tnum text-sm font-bold text-foreground">{{ currency }} {{ fmt(line.amount) }}</p>
              <p class="tnum text-xs text-muted">{{ line.qty }} × {{ currency }} {{ line.rate?.toFixed(2) }}</p>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- Secondary actions -->
      <div class="flex flex-wrap gap-2">
        <AppButton v-if="order.docstatus === 0" variant="secondary" size="sm" icon="edit" @click="editItems">Edit items</AppButton>
        <AppButton v-if="order.docstatus === 0" variant="secondary" size="sm" icon="plus" @click="addMoreItems">Add items</AppButton>
        <AppButton v-if="order.docstatus === 1" variant="secondary" size="sm" icon="printer" @click="printPdf">Print receipt</AppButton>
      </div>
    </div>

    <!-- Primary action -->
    <StickyBar v-if="order && order.docstatus === 0">
      <AppButton size="lg" block icon="check" :loading="submitting" @click="submitOrder">
        {{ submitting ? 'Submitting…' : 'Submit order' }}
      </AppButton>
    </StickyBar>
    <StickyBar v-else-if="order && order.docstatus === 1 && (order.per_billed ?? 0) < 100">
      <AppAlert v-if="invoiceCreated" tone="success" :message="`Invoice ${invoiceCreated} created`" class="mb-2" />
      <AppButton size="lg" block icon="file-text" :loading="invoicing" @click="createInvoice">
        {{ invoicing ? 'Creating invoice…' : 'Create sales invoice' }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api/frappe';
import type { SalesOrder } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, StatusBadge, SkeletonList, StickyBar } from '../components/ui';

const route = useRoute();
const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);
const orderId = route.params.name as string;

const order = ref<SalesOrder | null>(null);
const loading = ref(true);
const error = ref('');
const submitting = ref(false);
const invoicing = ref(false);
const invoiceCreated = ref('');

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    order.value = await api.getSalesOrder(orderId);
  } catch (e: any) {
    error.value = e?.message || 'Failed to load order';
  } finally {
    loading.value = false;
  }
};
onMounted(load);
const reload = () => load();

const submitOrder = async () => {
  if (!order.value || order.value.docstatus !== 0) return;
  submitting.value = true;
  error.value = '';
  try {
    order.value = await api.getSalesOrder(order.value.name);
    await api.submitSalesOrder(order.value.name);
    await load();
  } catch (e: any) {
    error.value = e?.message || 'Failed to submit order';
  } finally {
    submitting.value = false;
  }
};

const createInvoice = async () => {
  if (!order.value || order.value.docstatus !== 1) return;
  invoicing.value = true;
  error.value = '';
  try {
    invoiceCreated.value = await api.createSalesInvoice(order.value.name);
    await load();
  } catch (e: any) {
    error.value = e?.message || 'Failed to create invoice';
  } finally {
    invoicing.value = false;
  }
};

const printPdf = () => api.downloadPdf('Sales Order', orderId);

const seedCart = () => {
  if (!order.value) return;
  store.setCustomer({ name: order.value.customer, customer_name: order.value.customer_name, customer_group: '', territory: '' });
  store.setCurrentOrder(order.value.name);
  store.setCartFromOrder(order.value.items || []);
};
const editItems = () => {
  seedCart();
  router.push({ name: 'cart' });
};
const addMoreItems = () => {
  seedCart();
  router.push({ name: 'items', query: { customer: order.value!.customer, customer_name: order.value!.customer_name } });
};

const docLabel = (d: number) => (d === 0 ? 'Draft' : d === 1 ? 'Submitted' : d === 2 ? 'Cancelled' : 'Unknown');
const docTone = (d: number): 'success' | 'danger' | 'warning' => (d === 1 ? 'success' : d === 2 ? 'danger' : 'warning');
</script>
