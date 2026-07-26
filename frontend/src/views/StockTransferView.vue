<template>
  <WorkspacePage back eyebrow="Load van" title="Stock transfer" description="Replenish the van warehouse from the source warehouse." width="default">
    <div class="space-y-4 pb-28">
      <!-- Route -->
      <AppCard padding="sm" class="space-y-3">
        <div class="flex items-center gap-2">
          <div class="flex-1 rounded-2xl bg-card-muted px-3 py-2.5">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-muted">From</p>
            <p class="truncate text-sm font-bold text-foreground">{{ driverConfig?.source_warehouse || 'Not configured' }}</p>
          </div>
          <AppIcon name="arrow-right" :size="20" class="shrink-0 text-subtle" />
          <div class="flex-1 rounded-2xl bg-primary/10 px-3 py-2.5">
            <p class="text-[11px] font-semibold uppercase tracking-wide text-primary">To</p>
            <p class="truncate text-sm font-bold text-foreground">{{ driverConfig?.van_warehouse || 'Not configured' }}</p>
          </div>
        </div>
        <BaseTextarea v-model="remarks" :rows="2" placeholder="Optional note for this van load…" />
      </AppCard>

      <AppAlert v-if="message" tone="success" :message="message" />
      <AppAlert v-if="error" tone="danger" :message="error" />

      <!-- Source search -->
      <AppCard padding="sm" class="space-y-3">
        <p class="px-1 text-sm font-bold text-foreground">Search transfer items</p>
        <SearchBar v-model="search" placeholder="Search by item name or code…" />
        <SkeletonList v-if="searchLoading" :rows="2" height="4rem" />
        <div v-else class="max-h-80 space-y-2 overflow-y-auto">
          <div
            v-for="item in searchResults"
            :key="item.item_code"
            class="flex items-center justify-between gap-3 rounded-2xl border border-line bg-card-muted p-3"
          >
            <div class="min-w-0">
              <p class="truncate font-semibold text-foreground">{{ item.item_name }}</p>
              <p class="text-xs text-muted">{{ item.item_code }} • {{ item.stock_uom }}</p>
              <p class="tnum mt-0.5 text-xs text-muted">Source: {{ Number(item.actual_qty || 0).toFixed(2) }}</p>
              <div class="mt-1 flex gap-1">
                <StatusBadge v-if="item.has_batch_no" tone="info" :dot="false">Batch</StatusBadge>
                <StatusBadge v-if="item.has_serial_no" tone="info" :dot="false">Serial</StatusBadge>
              </div>
            </div>
            <AppButton variant="secondary" size="sm" icon="plus" :disabled="lines.some(l => l.item_code === item.item_code)" @click="openAddSheet(item)">
              {{ lines.some(l => l.item_code === item.item_code) ? 'Added' : 'Add' }}
            </AppButton>
          </div>
          <p v-if="!searchResults.length" class="py-2 text-sm text-muted">No source stock found for this filter.</p>
        </div>
      </AppCard>

      <!-- Transfer lines -->
      <div class="space-y-3">
        <div class="flex items-center justify-between px-1">
          <p class="text-sm font-bold text-foreground">Transfer lines</p>
          <p class="text-xs text-muted">{{ lines.length }} selected</p>
        </div>

        <EmptyState v-if="!lines.length" icon="truck" title="No lines yet" description="Add items from the source warehouse to build this load." />

        <AppCard v-for="line in lines" :key="line.item_code" class="space-y-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate font-semibold text-foreground">{{ line.item_name }}</p>
              <p class="text-xs text-muted">{{ line.item_code }} • {{ line.stock_uom }}</p>
            </div>
            <button class="text-sm font-semibold text-danger" @click="removeLine(line.item_code)">Remove</button>
          </div>

          <FormField label="Quantity" :hint="`Available: ${line.available_qty.toFixed(2)}`">
            <BaseInput :model-value="line.qty" type="number" inputmode="numeric" @update:modelValue="(v) => setQty(line.item_code, v)" />
          </FormField>

          <FormField v-if="line.has_batch_no" label="Batch">
            <BaseSelect :model-value="line.batch_no || ''" placeholder="Select batch" @update:modelValue="(v) => setBatch(line.item_code, v)">
              <option v-for="batch in detailMap[line.item_code]?.batches || []" :key="batch.batch_no" :value="batch.batch_no">
                {{ batch.batch_no }} • {{ batch.available_qty.toFixed(2) }}
              </option>
            </BaseSelect>
          </FormField>

          <FormField v-if="line.has_serial_no" label="Serial numbers" :hint="`Entered ${(line.serial_nos || []).length} of ${Math.trunc(line.qty)}`">
            <BaseTextarea :model-value="(line.serial_nos || []).join('\n')" :rows="4" placeholder="One serial number per line" @update:modelValue="(v) => setSerials(line.item_code, v)" />
          </FormField>
        </AppCard>
      </div>
    </div>

    <StickyBar>
      <div class="flex items-center justify-between gap-3 pl-2">
        <div>
          <p class="text-[11px] font-semibold uppercase tracking-wide text-muted">Transfer</p>
          <p class="text-sm font-bold text-foreground">{{ lines.length }} line{{ lines.length !== 1 ? 's' : '' }}</p>
        </div>
        <AppButton variant="warning" size="lg" icon="truck" :disabled="!canSubmit" :loading="submitting" @click="submitTransfer">
          {{ submitting ? 'Submitting…' : 'Submit transfer' }}
        </AppButton>
      </div>
    </StickyBar>

    <QtyInputSheet
      v-model="addSheetOpen"
      :title="pendingDetail?.item_name || ''"
      :subtitle="pendingDetail?.item_code"
      :max-qty="pendingDetail?.source_qty"
      confirm-label="Add to transfer"
      @confirm="onTransferQtyConfirmed"
    />
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import * as api from '../api/frappe';
import type { Item, StockTransferLine, TransferItemDetail } from '../types';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, AppIcon, FormField, BaseInput, BaseSelect, BaseTextarea, SearchBar, StatusBadge, SkeletonList, EmptyState, StickyBar, QtyInputSheet } from '../components/ui';

const store = useSessionStore();
const driverConfig = computed(() => store.driverConfig);
const search = ref('');
const searchResults = ref<Item[]>([]);
const searchLoading = ref(false);
const lines = ref<StockTransferLine[]>([]);
const detailMap = ref<Record<string, TransferItemDetail>>({});
const submitting = ref(false);
const error = ref('');
const message = ref('');
const remarks = ref('');
const addSheetOpen = ref(false);
const pendingDetail = ref<TransferItemDetail | null>(null);

let searchTimer = window.setTimeout(() => undefined, 0);

const canSubmit = computed(() => {
  if (!lines.value.length) return false;
  return lines.value.every((line) => {
    if (!(line.qty > 0) || line.qty > line.available_qty) return false;
    if (line.has_batch_no && !line.batch_no) return false;
    if (line.has_serial_no && (line.serial_nos || []).length !== Math.trunc(line.qty)) return false;
    return true;
  });
});

async function loadItems() {
  if (!driverConfig.value?.source_warehouse || !driverConfig.value?.van_warehouse) {
    searchResults.value = [];
    error.value = 'Assign both source and van warehouses in Driver Profiles before creating a transfer.';
    searchLoading.value = false;
    return;
  }
  searchLoading.value = true;
  error.value = '';
  try {
    searchResults.value = await api.searchTransferItems(search.value);
  } catch (err: any) {
    error.value = err?.message || 'Failed to load transfer items';
  } finally {
    searchLoading.value = false;
  }
}

async function openAddSheet(item: Item) {
  error.value = '';
  if (lines.value.some((line) => line.item_code === item.item_code)) return;
  try {
    const detail = await api.getTransferItemDetail(item.item_code);
    pendingDetail.value = detail;
    addSheetOpen.value = true;
  } catch (err: any) {
    error.value = err?.message || 'Failed to load item detail';
  }
}

function onTransferQtyConfirmed(qty: number) {
  const detail = pendingDetail.value;
  if (!detail) return;
  detailMap.value = { ...detailMap.value, [detail.item_code]: detail };
  lines.value = [
    ...lines.value,
    {
      item_code: detail.item_code,
      item_name: detail.item_name,
      stock_uom: detail.stock_uom,
      qty,
      available_qty: detail.source_qty,
      has_batch_no: detail.has_batch_no,
      has_serial_no: detail.has_serial_no,
      batch_no: detail.batches[0]?.batch_no,
      serial_nos: [],
    },
  ];
  pendingDetail.value = null;
}

function removeLine(itemCode: string) {
  lines.value = lines.value.filter((line) => line.item_code !== itemCode);
}
function setQty(itemCode: string, value: string | number) {
  const nextQty = Number(value || 0);
  lines.value = lines.value.map((line) => (line.item_code === itemCode ? { ...line, qty: nextQty } : line));
}
function setBatch(itemCode: string, value: string) {
  lines.value = lines.value.map((line) => (line.item_code === itemCode ? { ...line, batch_no: value || undefined } : line));
}
function setSerials(itemCode: string, value: string) {
  const serials = value.split('\n').map((row) => row.trim()).filter(Boolean);
  lines.value = lines.value.map((line) => (line.item_code === itemCode ? { ...line, serial_nos: serials } : line));
}

async function submitTransfer() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = '';
  message.value = '';
  try {
    const result = await api.createStockTransfer(lines.value, remarks.value);
    message.value = `Stock Entry ${result.name} submitted to ${result.to_warehouse}.`;
    lines.value = [];
    remarks.value = '';
    await loadItems();
  } catch (err: any) {
    error.value = err?.message || 'Failed to create stock transfer';
  } finally {
    submitting.value = false;
  }
}

watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadItems, 250);
});
onMounted(loadItems);
</script>
