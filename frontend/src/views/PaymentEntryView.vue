<template>
  <WorkspacePage back eyebrow="Collect payment" title="New payment" description="Choose allocation behaviour and post a payment entry." width="default">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" @click="reload">Refresh</AppButton>
    </template>

    <div class="space-y-5 pb-28">
      <!-- Customer -->
      <AppCard v-if="customer" padding="sm">
        <div class="flex items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-sm font-bold text-primary">
              {{ initials(customer.customer_name) }}
            </span>
            <div class="min-w-0">
              <p class="truncate font-bold text-foreground">{{ customer.customer_name }}</p>
              <p class="truncate text-xs text-muted">{{ customer.name }}</p>
            </div>
          </div>
          <button class="text-sm font-semibold text-primary" @click="changeCustomer">Change</button>
        </div>
      </AppCard>
      <AppButton v-else variant="secondary" block icon="plus" @click="$router.push({ name: 'customers', query: { redirect: 'payment' } })">
        Select customer
      </AppButton>

      <div v-if="customer" class="space-y-5">
        <!-- Customer summary -->
        <AppCard v-if="customerSummary" class="bg-primary/[0.07] border-primary/20" padding="sm">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-muted">Outstanding balance</span>
            <span class="tnum text-lg font-bold text-foreground">{{ currency }} {{ (customerSummary.outstanding_balance || 0).toFixed(2) }}</span>
          </div>
          <div v-if="customerSummary.last_invoice" class="mt-2 flex items-center justify-between border-t border-line pt-2 text-sm">
            <span class="text-muted">Last invoice</span>
            <span class="text-right">
              <span class="block font-semibold text-foreground">{{ customerSummary.last_invoice.name }}</span>
              <span class="tnum block text-xs text-muted">{{ customerSummary.last_invoice.posting_date }} • {{ currency }} {{ (customerSummary.last_invoice.grand_total || 0).toFixed(2) }}</span>
            </span>
          </div>
          <div v-if="customerSummary.last_payment" class="mt-2 flex items-center justify-between border-t border-line pt-2 text-sm">
            <span class="text-muted">Last payment</span>
            <span class="text-right">
              <span class="tnum block font-semibold text-foreground">{{ currency }} {{ (customerSummary.last_payment.paid_amount || 0).toFixed(2) }}</span>
              <span class="block text-xs text-muted">{{ customerSummary.last_payment.posting_date }}</span>
            </span>
          </div>
        </AppCard>

        <!-- Amount + mode -->
        <div class="grid gap-4 sm:grid-cols-2">
          <FormField label="Paid amount">
            <BaseInput v-model="paidAmount" type="number" inputmode="decimal" :prefix="currency" placeholder="0.00" @update:modelValue="onPaidAmountChange" />
          </FormField>
          <FormField label="Mode of payment">
            <BaseSelect v-model="modeOfPayment" placeholder="Select mode">
              <option v-for="mode in paymentModes" :key="mode.name" :value="mode.name">{{ mode.name }}</option>
            </BaseSelect>
          </FormField>
        </div>

        <!-- Allocation mode -->
        <div class="space-y-2">
          <label class="text-xs font-bold uppercase tracking-wider text-muted">Allocation type</label>
          <SegmentedControl
            :model-value="allocationMode"
            :options="[{ value: 'auto', label: 'Auto FIFO' }, { value: 'manual', label: 'Manual' }, { value: 'advance', label: 'Advance' }]"
            @update:modelValue="(v: string) => (allocationMode = v as any)"
          />
          <p class="text-xs text-muted">
            {{ allocationMode === 'auto' ? 'Allocates to the oldest invoices first.' : allocationMode === 'manual' ? 'Pick and allocate specific invoices.' : 'Recorded as an advance — not allocated to invoices.' }}
          </p>
        </div>

        <!-- Outstanding invoices -->
        <div v-if="allocationMode !== 'advance'" class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-xs font-bold uppercase tracking-wider text-muted">Outstanding invoices</label>
            <span class="tnum text-xs font-medium" :class="unallocatedAmount < 0 ? 'text-danger' : 'text-muted'">
              Unallocated: {{ currency }} {{ unallocatedAmount.toFixed(2) }}
            </span>
          </div>

          <SearchBar v-if="allocationMode === 'manual' && invoices.length" v-model="invoiceSearchQuery" placeholder="Search invoice number…" />

          <SkeletonList v-if="loadingInvoices" :rows="2" height="4rem" />
          <EmptyState v-else-if="!invoices.length" icon="file-text" title="No outstanding invoices" description="This customer has nothing pending." />

          <div v-else class="space-y-2">
            <div
              v-for="inv in filteredInvoices"
              :key="inv.name"
              class="rounded-2xl border bg-card p-3 shadow-card transition"
              :class="inv.checked ? 'border-primary ring-1 ring-primary/40' : 'border-line'"
              @click="allocationMode === 'manual' ? toggleInvoice(inv) : null"
            >
              <div class="flex items-start gap-3">
                <span
                  v-if="allocationMode === 'manual'"
                  class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition"
                  :class="inv.checked ? 'border-primary bg-primary text-primary-fg' : 'border-line-strong'"
                >
                  <AppIcon v-if="inv.checked" name="check" :size="14" :stroke-width="3" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between">
                    <div>
                      <p class="font-semibold text-foreground">{{ inv.name }}</p>
                      <p class="text-xs text-muted">{{ inv.posting_date }}</p>
                    </div>
                  </div>
                  <div class="mt-2 flex items-center justify-between rounded-xl bg-card-muted p-2.5 text-sm">
                    <div>
                      <p class="text-[10px] font-bold uppercase tracking-wide text-muted">Invoice</p>
                      <p class="tnum font-medium text-foreground">{{ currency }} {{ inv.grand_total.toFixed(2) }}</p>
                    </div>
                    <div class="text-right">
                      <p class="text-[10px] font-bold uppercase tracking-wide text-muted">Pending</p>
                      <p class="tnum font-bold text-primary">{{ currency }} {{ inv.outstanding_amount.toFixed(2) }}</p>
                    </div>
                  </div>
                  <div v-if="inv.checked && inv.allocated_amount > 0" class="mt-2 flex items-center justify-between border-t border-line pt-2">
                    <label class="text-xs font-medium text-muted">Allocated</label>
                    <input
                      v-if="allocationMode === 'manual'"
                      type="number"
                      v-model.number="inv.allocated_amount"
                      class="tnum w-28 rounded-xl border border-line bg-input px-3 py-1.5 text-right text-sm font-semibold text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                      @click.stop
                      @input="validateAllocation(inv)"
                    />
                    <span v-else class="tnum text-sm font-bold text-primary">{{ currency }} {{ inv.allocated_amount.toFixed(2) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Advance: link sales order -->
        <div v-else class="space-y-3">
          <AppAlert tone="info" title="Advance payment" message="Optionally link to a Sales Order, or leave unlinked for a general advance." />
          <label class="text-xs font-bold uppercase tracking-wider text-muted">Link to sales order (optional)</label>
          <SearchBar v-if="!loadingSalesOrders && salesOrders.length" v-model="salesOrderSearchQuery" placeholder="Search order number…" />

          <SkeletonList v-if="loadingSalesOrders" :rows="2" height="4rem" />
          <EmptyState v-else-if="!salesOrders.length" icon="receipt" title="No sales orders" description="None found for this customer." />

          <div v-else class="space-y-2">
            <button
              class="flex w-full items-center gap-3 rounded-2xl border bg-card p-3 text-left transition"
              :class="selectedSalesOrder === null ? 'border-primary ring-1 ring-primary/40' : 'border-line'"
              @click="selectedSalesOrder = null"
            >
              <span class="flex h-5 w-5 items-center justify-center rounded-full border" :class="selectedSalesOrder === null ? 'border-primary' : 'border-line-strong'">
                <span v-if="selectedSalesOrder === null" class="h-2 w-2 rounded-full bg-primary" />
              </span>
              <div>
                <p class="font-semibold text-foreground">No sales order</p>
                <p class="text-xs text-muted">General advance payment</p>
              </div>
            </button>
            <button
              v-for="so in filteredSalesOrders"
              :key="so.name"
              class="flex w-full items-start gap-3 rounded-2xl border bg-card p-3 text-left transition"
              :class="selectedSalesOrder === so.name ? 'border-primary ring-1 ring-primary/40' : 'border-line'"
              @click="selectedSalesOrder = so.name"
            >
              <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border" :class="selectedSalesOrder === so.name ? 'border-primary' : 'border-line-strong'">
                <span v-if="selectedSalesOrder === so.name" class="h-2 w-2 rounded-full bg-primary" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="font-semibold text-foreground">{{ so.name }}</p>
                <p class="text-xs text-muted">{{ so.transaction_date }}</p>
                <div class="mt-2 flex items-center justify-between rounded-xl bg-card-muted p-2.5 text-sm">
                  <div>
                    <p class="text-[10px] font-bold uppercase tracking-wide text-muted">Order</p>
                    <p class="tnum font-medium text-foreground">{{ currency }} {{ so.grand_total.toFixed(2) }}</p>
                  </div>
                  <div class="text-right">
                    <p class="text-[10px] font-bold uppercase tracking-wide text-muted">Pending</p>
                    <p class="tnum font-bold text-primary">{{ currency }} {{ (so.grand_total - (so.advance_paid || 0)).toFixed(2) }}</p>
                  </div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>

      <AppAlert v-if="submitError" tone="danger" :message="submitError" />
      <AppAlert v-if="successMsg" tone="success" :message="successMsg" />
    </div>

    <StickyBar>
      <AppButton size="lg" block icon="check" :disabled="!isValid" :loading="submitting" @click="submit">
        {{ submitting ? 'Submitting…' : `Confirm payment${paidAmount ? ` • ${currency} ${Number(paidAmount).toFixed(2)}` : ''}` }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import * as api from '../api/frappe';
import type { OutstandingInvoice, PaymentMode, PaymentReference, SalesOrderSummary, CustomerSummary } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, AppIcon, FormField, BaseInput, BaseSelect, SearchBar, SegmentedControl, SkeletonList, EmptyState, StickyBar } from '../components/ui';

const store = useSessionStore();
const route = useRoute();
const router = useRouter();

const customer = computed(() => store.customer);
const currency = computed(() => store.currencyDisplay);

const modeOfPayment = ref('');
const paidAmount = ref<number | null>(null);
const invoices = ref<OutstandingInvoice[]>([]);
const salesOrders = ref<SalesOrderSummary[]>([]);
const customerSummary = ref<CustomerSummary | null>(null);
const paymentModes = ref<PaymentMode[]>([]);
const loadingInvoices = ref(false);
const loadingSalesOrders = ref(false);
const submitting = ref(false);
const submitError = ref('');
const successMsg = ref('');
const allocationMode = ref<'auto' | 'manual' | 'advance'>('auto');
const selectedSalesOrder = ref<string | null>(null);
const invoiceSearchQuery = ref('');
const salesOrderSearchQuery = ref('');

const customerParam = route.query.customer as string | undefined;
const customerNameParam = route.query.customer_name as string | undefined;

const initials = (name: string) => name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

onMounted(async () => {
  if (customerParam && customerNameParam) {
    store.setCustomer({ name: customerParam, customer_name: customerNameParam, customer_group: '', territory: '' });
  }
  try {
    paymentModes.value = await api.getPaymentModes();
    if (paymentModes.value.length) modeOfPayment.value = paymentModes.value[0].name;
  } catch (e) {
    console.error('Failed to load payment modes', e);
  }
  if (customer.value) {
    loadInvoices();
    loadSalesOrders();
    loadCustomerSummary();
  }
});

const reload = async () => {
  if (!customer.value) return;
  await Promise.all([loadInvoices(), loadSalesOrders(), loadCustomerSummary()]);
};

const loadInvoices = async () => {
  if (!customer.value) return;
  loadingInvoices.value = true;
  try {
    const data = await api.getOutstandingInvoices(customer.value.name);
    invoices.value = data.map((inv) => ({ ...inv, checked: false, allocated_amount: 0 }));
  } catch (e) {
    console.error('Failed to load invoices', e);
  } finally {
    loadingInvoices.value = false;
  }
};

const loadSalesOrders = async () => {
  if (!customer.value) return;
  loadingSalesOrders.value = true;
  try {
    salesOrders.value = await api.getSalesOrders(customer.value.name);
  } catch (e) {
    console.error('Failed to load sales orders', e);
  } finally {
    loadingSalesOrders.value = false;
  }
};

const loadCustomerSummary = async () => {
  if (!customer.value) return;
  try {
    customerSummary.value = await api.getCustomerSummary(customer.value.name);
  } catch (e) {
    console.error('Failed to load customer summary', e);
  }
};

const changeCustomer = () => {
  store.setCustomer(null);
  invoices.value = [];
  salesOrders.value = [];
  customerSummary.value = null;
  paidAmount.value = null;
  selectedSalesOrder.value = null;
};

const onPaidAmountChange = () => {
  if (allocationMode.value === 'auto') autoAllocate();
};

const autoAllocate = () => {
  if (!paidAmount.value || paidAmount.value <= 0) {
    invoices.value.forEach((inv) => {
      inv.checked = false;
      inv.allocated_amount = 0;
    });
    return;
  }
  let remaining = Number(paidAmount.value);
  const sortedInvoices = [...invoices.value].sort((a, b) => new Date(a.posting_date).getTime() - new Date(b.posting_date).getTime());
  sortedInvoices.forEach((inv) => {
    if (remaining <= 0) {
      inv.checked = false;
      inv.allocated_amount = 0;
    } else {
      const toAllocate = Math.min(remaining, inv.outstanding_amount);
      inv.checked = toAllocate > 0;
      inv.allocated_amount = toAllocate;
      remaining -= toAllocate;
    }
  });
};

const toggleInvoice = (inv: OutstandingInvoice) => {
  inv.checked = !inv.checked;
  if (inv.checked) {
    if (!inv.allocated_amount) inv.allocated_amount = inv.outstanding_amount;
  } else {
    inv.allocated_amount = 0;
  }
  updatePaidAmountFromSelection();
};

const validateAllocation = (inv: OutstandingInvoice) => {
  if (inv.allocated_amount && inv.allocated_amount > inv.outstanding_amount) inv.allocated_amount = inv.outstanding_amount;
  if (inv.allocated_amount && inv.allocated_amount < 0) inv.allocated_amount = 0;
  if (inv.allocated_amount === 0) inv.checked = false;
  updatePaidAmountFromSelection();
};

const updatePaidAmountFromSelection = () => {
  paidAmount.value = invoices.value.filter((i) => i.checked).reduce((sum, i) => sum + (i.allocated_amount || 0), 0);
};

const allocatedTotal = computed(() => invoices.value.filter((i) => i.checked).reduce((sum, i) => sum + (i.allocated_amount || 0), 0));

const filteredInvoices = computed(() => {
  if (!invoiceSearchQuery.value.trim()) return invoices.value;
  const query = invoiceSearchQuery.value.toLowerCase();
  return invoices.value.filter((inv) => inv.name.toLowerCase().includes(query));
});

const filteredSalesOrders = computed(() => {
  if (!salesOrderSearchQuery.value.trim()) return salesOrders.value;
  const query = salesOrderSearchQuery.value.toLowerCase();
  return salesOrders.value.filter((so) => so.name.toLowerCase().includes(query));
});

const unallocatedAmount = computed(() => (Number(paidAmount.value) || 0) - allocatedTotal.value);

const isValid = computed(() => {
  if (!customer.value || !modeOfPayment.value || (Number(paidAmount.value) || 0) <= 0) return false;
  if (allocationMode.value === 'advance') return true;
  return unallocatedAmount.value >= 0;
});

const submit = async () => {
  if (!isValid.value || !customer.value) return;
  submitting.value = true;
  submitError.value = '';
  successMsg.value = '';
  try {
    const references: PaymentReference[] =
      allocationMode.value === 'advance'
        ? []
        : invoices.value
            .filter((i) => i.checked && (i.allocated_amount || 0) > 0)
            .map((i) => ({ name: i.name, grand_total: i.grand_total, outstanding_amount: i.outstanding_amount, allocated_amount: i.allocated_amount || 0 }));

    await api.createPaymentEntry(
      customer.value.name,
      modeOfPayment.value,
      Number(paidAmount.value) || 0,
      references,
      allocationMode.value === 'advance' ? selectedSalesOrder.value || undefined : undefined,
    );
    successMsg.value = 'Payment created successfully. Returning…';
    setTimeout(() => router.back(), 1500);
  } catch (e: any) {
    submitError.value = e.message || 'Failed to create payment';
  } finally {
    submitting.value = false;
  }
};

watch(allocationMode, (newMode) => {
  if (newMode === 'auto' && paidAmount.value) autoAllocate();
  else if (newMode === 'advance') {
    invoices.value.forEach((inv) => {
      inv.checked = false;
      inv.allocated_amount = 0;
    });
  }
});
</script>
