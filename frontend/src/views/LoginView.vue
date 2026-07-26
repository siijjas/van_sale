<template>
  <div class="relative min-h-screen bg-background px-5 py-8 pt-safe">
    <div class="absolute right-5 top-6 pt-safe">
      <ThemeToggle />
    </div>

    <div class="mx-auto grid min-h-[calc(100vh-4rem)] max-w-5xl items-center gap-10 lg:grid-cols-[1.05fr,0.95fr]">
      <!-- Brand / value prop -->
      <div class="space-y-7">
        <div class="flex items-center gap-3">
          <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-fg shadow-raised">
            <AppIcon name="truck" :size="26" />
          </div>
          <p class="text-[11px] font-bold uppercase tracking-[0.3em] text-primary">Van Sales</p>
        </div>
        <div class="space-y-3">
          <h1 class="max-w-xl text-4xl font-bold tracking-tight text-foreground lg:text-5xl">
            Your route, in one workspace.
          </h1>
          <p class="max-w-md text-base leading-7 text-muted">
            Orders, collections, van stock, returns, and end-of-day — built for the field. Sign in with your ERPNext
            credentials to start your shift.
          </p>
        </div>
        <div class="grid max-w-md gap-3 sm:grid-cols-3">
          <div v-for="f in features" :key="f.label" class="rounded-2xl border border-line bg-card p-4 shadow-card">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/12 text-primary">
              <AppIcon :name="f.icon" :size="18" />
            </span>
            <p class="mt-3 text-sm font-semibold text-foreground">{{ f.label }}</p>
          </div>
        </div>
      </div>

      <!-- Sign-in card -->
      <AppCard padding="lg" class="shadow-raised">
        <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-muted">Access</p>
        <h2 class="mt-1 text-2xl font-bold tracking-tight text-foreground">Sign in</h2>
        <p class="mt-1 text-sm text-muted">Use your ERPNext username and password.</p>

        <form class="mt-6 space-y-4" @submit.prevent="submit">
          <FormField label="Username">
            <BaseInput v-model="username" icon="user" placeholder="you@company.com" />
          </FormField>
          <FormField label="Password">
            <BaseInput v-model="password" type="password" icon="lock" placeholder="••••••••" />
          </FormField>
          <AppAlert v-if="error" tone="danger" :message="error" />
          <AppButton type="submit" size="lg" block :loading="loading">
            {{ loading ? 'Signing in…' : 'Sign in' }}
          </AppButton>
        </form>
      </AppCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useSessionStore } from '../stores/session';
import { AppCard, AppButton, AppAlert, AppIcon, FormField, BaseInput, ThemeToggle } from '../components/ui';

const store = useSessionStore();
const router = useRouter();

const username = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');

const features = [
  { label: 'Field Orders', icon: 'cart' },
  { label: 'Collections', icon: 'wallet' },
  { label: 'Van Stock', icon: 'boxes' },
];

// Native inputs handle required; submit validates server-side.
const submit = async () => {
  if (!username.value || !password.value) {
    error.value = 'Enter your username and password.';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    await store.login(username.value, password.value);
    router.push({ name: 'dashboard' });
  } catch (e: any) {
    error.value = e?.message || 'Login failed';
  } finally {
    loading.value = false;
  }
};
</script>
