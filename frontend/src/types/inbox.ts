/**
 * Inbox domain types for Round 2 Admin Inbox.
 */

export type ConversationType = 'dm' | 'group';
export type ConversationMode = 'auto' | 'copilot' | 'manual' | 'paused';
export type DeliveryStatus = 'received' | 'pending' | 'sent' | 'failed' | 'delivered' | 'read';
export type MessageActor = 'customer' | 'bot' | 'admin' | 'system';
export type MessageOrigin =
  | 'customer'
  | 'ai_auto'
  | 'human_manual'
  | 'human_ai_assisted'
  | 'system'
  | 'campaign';

export interface AttachmentDTO {
  id: number;
  filename?: string | null;
  mime_type?: string | null;
  size?: number | null;
  external_attachment_id?: string | null;
  processing_status?: 'pending' | 'completed' | 'unsupported' | 'failed' | string;
  extracted_text?: string | null;
  processor_model?: string | null;
  processor_type?: string | null;
  processing_error?: string | null;
}

export interface ReactionDTO {
  id: number;
  emoji: string;
  reactor_identity: string;
  reactor_name?: string | null;
  target_timestamp?: number | null;
  is_removed: boolean;
  occurred_at?: string | null;
}

export interface MessageDTO {
  id: number;
  conversation_id: number;
  direction: 'inbound' | 'outbound';
  actor: MessageActor;
  role: 'user' | 'assistant' | 'system';
  sender_id?: string | null;
  sender_name?: string | null;
  content: string;
  tokens_used?: number | null;
  reply_to_id?: number | null;
  delivery_status?: DeliveryStatus | null;
  delivery_error?: string | null;
  signal_timestamp_ms?: number | null;
  occurred_at?: string | null;
  origin?: MessageOrigin | null;
  ai_run_id?: number | null;
  ai_suggestion_id?: number | null;
  admin_identity?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  timestamp: string;
  attachments: AttachmentDTO[];
  reactions: ReactionDTO[];
}

export interface ConversationDTO {
  id: number;
  type: ConversationType;
  signal_id: string;
  group_id?: string | null;
  display_name: string;
  mode: ConversationMode;
  is_blocked: boolean;
  is_active: boolean;
  summary?: string | null;
  message_count: number;
  unread_count: number;
  has_failed_outbound: boolean;
  last_message: string;
  last_message_at?: string | null;
  last_message_actor?: MessageActor | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetailDTO extends ConversationDTO {
  notes?: string | null;
  dm_user_id?: number | null;
  phone_number?: string | null;
  signal_uuid?: string | null;
  members_count: number;
  admins_count: number;
  sync_status?: string | null;
}

export interface ConversationListResponse {
  items: ConversationDTO[];
  total: number;
  total_unread: number;
}

export interface ConversationMessagesResponse {
  conversation_id: number;
  items: MessageDTO[];
  has_more_before: boolean;
  has_more_after: boolean;
  oldest_id?: number | null;
  newest_id?: number | null;
}
