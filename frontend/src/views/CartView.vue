<template>
  <WorkspacePage back title="Review order" description="Check items and totals before confirming." width="default">
    <template #actions>
      <AppButton v-if="cart.length" variant="ghost" size="sm" icon="trash" @click="clear">Clear</AppButton>
    </template>

    <div class="space-y-4 pb-32">
      <AppAlert v-if="!customer" tone="warning" message="Select a customer first." />

      <!-- Customer -->
      <AppCard v-if="customer" padding="sm">
        <div class="flex items-center gap-3">
          <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-sm font-bold text-primary">
            {{ initials(customer.customer_name) }}
          </span>
          <div class="min-w-0">
            <p class="text-[11px] font-bold uppercase tracking-wide text-muted">Customer</p>
            <p class="truncate font-bold text-foreground">{{ customer.customer_name }}</p>
          </div>
        </div>
      </AppCard>

      <!-- Items -->
      <AppCard v-if="cart.length" padding="none">
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <span class="text-xs font-bold uppercase tracking-wider text-muted">Items ({{ cart.length }})</span>
        </div>
        <div class="divide-y divide-line">
          <div v-for="line in cart" :key="line.item.item_code" class="flex items-center justify-between gap-3 p-4">
            <div class="min-w-0 flex-1">
              <p class="font-semibold leading-tight text-foreground">{{ line.item.item_name }}</p>
              <p class="mt-0.5 text-xs text-muted">{{ line.item.item_code }}</p>
              <button
                type="button"
                class="mt-2 inline-flex w-fit items-center gap-1.5 rounded-xl border border-line bg-card-muted px-2.5 py-1.5 text-xs font-semibold transition"
                :class="allowRateChange ? 'text-foreground hover:border-primary' : 'cursor-default text-muted opacity-70'"
                @click="openEdit(line)"
              >
                <span class="tnum">{{ currency }} {{ itemRate(line).toFixed(2) }}</span>
                <span class="text-subtle">/ {{ line.item.stock_uom }}</span>
                <AppIcon v-if="allowRateChange" name="edit" :size="13" class="ml-0.5 text-primary" />
              </button>
            </div>
            <QtyStepper :model-value="line.qty" @change="(d: number) => update(line.item.item_code, d)" />
          </div>
        </div>
      </AppCard>

      <EmptyState v-else-if="customer" icon="cart" title="Cart is empty" description="Add products from the catalog to continue.">
        <template #action>
          <AppButton variant="secondary" icon="package" @click="$router.push({ name: 'items' })">Browse catalog</AppButton>
        </template>
      </EmptyState>

      <!-- Totals -->
      <AppCard v-if="cart.length">
        <div class="space-y-2.5">
          <div class="flex items-center justify-between text-sm font-medium text-muted">
            <span>Subtotal</span><span class="tnum">{{ currency }} {{ net.toFixed(2) }}</span>
          </div>
          <div v-if="allowDiscountChange" class="space-y-2">
            <div class="flex items-center justify-between gap-3">
              <span class="text-sm font-medium text-muted">Discount</span>
              <SegmentedControl
                :model-value="discountMode"
                :options="[{ value: 'percent', label: '%' }, { value: 'amount', label: currency }]"
                @update:modelValue="(v: string) => (discountMode = v as any)"
              />
            </div>
            <div class="flex items-center justify-between gap-3 text-sm font-medium text-muted">
              <span>{{ discountMode === 'percent' ? 'Discount %' : `Discount (${currency})` }}</span>
              <input
                v-if="discountMode === 'percent'"
                v-model.number="discountPercent"
                type="number"
                inputmode="decimal"
                min="0"
                max="100"
                step="0.01"
                placeholder="0"
                class="tnum w-24 rounded-xl border border-line bg-card-muted px-3 py-1.5 text-right text-sm font-semibold text-foreground focus:outline-none"
              />
              <input
                v-else
                v-model.number="discountAmountInput"
                type="number"
                inputmode="decimal"
                min="0"
                :max="net"
                step="0.01"
                placeholder="0.00"
                class="tnum w-24 rounded-xl border border-line bg-card-muted px-3 py-1.5 text-right text-sm font-semibold text-foreground focus:outline-none"
              />
            </div>
          </div>
          <div v-if="discountAmount > 0" class="flex items-center justify-between text-sm font-medium text-muted">
            <span>Discount</span><span class="tnum">- {{ currency }} {{ discountAmount.toFixed(2) }}</span>
          </div>
          <div v-if="tax" class="flex items-center justify-between text-sm font-medium text-muted">
            <span>Tax</span><span class="tnum">{{ currency }} {{ tax.toFixed(2) }}</span>
          </div>
          <div class="flex items-center justify-between border-t border-line pt-3 text-lg font-bold text-foreground">
            <span>Total</span><span class="tnum">{{ currency }} {{ grand.toFixed(2) }}</span>
          </div>
        </div>
      </AppCard>

      <AppAlert v-if="submitError" tone="danger" :message="submitError" />
    </div>

    <!-- Confirm -->
    <StickyBar v-if="cart.length">
      <AppButton size="lg" block :loading="submitting" :disabled="!customer" trailing-icon="check" @click="submit">
        {{ submitting ? 'Processing…' : `Confirm order • ${currency} ${grand.toFixed(2)}` }}
      </AppButton>
    </StickyBar>

    <!-- Edit price sheet -->
    <BottomSheet v-model="sheetOpen" title="Edit unit price">
      <div v-if="editingItem" class="space-y-4">
        <div>
          <p class="text-[11px] font-bold uppercase tracking-wide text-muted">Item</p>
          <p class="mt-0.5 font-semibold text-foreground">{{ editingItem.item.item_name }}</p>
        </div>
        <FormField :label="`Override price (${currency})`">
          <BaseInput v-model="editPrice" type="number" inputmode="decimal" @keyup.enter="savePrice" />
        </FormField>
        <div class="flex gap-3">
          <AppButton variant="subtle" block @click="sheetOpen = false">Cancel</AppButton>
          <AppButton block @click="savePrice">Apply</AppButton>
        </div>
      </div>
    </BottomSheet>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import * as api from '../api/frappe';
import type { CartLine, SalesOrder } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, AppIcon, QtyStepper, EmptyState, StickyBar, BottomSheet, FormField, BaseInput, SegmentedControl } from '../components/ui';

const store = useSessionStore();
const router = useRouter();

const cart = computed(() => store.cart);
const customer = computed(() => store.customer);
const existingOrder = computed(() => store.currentOrderName);
const net = computed(() => store.cartTotal);
const orderDetail = ref<SalesOrder | null>(null);
const currency = computed(() => store.currencyDisplay);
// Matches the backend precedence exactly (_check_rate_change_allowed /
// _check_discount_change_allowed in sales.py): managers are exempt outright,
// and a user with no Van Profile at all (e.g. an admin/manager account not
// assigned to any van) is also treated as allowed — only an *explicit* false
// on an actual driver's own profile restricts it.
const allowRateChange = computed(() => store.isManager || store.driverConfig?.allow_rate_change !== false);
const allowDiscountChange = computed(() => store.isManager || store.driverConfig?.allow_discount_change !== false);
const tax = computed(() => {
  const t = orderDetail.value?.total_taxes_and_charges;
  return t && t > 0 ? t : 0;
});
const discountMode = ref<'percent' | 'amount'>('percent');
const discountPercent = ref(0);
const discountAmountInput = ref(0);
// The server sets apply_discount_on = "Grand Total" (Van Profile default), so ERPNext
// applies a percentage to net + tax, not to net alone. Mirror that here or the figure
// quoted to the customer differs from the order that gets saved whenever tax applies.
const applyDiscountOnGrandTotal = computed(() => (store.driverConfig?.apply_discount_on || 'Grand Total') === 'Grand Total');
const discountBase = computed(() => (applyDiscountOnGrandTotal.value ? net.value + tax.value : net.value));
const discountAmount = computed(() => {
  // A flat amount is clamped to net, matching the server's clamp in _apply_order_payload;
  // only the percentage base follows apply_discount_on.
  if (discountMode.value === 'amount') return Math.min(Math.max(discountAmountInput.value || 0, 0), net.value);
  return (discountBase.value * (discountPercent.value || 0)) / 100;
});
const grand = computed(() => Math.max(0, net.value + tax.value - discountAmount.value));
const submitting = ref(false);
const submitError = ref('');

const sheetOpen = ref(false);
const editingItem = ref<CartLine | null>(null);
const editPrice = ref<number>(0);

const initials = (name: string) => name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

const openEdit = (line: CartLine) => {
  if (!allowRateChange.value) return;
  editingItem.value = line;
  editPrice.value = itemRate(line);
  sheetOpen.value = true;
};
const savePrice = () => {
  if (editingItem.value) store.updateRate(editingItem.value.item.item_code, Number(editPrice.value));
  sheetOpen.value = false;
};

const update = (code: string, delta: number) => store.updateQty(code, delta);
const clear = () => store.clearCart();
const itemRate = (line: CartLine) => line.rate ?? line.item.price_list_rate ?? line.item.standard_rate ?? 0;

onMounted(async () => {
  if (existingOrder.value) {
    try {
      orderDetail.value = await api.getSalesOrder(existingOrder.value);
      const pct = orderDetail.value?.additional_discount_percentage || 0;
      const amt = orderDetail.value?.discount_amount || 0;
      if (pct > 0) {
        discountMode.value = 'percent';
        discountPercent.value = pct;
      } else if (amt > 0) {
        discountMode.value = 'amount';
        discountAmountInput.value = amt;
      }
    } catch (_e) {
      orderDetail.value = null;
    }
  }
});

const submit = async () => {
  if (!customer.value || !cart.value.length) return;
  submitting.value = true;
  submitError.value = '';
  try {
    const today = new Date().toISOString().slice(0, 10);
    const itemsPayload = cart.value.map((line) => ({
      item_code: line.item.item_code,
      item_name: line.item.item_name,
      qty: line.qty,
      rate: itemRate(line),
      amount: line.qty * itemRate(line),
      delivery_date: today,
      stock_uom: line.item.stock_uom,
      price_list_rate: itemRate(line),
    }));
    const discountArgs = allowDiscountChange.value
      ? discountMode.value === 'percent'
        ? { discountPercent: discountPercent.value || 0 }
        // discountAmount (clamped to the subtotal), not the raw input — typing 500
        // against a 100 subtotal must not send 500 to the server.
        : { discountAmount: discountAmount.value || 0 }
      : {};
    let orderName: string;
    if (existingOrder.value) {
      await api.updateSalesOrder(existingOrder.value, { customer: customer.value.name, items: itemsPayload, ...discountArgs });
      orderName = existingOrder.value;
    } else {
      const res = await api.createSalesOrder({ customer: customer.value.name, items: itemsPayload, ...discountArgs });
      store.setCurrentOrder(res.name);
      orderName = res.name;
    }
    await api.submitSalesOrder(orderName);
    store.clearCart();
    router.push({ name: 'history' });
  } catch (e: any) {
    submitError.value = e?.message || 'Failed to submit order';
  } finally {
    submitting.value = false;
  }
};
</script>
