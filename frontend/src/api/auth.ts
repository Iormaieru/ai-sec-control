import { api, setToken } from "./client";
import type { TokenResponse, User } from "./types";

export async function login(username: string, password: string): Promise<User> {
  const form = new URLSearchParams({ username, password });
  const token = await api.postForm<TokenResponse>("/auth/login", form);
  setToken(token.access_token);
  return getMe();
}

export function getMe(): Promise<User> {
  return api.get<User>("/auth/me");
}

export function logout(): void {
  setToken(null);
}
