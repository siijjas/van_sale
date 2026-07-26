import { computed, ref } from 'vue';

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'vansale-theme';

// Surface colors that match --c-elevated so the mobile browser chrome blends in.
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: '#ffffff',
  dark: '#0f172a',
};

function readStored(): ThemePreference {
  const v = localStorage.getItem(STORAGE_KEY);
  return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
}

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

// Module-level singleton — one source of truth shared across the app.
const preference = ref<ThemePreference>(readStored());
const systemDark = ref(systemPrefersDark());

const resolved = computed<ResolvedTheme>(() => {
  if (preference.value === 'system') return systemDark.value ? 'dark' : 'light';
  return preference.value;
});

function apply(theme: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', THEME_COLOR[theme]);
}

let initialized = false;
function init() {
  if (initialized) return;
  initialized = true;
  apply(resolved.value);
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', (e) => {
      systemDark.value = e.matches;
      if (preference.value === 'system') apply(resolved.value);
    });
}

function setPreference(pref: ThemePreference) {
  preference.value = pref;
  localStorage.setItem(STORAGE_KEY, pref);
  apply(resolved.value);
}

function toggle() {
  setPreference(resolved.value === 'dark' ? 'light' : 'dark');
}

export function useTheme() {
  init();
  return {
    preference,
    resolved,
    isDark: computed(() => resolved.value === 'dark'),
    setPreference,
    toggle,
  };
}
