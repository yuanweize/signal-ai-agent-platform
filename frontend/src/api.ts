/**
 * API client — handles all backend communication.
 * 
 * Automatically attaches JWT from localStorage.
 * Redirects to login on 401.
 */

const API_BASE = '/api';

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem('token');
  }

  setToken(token: string): void {
    localStorage.setItem('token', token);
  }

  clearToken(): void {
    localStorage.removeItem('token');
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  async request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options;

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (body) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.status === 401 && endpoint !== '/auth/login' && endpoint !== '/auth/me') {
      this.clearToken();
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (response.status === 204) {
      return undefined as T;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Auth
  async checkAuth() {
    return this.request<{ requires_2fa: boolean }>('/auth/me');
  }

  async login(username: string, password: string, totpCode?: string) {
    return this.request<{ access_token: string; expires_in: number }>(
      '/auth/login',
      {
        method: 'POST',
        body: { username, password, totp_code: totpCode || null },
      }
    );
  }

  // Dashboard
  async getStats() {
    return this.request<{
      users: number;
      products: number;
      conversations: number;
      messages: number;
      groups: number;
      orders: number;
      features: Record<string, boolean>;
    }>('/dashboard/stats');
  }

  // Products
  async getProducts(page = 1, pageSize = 20) {
    return this.request<{
      items: Product[];
      total: number;
      page: number;
      page_size: number;
    }>(`/products?page=${page}&page_size=${pageSize}&active_only=false`);
  }

  async createProduct(data: ProductInput) {
    return this.request<Product>('/products', { method: 'POST', body: data });
  }

  async updateProduct(id: number, data: Partial<ProductInput>) {
    return this.request<Product>(`/products/${id}`, { method: 'PUT', body: data });
  }

  async deleteProduct(id: number) {
    return this.request<void>(`/products/${id}`, { method: 'DELETE' });
  }
}

export interface Product {
  id: number;
  name: string;
  description: string;
  price: number;
  currency: string;
  category: string;
  tags: string;
  stock: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductInput {
  name: string;
  description?: string;
  price: number;
  currency?: string;
  category?: string;
  tags?: string;
  stock?: number;
  is_active?: boolean;
}

export const api = new ApiClient();
