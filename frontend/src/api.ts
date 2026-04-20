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
  retryCount?: number;
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
    const { method = 'GET', body, headers = {}, retryCount = 2 } = options;

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (body) {
      headers['Content-Type'] = 'application/json';
    }

    let lastError: unknown = null;

    for (let attempt = 0; attempt <= retryCount; attempt += 1) {
      try {
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
          const message = error.detail || `HTTP ${response.status}`;
          const retriable = response.status >= 500 || response.status === 429;
          if (retriable && attempt < retryCount) {
            await new Promise(resolve => setTimeout(resolve, (attempt + 1) * 300));
            continue;
          }
          throw new Error(message);
        }

        return response.json();
      } catch (error) {
        lastError = error;
        const retriable = method === 'GET' && attempt < retryCount;
        if (!retriable) break;
        await new Promise(resolve => setTimeout(resolve, (attempt + 1) * 300));
      }
    }

    throw (lastError instanceof Error ? lastError : new Error('Request failed'));
  }

  // Auth
  async checkAuth() {
    return this.request<{ requires_2fa: boolean; bootstrap_required: boolean }>('/auth/me');
  }

  async initBootstrap(payload: BootstrapInitRequest) {
    return this.request<BootstrapInitResponse>('/auth/bootstrap/init', {
      method: 'POST',
      body: payload,
    });
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

  // Runtime Settings
  async getSettings() {
    return this.request<RuntimeSettings>('/settings');
  }

  async updateSettings(data: RuntimeSettingsUpdate) {
    return this.request<RuntimeSettings>('/settings', { method: 'PUT', body: data });
  }

  async getUsers(page = 1, pageSize = 20, search = '', blocked?: boolean) {
    const searchPart = search ? `&search=${encodeURIComponent(search)}` : '';
    const blockedPart = typeof blocked === 'boolean' ? `&blocked=${blocked}` : '';
    return this.request<ManagedUserListResponse>(
      `/users?page=${page}&page_size=${pageSize}${searchPart}${blockedPart}`
    );
  }

  async updateUser(userId: number, payload: ManagedUserUpdateRequest) {
    return this.request<ManagedUserItem>(`/users/${userId}`, {
      method: 'PUT',
      body: payload,
    });
  }

  async batchUsersAction(payload: ManagedUsersBatchRequest) {
    return this.request<ManagedUsersBatchResponse>('/users/batch', {
      method: 'POST',
      body: payload,
    });
  }

  async getUserActivity(userId: number, messageLimit = 20, conversationLimit = 10) {
    return this.request<ManagedUserActivityResponse>(
      `/users/${userId}/activity?message_limit=${messageLimit}&conversation_limit=${conversationLimit}`
    );
  }

  async runCampaignBroadcast(payload: CampaignBroadcastPayload) {
    return this.request<CampaignBroadcastResponse>('/campaigns/broadcast', {
      method: 'POST',
      body: payload,
    });
  }

  async getCampaignSummary() {
    return this.request<CampaignSummaryResponse>('/campaigns/summary');
  }

  async rollbackSettings(auditLogId?: number) {
    return this.request<RuntimeSettings>('/settings/rollback', {
      method: 'POST',
      body: { audit_log_id: auditLogId ?? null },
    });
  }

  async getAuditLogs(page = 1, pageSize = 50, actionPrefix?: string) {
    const actionParam = actionPrefix ? `&action_prefix=${encodeURIComponent(actionPrefix)}` : '';
    return this.request<AuditLogListResponse>(
      `/settings/audit?page=${page}&page_size=${pageSize}${actionParam}`
    );
  }

  async cleanupData(purgeAll = false) {
    return this.request<CleanupResponse>('/settings/cleanup', {
      method: 'POST',
      body: { purge_all: purgeAll },
    });
  }

  async probeAiCompatibility(payload: AiProbeRequest) {
    return this.request<AiProbeResponse>('/settings/ai/probe', {
      method: 'POST',
      body: payload,
    });
  }

  async verifyAiModel(payload: AiModelVerifyRequest) {
    return this.request<AiModelVerifyResponse>('/settings/ai/verify-model', {
      method: 'POST',
      body: payload,
    });
  }

  // Chats
  async getChats(limit = 50) {
    return this.request<{ items: ChatConversation[]; total: number }>(`/chats?limit=${limit}`);
  }

  async getChatMessages(signalId: string, groupId?: string, page = 1, pageSize = 100) {
    const groupParam = groupId ? `&group_id=${encodeURIComponent(groupId)}` : '';
    return this.request<ChatMessagesResponse>(
      `/chats/${encodeURIComponent(signalId)}/messages?page=${page}&page_size=${pageSize}${groupParam}`
    );
  }

  async sendChatMessage(signalId: string, payload: ChatSendPayload) {
    return this.request<{ success: boolean }>(`/chats/${encodeURIComponent(signalId)}/send`, {
      method: 'POST',
      body: payload,
    });
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

export interface RuntimeSettings {
  bot_name: string;
  bot_default_language: string;
  signal_api_url: string;
  signal_phone_number: string;
  has_signal_api_token: boolean;
  signal_api_token_masked: string;
  ai_prompt: string;
  is_ai_enabled: boolean;
  is_market_enabled: boolean;
  has_ai_api_key: boolean;
  ai_api_key_masked: string;
  ai_api_key_source: string;
  ai_api_base_url: string;
  ai_provider_detected: string;
  ai_model: string;
  ai_temperature: number;
  ai_max_tokens: number;
  ai_context_messages: number;
  ai_models_cached: string[];
  ai_models_cached_invalid: string[];
  ai_models_listed_total: number;
  ai_models_cached_at?: string | null;
  retention_days: number;
  ad_automation_enabled: boolean;
  ad_min_interval_minutes: number;
  ad_quiet_hour_start: number;
  ad_quiet_hour_end: number;
  ad_group_blacklist: string[];
}

export interface RuntimeSettingsUpdate {
  bot_name?: string;
  bot_default_language?: string;
  signal_api_url?: string;
  signal_phone_number?: string;
  signal_api_token?: string;
  ai_prompt?: string;
  is_ai_enabled?: boolean;
  is_market_enabled?: boolean;
  ai_api_key?: string;
  ai_api_base_url?: string;
  ai_model?: string;
  ai_temperature?: number;
  ai_max_tokens?: number;
  ai_context_messages?: number;
  retention_days?: number;
  ad_automation_enabled?: boolean;
  ad_min_interval_minutes?: number;
  ad_quiet_hour_start?: number;
  ad_quiet_hour_end?: number;
  ad_group_blacklist?: string[];
}

export interface AiProbeRequest {
  ai_api_base_url?: string;
  ai_model?: string;
  ai_api_key?: string;
}

export interface AiModelVerifyRequest {
  ai_api_base_url?: string;
  ai_model: string;
  ai_api_key?: string;
}

export interface BootstrapInitRequest {
  username: string;
  password: string;
  password_confirm: string;
  totp_secret?: string;
}

export interface BootstrapInitResponse {
  initialized: boolean;
  username: string;
  generated_totp_secret?: string | null;
}

export interface AiProbeAttempt {
  base_url: string;
  model: string;
  status?: number | null;
  message: string;
}

export interface AiProbeResponse {
  ok: boolean;
  provider_detected: string;
  requested_base_url?: string | null;
  candidate_base_urls: string[];
  verification_base_candidates: string[];
  effective_base_url?: string | null;
  effective_model?: string | null;
  models: string[];
  invalid_models: Array<{ model: string; reason?: string }>;
  listed_total: number;
  models_count?: number;
  verified_total?: number;
  probed_at?: string | null;
  cached_at?: string | null;
  message: string;
  preview?: string | null;
  attempts: AiProbeAttempt[];
}

export interface AiModelVerifyResponse {
  ok: boolean;
  model: string;
  effective_model?: string | null;
  effective_base_url?: string | null;
  checked_at: string;
  message: string;
  preview?: string | null;
  attempts: AiProbeAttempt[];
}

export interface CampaignBroadcastPayload {
  campaign_name: string;
  message: string;
  target_group_ids?: string[];
  dry_run?: boolean;
}

export interface CampaignBroadcastGroupResult {
  group_id: string;
  status: string;
  reason?: string | null;
}

export interface CampaignBroadcastResponse {
  campaign_name: string;
  attempted: number;
  sent: number;
  skipped: number;
  failed: number;
  dry_run: boolean;
  items: CampaignBroadcastGroupResult[];
}

export interface CampaignSummaryRow {
  id: number;
  campaign_name: string;
  group_id: string;
  status: string;
  reason?: string | null;
  created_at: string;
}

export interface CampaignSummaryResponse {
  total_attempts: number;
  total_sent: number;
  total_failed: number;
  recent: CampaignSummaryRow[];
}

export interface ChatConversation {
  signal_id: string;
  display_name?: string;
  group_id?: string;
  last_message: string;
  last_message_at?: string;
  message_count: number;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  timestamp: string;
}

export interface ChatMessagesResponse {
  signal_id: string;
  display_name?: string;
  group_id?: string;
  items: ChatMessage[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChatSendPayload {
  message: string;
  group_id?: string;
}

export interface CleanupResponse {
  messages_deleted: number;
  conversations_deleted: number;
  audit_logs_deleted: number;
  campaign_logs_deleted: number;
  retention_days?: number | null;
}

export interface AuditLogItem {
  id: number;
  actor: string;
  action: string;
  target: string;
  status: string;
  ip_address?: string;
  details: string;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ManagedUserItem {
  id: number;
  signal_id: string;
  display_name?: string;
  role: string;
  language: string;
  is_blocked: boolean;
  notes?: string;
  first_seen: string;
  last_seen: string;
}

export interface ManagedUserListResponse {
  items: ManagedUserItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ManagedUserUpdateRequest {
  display_name?: string;
  role?: string;
  language?: string;
  is_blocked?: boolean;
  notes?: string;
}

export interface ManagedUsersBatchRequest {
  user_ids: number[];
  action: 'block' | 'unblock';
}

export interface ManagedUsersBatchResponse {
  updated_count: number;
  action: 'block' | 'unblock' | string;
}

export interface UserConversationSummary {
  conversation_id: number;
  group_id?: string;
  message_count: number;
  updated_at: string;
  last_message?: string;
}

export interface UserRecentMessage {
  id: number;
  role: string;
  content: string;
  timestamp: string;
  group_id?: string;
}

export interface ManagedUserActivityResponse {
  user: ManagedUserItem;
  conversation_count: number;
  message_count: number;
  recent_conversations: UserConversationSummary[];
  recent_messages: UserRecentMessage[];
}

export const api = new ApiClient();
