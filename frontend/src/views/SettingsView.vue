<template>
  <WorkspacePage eyebrow="Manager · access control" title="Roles & access" description="The three-tier role model enforced at the API and row level." width="default">
    <template #actions>
      <StatusBadge tone="primary" :dot="false">Restricted</StatusBadge>
    </template>

    <div class="space-y-5">
      <!-- Role cards -->
      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-3xl bg-slate-950 p-5 text-white shadow-card">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10">
            <AppIcon name="shield" :size="18" />
          </div>
          <p class="mt-3 text-[10px] font-bold uppercase tracking-widest text-slate-400">System Manager</p>
          <p class="mt-1 text-lg font-bold">Full admin</p>
          <p class="mt-1 text-sm text-slate-300">CRUD on all custom doctypes and manager endpoints. Can delete configurations.</p>
        </div>
        <AppCard class="border-warning/30 bg-warning/[0.08]" padding="lg">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-warning/15 text-warning">
            <AppIcon name="users" :size="18" />
          </div>
          <p class="mt-3 text-[10px] font-bold uppercase tracking-widest text-warning">Sales Manager</p>
          <p class="mt-1 text-lg font-bold text-foreground">Operations</p>
          <p class="mt-1 text-sm text-muted">Manage profiles, view reports, approve loads. Cannot delete records.</p>
        </AppCard>
        <AppCard class="border-success/30 bg-success/[0.08]" padding="lg">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-success/15 text-success">
            <AppIcon name="truck" :size="18" />
          </div>
          <p class="mt-3 text-[10px] font-bold uppercase tracking-widest text-success">Van Sales Driver</p>
          <p class="mt-1 text-lg font-bold text-foreground">Field driver</p>
          <p class="mt-1 text-sm text-muted">PWA only. Own data via row-level filter.</p>
        </AppCard>
      </div>

      <!-- Permission matrix -->
      <AppCard padding="none">
        <div class="border-b border-line px-5 py-3 text-xs font-bold uppercase tracking-wider text-muted">Permission matrix</div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="border-b border-line">
                <th class="px-5 py-3 text-left text-xs font-bold uppercase tracking-wider text-muted">Module / action</th>
                <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-muted">Sys Mgr</th>
                <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-muted">Sales Mgr</th>
                <th class="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-muted">Driver</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="row in permMatrix" :key="row.action">
                <td class="px-5 py-3 font-medium text-foreground">{{ row.action }}</td>
                <td class="px-4 py-3 text-center"><PermCell :value="row.sm" /></td>
                <td class="px-4 py-3 text-center"><PermCell :value="row.mgr" /></td>
                <td class="px-4 py-3 text-center"><PermCell :value="row.driver" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>

      <!-- How-to -->
      <AppAlert tone="info">
        <span class="font-semibold">Assign the Van Sales Driver role:</span>
        <ol class="mt-2 list-inside list-decimal space-y-1">
          <li>Open <strong>ERPNext Desk → Setup → User</strong> and select the driver.</li>
          <li>Add the <strong>Van Sales Driver</strong> role.</li>
          <li>Create a Driver Profile for that user in <strong>Profiles</strong>.</li>
          <li>Activate the profile — the driver can now use the PWA.</li>
        </ol>
      </AppAlert>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { defineComponent, h } from 'vue';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppAlert, AppIcon, StatusBadge } from '../components/ui';

// Tiny inline cell renderer for the ✅ / ❌ / 🔐 matrix values.
const PermCell = defineComponent({
  props: { value: { type: String, required: true } },
  setup(props) {
    return () => {
      if (props.value === '✅') return h(AppIcon, { name: 'check', size: 17, class: 'inline text-success', strokeWidth: 3 });
      if (props.value === '❌') return h(AppIcon, { name: 'x', size: 16, class: 'inline text-subtle' });
      return h('span', { class: 'inline-flex items-center gap-1 text-xs font-semibold text-warning' }, [
        h(AppIcon, { name: 'lock', size: 13, class: 'inline' }),
        'route',
      ]);
    };
  },
});

const permMatrix = [
  { action: 'Create / Submit Sales Orders', sm: '✅', mgr: '✅', driver: '✅' },
  { action: "Submit others' orders", sm: '✅', mgr: '✅', driver: '❌' },
  { action: 'View Stock Dashboard (own van)', sm: '✅', mgr: '✅', driver: '✅' },
  { action: 'Create Stock Transfer', sm: '✅', mgr: '✅', driver: '✅' },
  { action: 'Collect Payments', sm: '✅', mgr: '✅', driver: '✅' },
  { action: 'View Customer Ledger', sm: '✅', mgr: '✅', driver: '🔐' },
  { action: 'Log & Read Expenses (own)', sm: '✅', mgr: '✅', driver: '✅' },
  { action: 'Submit EOD Report', sm: '✅', mgr: '✅', driver: '✅' },
  { action: 'View All EOD Reports', sm: '✅', mgr: '✅', driver: '❌' },
  { action: 'Manage Driver Profiles', sm: '✅', mgr: '✅', driver: '❌' },
  { action: 'Delete Configurations', sm: '✅', mgr: '❌', driver: '❌' },
  { action: 'View Role & Access Settings', sm: '✅', mgr: '✅', driver: '❌' },
];
</script>
