import axios from 'axios';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL || undefined,
});

export function absoluteApiUrl(path: string) {
  if (path.startsWith('http')) return path;
  if (API_BASE_URL) return `${API_BASE_URL}${path}`;
  return new URL(path, window.location.origin).toString();
}
