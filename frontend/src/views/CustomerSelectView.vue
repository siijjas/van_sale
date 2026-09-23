<template>
  <WorkspacePage back :eyebrow="actionLabel" title="Select customer" width="default">
    <template #actions>
      <AppButton size="sm" icon="plus" @click="openNewCustomer">New customer</AppButton>
    </template>

    <div class="space-y-4">
      <div class="sticky top-[60px] z-30 -mx-1 px-1 pb-1">
        <SearchBar v-model="txt" placeholder="Search customers by name or ID…" />
      </div>

      <AppAlert tone="info" :message="actionHint" />

      <SkeletonList v-if="loading" :rows="5" height="4rem" />
      <EmptyState v-else-if="!customers.length" icon="users" title="No customers found" description="Try a different search term, or add this customer as new.">
        <template #action>
          <AppButton variant="secondary" icon="plus" @click="openNewCustomer">New customer</AppButton>
        </template>
      </EmptyState>
      <div v-else class="space-y-2.5">
        <AppCard
          v-for="customer in customers"
          :key="customer.name"
          padding="sm"
          interactive
          @click="selectCustomer(customer)"
        >
          <div class="flex items-center gap-3">
            <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-sm font-bold text-primary">
              {{ initials(customer.customer_name) }}
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-foreground">{{ customer.customer_name }}</p>
              <p class="truncate text-xs text-muted">{{ customer.name }}</p>
            </div>
            <StatusBadge v-if="customer.territory" tone="neutral" :dot="false">{{ customer.territory }}</StatusBadge>
            <AppIcon name="chevron-right" :size="18" class="text-subtle" />
          </div>
        </AppCard>
      </div>
    </div>

    <BottomSheet v-model="newCustomerOpen" title="New customer">
      <div class="space-y-4">
        <FormField label="Customer name" required>
          <BaseInput v-model="newCustomerName" placeholder="e.g. Al Amal Grocery" @keyup.enter="submitNewCustomer" />
        </FormField>
        <FormField label="Mobile number">
          <BaseInput v-model="newCustomerMobile" type="tel" inputmode="tel" placeholder="Optional" @keyup.enter="submitNewCustomer" />
        </FormField>
        <AppAlert v-if="newCustomerError" tone="danger" :message="newCustomerError" />
        <div class="flex gap-3">
          <AppButton variant="subtle" block @click="newCustomerOpen = false">Cancel</AppButton>
          <AppButton block :loading="creatingCustomer" @click="submitNewCustomer">Add customer</AppButton>
        </div>
      </div>
    </BottomSheet>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import * as api from '../api/frappe';
import type { Customer } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, AppIcon, SearchBar, StatusBadge, SkeletonList, EmptyState, BottomSheet, FormField, BaseInput } from '../components/ui';

const router = useRouter();
const route = useRoute();
const store = useSessionStore();
const txt = ref('');
const customers = ref<Customer[]>([]);
const loading = ref(true);

const newCustomerOpen = ref(false);
const newCustomerName = ref('');
const newCustomerMobile = ref('');
const newCustomerError = ref('');
const creatingCustomer = ref(false);

const redirect = computed(() => route.query.redirect as string | undefined);
const actionLabel = computed(
  () => ({ payment: 'Collect Payment', ledger: 'Customer Ledger', return: 'Sales Return' })[redirect.value || ''] || 'New Order',
);
const actionHint = computed(
  () =>
    ({
      payment: 'The selected customer opens the payment collection workflow.',
      ledger: 'The selected customer opens their financial ledger.',
      return: 'The selected customer opens the returns workflow.',
    })[redirect.value || ''] || 'The selected customer continues to the catalog to build a new order.',
);

const initials = (name: string) =>
  name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

const load = async () => {
  loading.value = true;
  customers.value = await api.searchCustomers(txt.value);
  loading.value = false;
};

watch(txt, () => {
  clearTimeout(timer);
  timer = window.setTimeout(load, 300);
});
let timer = window.setTimeout(load, 0);

const selectCustomer = (customer: Customer) => {
  store.setCustomer(customer);
  if (redirect.value === 'payment') router.push({ name: 'payment' });
  else if (redirect.value === 'ledger') router.push({ name: 'ledger' });
  else if (redirect.value === 'return') {
    store.clearReturnCart();
    router.push({ name: 'return-items', query: { customer: customer.name, customer_name: customer.customer_name } });
  } else router.push({ name: 'items' });
};

const openNewCustomer = () => {
  newCustomerName.value = txt.value.trim();
  newCustomerMobile.value = '';
  newCustomerError.value = '';
  newCustomerOpen.value = true;
};

const submitNewCustomer = async () => {
  const name = newCustomerName.value.trim();
  if (!name) {
    newCustomerError.value = 'Customer name is required';
    return;
  }
  creatingCustomer.value = true;
  newCustomerError.value = '';
  try {
    const customer = await api.createCustomer(name, newCustomerMobile.value.trim() || undefined);
    newCustomerOpen.value = false;
    selectCustomer(customer);
  } catch (e: any) {
    newCustomerError.value = e?.message || 'Failed to create customer';
  } finally {
    creatingCustomer.value = false;
  }
};
</script>
