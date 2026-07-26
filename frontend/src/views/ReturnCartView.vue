<template>
  <WorkspacePage back eyebrow="Review" title="Return summary" :description="customerName ? `From ${customerName}` : 'Confirm items being returned.'" width="default">
    <div class="space-y-4 pb-28">
      <AppCard class="bg-gradient-to-br from-danger to-danger/80 text-danger-fg" padding="lg">
        <p class="text-xs font-semibold uppercase tracking-wide opacity-80">Total credit issued</p>
        <p class="tnum text-3xl font-bold">{{ currency }} {{ total }}</p>
        <p class="mt-1 text-sm opacity-90">{{ cartCount }} item{{ cartCount !== 1 ? 's' : '' }}</p>
      </AppCard>

      <AppAlert v-if="error" tone="danger" :message="error" />

      <AppCard v-if="cart.length" padding="none">
        <div class="divide-y divide-line">
          <div v-for="line in cart" :key="line.item.item_code" class="flex items-center justify-between gap-3 p-4">
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-foreground">{{ line.item.item_name }}</p>
              <p class="mt-0.5 text-xs text-muted">{{ line.item.item_code }}</p>
              <p class="tnum mt-1 text-sm font-bold text-foreground">
                {{ currency }} {{ (line.qty * rate(line)).toFixed(2) }}
                <span class="font-medium text-muted">• {{ line.qty }} × {{ currency }} {{ rate(line).toFixed(2) }}</span>
              </p>
            </div>
            <QtyStepper :model-value="line.qty" @change="(d: number) => store.updateReturnQty(line.item.item_code, d)" />
          </div>
        </div>
      </AppCard>
      <EmptyState v-else icon="rotate-ccw" title="No items selected" description="Add items from the return catalog." />
    </div>

    <StickyBar v-if="cart.length">
      <AppButton variant="danger" size="lg" block icon="rotate-ccw" :loading="loading" @click="submit">
        {{ loading ? 'Processing…' : 'Process return credit' }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import type { CartLine } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, QtyStepper, EmptyState, StickyBar } from '../components/ui';

const store = useSessionStore();
const router = useRouter();

const cart = computed(() => store.returnCart);
const cartCount = computed(() => store.returnCartCount);
const total = computed(() => store.returnCartTotal.toFixed(2));
const currency = computed(() => store.currencyDisplay);
const customerName = computed(() => store.customer?.customer_name || '');

const loading = ref(false);
const error = ref('');
const rate = (line: CartLine) => line.item.price_list_rate || line.item.standard_rate || 0;

const submit = async () => {
  if (!store.customer || !cart.value.length) return;
  loading.value = true;
  error.value = '';
  try {
    const items = cart.value.map((line) => ({ item_code: line.item.item_code, qty: line.qty }));
    await api.createSalesReturn(store.customer.name, items);
    store.clearReturnCart();
    router.push({ name: 'ledger', query: { refresh: '1' } });
  } catch (e: any) {
    error.value = e?.message || 'Failed to process return. Check permissions and stock settings.';
  } finally {
    loading.value = false;
  }
};
</script>
