/**
 * Auth store — Zustand, persisted to localStorage.
 *
 * v1 stub: no password verification for regular login (the user just picks a
 * preconfigured username). Admin actions require a separate password modal.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "istock.auth";

interface AuthState {
  user: string | null;
  login: (username: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      login: (username) => set({ user: username }),
      logout: () => set({ user: null }),
    }),
    { name: STORAGE_KEY },
  ),
);
