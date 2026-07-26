<template>
  <WorkspacePage back :title="customerName ? 'Catalog' : 'Catalog'" :description="customerName ? `Ordering for ${customerName}` : 'Select items'" width="default">
    <div class="space-y-4 pb-28">
      <div class="sticky top-[60px] z-30 -mx-1 px-1 pb-1">
        <SearchBar v-model="search" placeholder="Search catalog…" />
      </div>

      <AppAlert v-if="error" tone="danger" :message="error" />
      <SkeletonList v-if="loading" :rows="6" height="5rem" />
      <EmptyState v-else-if="!items.length" icon="package" title="No items found" description="Adjust your search to find products." />

      <div v-else class="space-y-2.5">
        <AppCard v-for="item in items" :key="item.item_code" padding="sm">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0 flex-1">
              <p class="font-semibold leading-tight text-foreground">{{ item.item_name }}</p>
              <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <span class="tnum font-bold text-foreground">
                  <template v-if="itemPrice(item) !== null">{{ currency }} {{ itemPrice(item)?.toFixed(2) }}</template>
                  <span v-else class="font-medium text-subtle">N/A</span>
                </span>
                <span class="text-subtle">•</span>
                <span class="text-muted">{{ item.item_code }}</span>
              </div>
              <div class="mt-1.5">
                <StatusBadge v-if="hasQty(item) && item.actual_qty! <= 0" tone="danger" :dot="false">Out of stock</StatusBadge>
                <StatusBadge v-else-if="hasQty(item) && item.actual_qty! < 5" tone="warning" :dot="false">Only {{ item.actual_qty }} left</StatusBadge>
                <StatusBadge v-else-if="hasQty(item)" tone="success" :dot="false">{{ item.actual_qty }} available</StatusBadge>
              </div>
            </div>

            <!-- In-cart badge (tap to edit) -->
            <button
              v-if="getQty(item.item_code) > 0"
              type="button"
              class="flex shrink-0 items-center gap-1.5 rounded-2xl bg-primary/10 px-3 py-2 text-sm font-bold text-primary transition active:scale-95"
              @click="openSheet(item)"
            >
              <span class="tnum">× {{ getQty(item.item_code) }}</span>
              <AppIcon name="edit" :size="14" />
            </button>

            <!-- Add button -->
            <AppButton
              v-else
              variant="secondary"
              size="sm"
              icon="plus"
              :disabled="hasQty(item) && item.actual_qty! <= 0"
              @click="openSheet(item)"
            >
              Add
            </AppButton>
          </div>
        </AppCard>
      </div>

      <!-- Floating cart bar -->
      <StickyBar v-if="cartCount">
        <button
          class="focus-ring flex w-full items-center justify-between gap-3 rounded-2xl bg-primary px-4 py-1.5 text-primary-fg"
          @click="$router.push({ name: 'cart' })"
        >
          <span class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 text-sm font-bold">{{ cartCount }}</span>
            <span class="text-left">
              <span class="block text-[11px] font-semibold uppercase tracking-wide opacity-80">Cart total</span>
              <span class="tnum block text-lg font-bold leading-tight">{{ currency }} {{ total }}</span>
            </span>
          </span>
          <span class="flex items-center gap-1 text-base font-bold">Checkout <AppIcon name="arrow-right" :size="18" /></span>
        </button>
      </StickyBar>
    </div>

    <QtyInputSheet
      v-model="sheetOpen"
      :title="selectedItem?.item_name || ''"
      :subtitle="selectedItem?.item_code"
      :price="selectedItem ? `${currency} ${itemPrice(selectedItem)?.toFixed(2)}` : undefined"
      :max-qty="selectedItem?.actual_qty !== undefined ? selectedItem.actual_qty : undefined"
      :initial-qty="selectedItem ? getQty(selectedItem.item_code) : 0"
      :confirm-label="selectedItem && getQty(selectedItem.item_code) > 0 ? 'Update qty' : 'Add to order'"
      @confirm="onQtyConfirmed"
    />
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import * as api from '../api/frappe';
import type { Item } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppAlert, AppIcon, SearchBar, StatusBadge, SkeletonList, EmptyState, StickyBar, AppButton, QtyInputSheet } from '../components/ui';

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
const cartCount = computed(() => store.cartCount);
const total = computed(() => store.cartTotal.toFixed(2));

const sheetOpen = ref(false);
const selectedItem = ref<Item | null>(null);

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
    router.push({ name: 'customers' });
    return;
  }
  if (store.currentOrderName && store.cart.length === 0) {
    api.getSalesOrder(store.currentOrderName).then((order) => store.setCartFromOrder(order.items || []));
  }
  loadItems();
});

watch(search, () => {
  clearTimeout(timer);
  timer = window.setTimeout(loadItems, 300);
});
let timer = window.setTimeout(() => {}, 0);

function openSheet(item: Item) {
  if (hasQty(item) && item.actual_qty! <= 0 && getQty(item.item_code) === 0) return;
  selectedItem.value = item;
  sheetOpen.value = true;
}

function onQtyConfirmed(qty: number) {
  if (!selectedItem.value) return;
  store.setQty(selectedItem.value, qty);
}

function getQty(itemCode: string) {
  return store.cart.find((line) => line.item.item_code === itemCode)?.qty || 0;
}

const customerName = computed(() => store.customer?.customer_name || customerNameParam || '');
const itemPrice = (item: Item) => item.price_list_rate ?? item.standard_rate ?? 0;
const hasQty = (item: Item) => item.actual_qty !== undefined && item.actual_qty !== null;
</script>
