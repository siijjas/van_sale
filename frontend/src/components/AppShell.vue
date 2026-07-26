<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <!-- Top header -->
    <header
      class="sticky top-0 z-50 flex items-center justify-between border-b border-line bg-elevated/90 px-4 py-2.5 pt-safe backdrop-blur lg:px-6"
    >
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-fg shadow-sm">
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
          class="flex items-center gap-1.5 rounded-full border px-2.5 py-1"
          :class="isOnline ? 'border-success/25 bg-success/10' : 'border-warning/30 bg-warning/10'"
        >
          <span class="block h-1.5 w-1.5 rounded-full" :class="isOnline ? 'bg-success' : 'bg-warning'" />
          <span class="text-[10px] font-bold uppercase tracking-wide" :class="isOnline ? 'text-success' : 'text-warning'">
            {{ isOnline ? 'Online' : 'Offline' }}
          </span>
        </div>
        <ThemeToggle />
      </div>
    </header>

    <!-- Main content -->
    <main class="w-full min-w-0 flex-1 pb-[76px] lg:pb-0 lg:pl-[88px]">
      <slot />
    </main>

    <!-- Bottom tab bar (mobile) / left rail (desktop) -->
    <nav
      class="fixed bottom-0 left-0 right-0 z-40 flex h-[68px] items-stretch justify-around border-t border-line bg-elevated/95 pb-safe backdrop-blur lg:top-0 lg:right-auto lg:h-screen lg:w-[88px] lg:flex-col lg:justify-start lg:gap-1 lg:border-r lg:border-t-0 lg:pb-4 lg:pt-20"
    >
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.to"
        class="group flex flex-1 flex-col items-center justify-center gap-1 transition lg:flex-none lg:py-2.5"
        :class="isActive(item.names) ? 'text-primary' : 'text-subtle hover:text-foreground'"
      >
        <span
          class="flex h-9 w-14 items-center justify-center rounded-2xl transition lg:w-12"
          :class="isActive(item.names) ? 'bg-primary/12' : 'group-active:scale-90'"
        >
          <AppIcon :name="item.icon" :size="22" :stroke-width="isActive(item.names) ? 2.4 : 2" />
        </span>
        <span class="text-[10px]" :class="isActive(item.names) ? 'font-bold' : 'font-medium'">{{ item.label }}</span>
      </RouterLink>

      <div class="hidden lg:mt-auto lg:block" />

      <button
        class="group flex flex-1 flex-col items-center justify-center gap-1 text-subtle transition hover:text-danger lg:flex-none lg:py-2.5"
        @click="logout"
      >
        <span class="flex h-9 w-14 items-center justify-center rounded-2xl transition group-active:scale-90 lg:w-12">
          <AppIcon name="logout" :size="22" />
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
