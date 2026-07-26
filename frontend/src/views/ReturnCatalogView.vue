<template>
  <WorkspacePage back eyebrow="Process return" title="Select items" :description="customerName ? `Returning from ${customerName}` : 'Choose items to return.'" width="default">
    <div class="space-y-4 pb-28">
      <div class="sticky top-[60px] z-30 -mx-1 px-1 pb-1">
        <SearchBar v-model="search" placeholder="Search items…" />
      </div>

      <AppAlert v-if="error" tone="danger" :message="error" />
      <SkeletonList v-if="loading" :rows="5" height="5rem" />
      <EmptyState v-else-if="!items.length" icon="package" title="No items found" description="Adjust your search." />

      <div v-else class="space-y-2.5">
        <AppCard v-for="item in items" :key="item.item_code" padding="sm">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0 flex-1">
              <p class="font-semibold text-foreground">{{ item.item_name }}</p>
              <p class="text-xs text-muted">{{ item.item_code }}</p>
              <p class="mt-1.5 text-sm">
                <span class="text-xs text-muted">Credit rate: </span>
                <span v-if="itemPrice(item) !== null" class="tnum font-bold text-foreground">{{ currency }} {{ itemPrice(item)?.toFixed(2) }}</span>
                <span v-else class="text-xs font-medium text-subtle">Unavailable</span>
              </p>
            </div>
            <QtyStepper :model-value="getQty(item.item_code)" @change="(d: number) => (d > 0 ? add(item) : update(item.item_code, -1))" />
          </div>
        </AppCard>
      </div>

      <StickyBar v-if="cartCount">
        <button
          class="focus-ring flex w-full items-center justify-between gap-3 rounded-2xl bg-danger px-4 py-1.5 text-danger-fg"
          @click="$router.push({ name: 'return-cart' })"
        >
          <span class="text-left">
            <span class="block text-[11px] font-semibold uppercase tracking-wide opacity-80">Return total</span>
            <span class="tnum block text-lg font-bold leading-tight">{{ currency }} {{ total }}</span>
          </span>
          <span class="flex items-center gap-1 text-base font-bold">Review <AppIcon name="arrow-right" :size="18" /></span>
        </button>
      </StickyBar>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api/frappe';
import type { Item } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppAlert, AppIcon, SearchBar, QtyStepper, SkeletonList, EmptyState, StickyBar } from '../components/ui';

const store = useSessionStore();
const route = useRoute();
const router = useRouter();
const customerParam = route.query.customer as string | undefined;
const customerNameParam = route.query.customer_name as string | undefined;

const search = ref('');
const items = ref<Item[]>([]);
const loading = ref(true);
const error = ref('');
const currency = computed(() => store.currencyDisplay);
const cartCount = computed(() => store.returnCartCount);
const total = computed(() => store.returnCartTotal.toFixed(2));

const loadItems = async () => {
  loading.value = true;
  error.value = '';
  try {
    items.value = await api.listItems(search.value, store.customer?.name);
  } catch (e: any) {
    error.value = e?.message || 'Failed to load items';
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  if (customerParam && customerNameParam) {
    store.setCustomer({ name: customerParam, customer_name: customerNameParam, customer_group: '', territory: '' });
  }
  if (!store.customer) {
    router.push({ name: 'customers', query: { redirect: 'return' } });
    return;
  }
  loadItems();
});

watch(search, () => {
  clearTimeout(timer);
  timer = window.setTimeout(loadItems, 300);
});
let timer = window.setTimeout(() => {}, 0);

const add = (item: Item) => store.addToReturnCart(item);
const update = (itemCode: string, delta: number) => store.updateReturnQty(itemCode, delta);
const getQty = (itemCode: string) => store.returnCart.find((line) => line.item.item_code === itemCode)?.qty || 0;

const customerName = computed(() => store.customer?.customer_name || customerNameParam || '');
const itemPrice = (item: Item) => item.price_list_rate ?? item.standard_rate ?? 0;
</script>
