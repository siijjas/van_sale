<template>
  <WorkspacePage back eyebrow="Ledger" title="Customer ledger" description="Invoiced amounts, receipts, and running balance." width="default">
    <template #actions>
      <AppButton variant="secondary" size="sm" icon="refresh" :loading="loading" @click="reload">Refresh</AppButton>
    </template>

    <div class="space-y-4">
      <!-- Customer + period controls -->
      <AppCard padding="sm" class="space-y-3">
        <button
          v-if="customer"
          class="focus-ring flex w-full items-center justify-between rounded-2xl bg-primary/10 px-3.5 py-3 text-left"
          @click="changeCustomer"
        >
          <div class="flex items-center gap-3">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 text-xs font-bold text-primary">
              {{ initials(customer.customer_name) }}
            </span>
            <p class="font-bold text-foreground">{{ customer.customer_name }}</p>
          </div>
          <span class="text-xs font-semibold text-primary">Change</span>
        </button>
        <AppButton v-else variant="secondary" block icon="plus" @click="$router.push({ name: 'customers', query: { redirect: 'ledger' } })">
          Select customer
        </AppButton>

        <FormField label="Period">
          <BaseSelect v-model="selectedPeriod">
            <option value="week">Last week</option>
            <option value="month">Last month</option>
            <option value="3months">Last 3 months</option>
            <option value="6months">Last 6 months</option>
          </BaseSelect>
        </FormField>
      </AppCard>

      <SkeletonList v-if="loading" :rows="6" height="3.5rem" />
      <EmptyState v-else-if="customer && !entries.length" icon="ledger" title="No transactions" description="Nothing recorded for this period." />

      <template v-else-if="customer && entries.length">
        <!-- Summary -->
        <div class="grid grid-cols-3 gap-3">
          <KpiTile label="Opening" :value="`${currency} ${openingBalance.toFixed(2)}`" tone="info" />
          <KpiTile label="Invoiced" :value="`${currency} ${totalDebit.toFixed(2)}`" tone="danger" />
          <KpiTile label="Received" :value="`${currency} ${totalCredit.toFixed(2)}`" tone="success" />
        </div>

        <!-- Transactions -->
        <AppCard padding="none">
          <div class="border-b border-line px-4 py-3 text-xs font-bold uppercase tracking-wider text-muted">
            {{ entries.length }} transactions
          </div>
          <div class="divide-y divide-line">
            <div v-for="(entry, index) in entriesWithBalance" :key="index" class="flex items-center gap-3 px-4 py-3">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
                :class="entry.debit > 0 ? 'bg-danger/12 text-danger' : 'bg-success/12 text-success'"
              >
                <AppIcon :name="entry.debit > 0 ? 'file-text' : 'banknote'" :size="17" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-foreground">{{ getDescription(entry) }}</p>
                <p class="text-[11px] text-muted">{{ formatDate(entry.posting_date) }} • {{ entry.voucher_no }}</p>
              </div>
              <div class="shrink-0 text-right">
                <p class="tnum text-sm font-bold" :class="entry.debit > 0 ? 'text-danger' : 'text-success'">
                  {{ entry.debit > 0 ? '+' : '−' }} {{ currency }} {{ (entry.debit > 0 ? entry.debit : entry.credit).toFixed(2) }}
                </p>
                <p class="tnum text-[11px] text-muted">Bal {{ currency }} {{ Math.abs(entry.balance).toFixed(2) }}</p>
              </div>
            </div>
          </div>
        </AppCard>

        <!-- Outstanding -->
        <AppCard class="bg-gradient-to-br from-primary to-primary/80 text-primary-fg" padding="lg">
          <p class="text-xs font-semibold uppercase tracking-wide opacity-80">Outstanding balance</p>
          <p class="tnum mt-1 text-3xl font-bold">{{ currency }} {{ Math.abs(currentBalance).toFixed(2) }}</p>
        </AppCard>
      </template>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session';
import * as api from '../api/frappe';
import type { LedgerEntry } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppIcon, KpiTile, FormField, BaseSelect, SkeletonList, EmptyState } from '../components/ui';

const store = useSessionStore();
const route = useRoute();

const customer = computed(() => store.customer);
const currency = computed(() => store.currencyDisplay);

const selectedPeriod = ref('week');
const entries = ref<LedgerEntry[]>([]);
const openingBalance = ref(0);
const loading = ref(false);

const dateRange = computed(() => {
  const end = new Date();
  const start = new Date();
  if (selectedPeriod.value === 'week') start.setDate(start.getDate() - 7);
  else if (selectedPeriod.value === 'month') start.setMonth(start.getMonth() - 1);
  else if (selectedPeriod.value === '3months') start.setMonth(start.getMonth() - 3);
  else if (selectedPeriod.value === '6months') start.setMonth(start.getMonth() - 6);
  return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) };
});

const customerParam = route.query.customer as string | undefined;
const customerNameParam = route.query.customer_name as string | undefined;

interface EntryWithBalance extends LedgerEntry {
  balance: number;
}

const entriesWithBalance = computed<EntryWithBalance[]>(() => {
  let running = openingBalance.value;
  return entries.value.map((entry) => {
    running += entry.debit - entry.credit;
    return { ...entry, balance: running };
  });
});
const currentBalance = computed(() => openingBalance.value + entries.value.reduce((sum, e) => sum + e.debit - e.credit, 0));
const totalDebit = computed(() => entries.value.reduce((sum, e) => sum + e.debit, 0));
const totalCredit = computed(() => entries.value.reduce((sum, e) => sum + e.credit, 0));

const initials = (name: string) => name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

const getDescription = (entry: EntryWithBalance): string => {
  const labels: Record<string, string> = {
    'Sales Invoice': 'Sales Invoice',
    'Payment Entry': 'Payment Received',
    'Journal Entry': 'Journal Entry',
    'Credit Note': 'Credit Note',
    'Debit Note': 'Debit Note',
  };
  return labels[entry.voucher_type] || entry.voucher_type;
};

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const loadLedger = async () => {
  if (!customer.value) return;
  loading.value = true;
  try {
    const result = await api.getCustomerLedger(customer.value.name, dateRange.value.from, dateRange.value.to);
    if (Array.isArray(result)) {
      entries.value = result;
      openingBalance.value = 0;
    } else {
      entries.value = (result as any).entries || [];
      openingBalance.value = (result as any).opening_balance || 0;
    }
  } catch (e) {
    console.error('Failed to load ledger', e);
  } finally {
    loading.value = false;
  }
};

const reload = () => customer.value && loadLedger();
const changeCustomer = () => {
  store.setCustomer(null);
  entries.value = [];
};

onMounted(() => {
  if (customerParam && customerNameParam) {
    store.setCustomer({ name: customerParam, customer_name: customerNameParam, customer_group: '', territory: '' });
  }
  if (customer.value) loadLedger();
});

watch([customer, selectedPeriod], () => customer.value && loadLedger());
</script>
