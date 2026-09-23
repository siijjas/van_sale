<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <!-- Top header — borderless, separated by elevation -->
    <header
      class="sticky top-0 z-50 flex items-center justify-between bg-elevated/92 px-4 py-2.5 pt-safe shadow-[0_1px_0_rgb(var(--c-line)),0_4px_14px_-10px_rgb(23_26_27/0.25)] backdrop-blur-md lg:px-6"
    >
      <div class="flex items-center gap-2.5">
        <div class="flex h-[38px] w-[38px] items-center justify-center rounded-xl bg-primary text-primary-fg shadow-btn">
          <AppIcon name="truck" :size="20" />
        </div>
        <div class="min-w-0">
          <h1 class="truncate text-[15px] font-bold leading-tight tracking-tight">Van Sales</h1>
          <p class="truncate text-[11px] font-medium text-muted">
            {{ store.driverConfig?.van_warehouse || store.session?.full_name || 'Workspace' }}
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div
          class="flex items-center gap-1.5 rounded-full px-2.5 py-[5px]"
          :class="isOnline ? 'bg-success/14' : 'bg-warning/16'"
        >
          <span class="block h-1.5 w-1.5 rounded-full" :class="isOnline ? 'bg-success' : 'bg-warning'" />
          <span class="text-[10px] font-bold uppercase tracking-[0.06em]" :class="isOnline ? 'text-success' : 'text-warning'">
            {{ isOnline ? 'Online' : 'Offline' }}
          </span>
        </div>
        <ThemeToggle />
      </div>
    </header>

    <!-- Main content -->
    <main class="w-full min-w-0 flex-1 pb-[84px] lg:pb-0 lg:pl-[88px]">
      <slot />
    </main>

    <!-- Bottom tab bar (mobile) / left rail (desktop) -->
    <nav
      class="fixed bottom-0 left-0 right-0 z-40 flex h-[76px] items-stretch justify-around bg-elevated/94 pb-safe pt-2 backdrop-blur-md
             shadow-[0_-1px_0_rgb(var(--c-line)),0_-10px_26px_-16px_rgb(23_26_27/0.3)]
             lg:top-0 lg:right-auto lg:h-screen lg:w-[88px] lg:flex-col lg:justify-start lg:gap-1 lg:pb-4 lg:pt-20"
    >
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="group flex flex-1 flex-col items-center justify-start gap-[3px] transition lg:flex-none lg:py-2.5"
        :class="isActive(item.names) ? 'text-primary' : 'text-subtle hover:text-foreground'"
      >
        <span
          class="flex h-8 w-[54px] items-center justify-center rounded-xl transition duration-150 ease-emphasis lg:w-12"
          :class="isActive(item.names) ? 'bg-primary-soft' : 'group-active:scale-90'"
        >
          <AppIcon :name="item.icon" :size="21" :stroke-width="isActive(item.names) ? 2.3 : 2" />
        </span>
        <span class="text-[10px]" :class="isActive(item.names) ? 'font-bold' : 'font-medium'">{{ item.label }}</span>
      </RouterLink>

      <div class="hidden lg:mt-auto lg:block" />

      <button
        class="group flex flex-1 flex-col items-center justify-start gap-[3px] text-subtle transition hover:text-danger lg:flex-none lg:py-2.5"
        @click="logout"
      >
        <span class="flex h-8 w-[54px] items-center justify-center rounded-xl transition group-active:scale-90 lg:w-12">
          <AppIcon name="logout" :size="21" />
        </span>
        <span class="text-[10px] font-medium">Logout</span>
      </button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import AppIcon from './ui/AppIcon.vue';
import ThemeToggle from './ui/ThemeToggle.vue';

const store = useSessionStore();
const route = useRoute();
const router = useRouter();

const isOnline = ref(navigator.onLine);
const handleOnline = () => (isOnline.value = true);
const handleOffline = () => (isOnline.value = false);
onMounted(() => {
  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);
});
onUnmounted(() => {
  window.removeEventListener('online', handleOnline);
  window.removeEventListener('offline', handleOffline);
});

type NavItem = { name: string; names: string[]; label: string; to: { name: string }; icon: string };

const navItems = computed<NavItem[]>(() => {
  const items: NavItem[] = [
    { name: 'dashboard', names: ['dashboard'], label: 'Home', to: { name: 'dashboard' }, icon: 'home' },
    {
      name: 'history',
      names: ['history', 'order-detail', 'payment-detail', 'daily-log'],
      label: 'Activity',
      to: { name: 'history' },
      icon: 'receipt',
    },
  ];

  if (store.driverConfig) {
    items.push({
      name: 'stock-dashboard',
      names: ['stock-dashboard', 'stock-transfer'],
      label: 'Stock',
      to: { name: 'stock-dashboard' },
      icon: 'boxes',
    });
  } else if (!store.isManager) {
    items.push({ name: 'ledger', names: ['ledger'], label: 'Ledger', to: { name: 'ledger' }, icon: 'ledger' });
  }

  if (store.isManager) {
    items.push({ name: 'van-profiles', names: ['van-profiles'], label: 'Profiles', to: { name: 'van-profiles' }, icon: 'user' });
    items.push({ name: 'settings', names: ['settings'], label: 'Settings', to: { name: 'settings' }, icon: 'settings' });
  }

  return items;
});

function isActive(names: string[]) {
  return names.includes(String(route.name || ''));
}

async function logout() {
  await store.logout();
  router.push({ name: 'login' });
}
</script>
