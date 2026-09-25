/**
 * AI Platform v0.4 Domain Types.
 */

export interface AISuggestionDTO {
  id: number;
  conversation_id: number;
  inbound_message_id?: number | null;
  ai_run_id?: number | null;
  suggested_text: string;
  status: 'pending' | 'accepted' | 'edited' | 'rejected' | 'expired' | 'auto_sent';
  generated_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  edit_distance?: number | null;
  edit_ratio?: number | null;
  metadata?: {
    citations?: Array<{
      chunk_id?: number;
      title?: string;
      snippet?: string;
      score?: number;
    }>;
    skills_used?: string[];
    memories_used?: Array<{
      id?: number;
      content?: string;
      type?: string;
    }>;
    tools_called?: Array<{
      name?: string;
      arguments?: Record<string, unknown>;
    }>;
  } | null;
}

export interface AIRunExplainabilityDTO {
  id: number;
  trace_id: string;
  conversation_id: number;
  model?: string | null;
  provider?: string | null;
  prompt_version?: string | null;
  decision: string;
  confidence?: number | null;
  latency_ms?: number | null;
  tokens?: number | null;
  skills: string[];
  citations: Array<{
    chunk_id?: number;
    title?: string;
    snippet?: string;
    score?: number;
  }>;
  memories: Array<{
    id?: number;
    content?: string;
    type?: string;
  }>;
  tool_calls: Array<{
    name?: string;
    arguments?: Record<string, unknown>;
  }>;
  attachments?: Array<{
    id?: number;
    filename?: string | null;
    mime_type?: string | null;
    processing_status?: string | null;
    extracted_text?: string | null;
    processor_model?: string | null;
    processor_type?: string | null;
  }>;
  created_at: string;
}

export interface AIOverviewMetricsDTO {
  total_ai_runs?: number;
  total_runs: number;
  automation_rate?: number;
  copilot_rate?: number;
  human_takeover_rate?: number;
  suggestion_acceptance_rate?: number;
  copilot_acceptance_rate: number;
  copilot_suggestions_count?: number;
  suggestion_edit_rate?: number;
  copilot_avg_edit_ratio?: number;
  suggestion_rejection_rate?: number;
  rag_hit_rate?: number;
  knowledge_documents_count?: number;
  knowledge_sources_count?: number;
  knowledge_chunks_count?: number;
  memory_items_count: number;
  average_latency_ms?: number;
  avg_latency_ms: number;
  p50_latency_ms?: number | null;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
  total_tokens_used?: number;
  total_tokens: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
  estimated_cost?: number | null;
  cost_currency?: string;
  successful_runs?: number;
  error_runs?: number;
  error_rate?: number;
  tool_invocation_count?: number;
  tool_call_success_rate?: number;
  tool_approval_rate?: number;
  active_prompt_version?: string | null;
  time_range?: string;
  timezone?: string;
}

export interface AIModelCallDTO {
  id: number;
  phase: string;
  provider?: string | null;
  model?: string | null;
  latency_ms: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
  usage_source: string;
  finish_reason?: string | null;
  provider_request_id?: string | null;
  success: boolean;
  error?: string | null;
  estimated_cost?: number | null;
  currency?: string;
  started_at?: string;
}

export interface AIRunDTO {
  id: number;
  trace_id: string;
  conversation_id: number;
  input_message_id?: number | null;
  final_message_id?: number | null;
  model?: string | null;
  provider?: string | null;
  prompt_version?: string | null;
  decision: string;
  confidence?: number | null;
  latency_ms?: number | null;
  tokens?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
  llm_call_count?: number;
  usage_source?: string;
  estimated_cost?: number | null;
  cost_currency?: string;
  traffic_source?: string;
  rag_hit_count?: number;
  tool_call_count?: number;
  retrieval?: Array<Record<string, unknown>>;
  citations: Array<{
    chunk_id?: number;
    title?: string;
    snippet?: string;
    score?: number;
  }>;
  memory?: Array<Record<string, unknown>>;
  memories: Array<{
    id?: number;
    content?: string;
    type?: string;
  }>;
  tool_calls: Array<{
    name?: string;
    arguments?: Record<string, unknown>;
    status?: string;
  }>;
  model_calls?: AIModelCallDTO[];
  errors?: string | null;
  created_at: string;
}

export interface AIRunListResponse {
  items: AIRunDTO[];
  total: number;
  limit: number;
  offset: number;
}

export interface UsageSummaryDTO {
  time_range?: string;
  total_runs: number;
  total_tokens: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  reasoning_tokens: number | null;
  estimated_cost: number | null;
  currency: string;
  cost_currency: string;
  total_model_calls: number;
  avg_latency_ms: number;
  errors: number;
  error_rate: number;
}

export interface UsageTimeseriesPointDTO {
  timestamp: string;
  runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  errors: number;
  avg_latency_ms: number;
}

export interface UsageTimeseriesResponseDTO {
  points: UsageTimeseriesPointDTO[];
  time_range: string;
  timezone: string;
}

export interface ModelUsageItemDTO {
  provider: string;
  model: string;
  runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens?: number;
  reasoning_tokens?: number;
  avg_latency_ms: number;
  errors?: number;
  error_count?: number;
  error_rate?: number;
  estimated_cost: number | null;
  currency: string;
}

export interface ModelUsageResponseDTO {
  models: ModelUsageItemDTO[];
}

export interface KnowledgeDocumentDTO {
  id: number;
  source_id: number;
  title: string;
  content: string;
  scope_type: string;
  scope_id?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSourceDetailDTO {
  source: KnowledgeSourceDTO;
  documents: KnowledgeDocumentDTO[];
}

export interface RAGSearchResultDTO {
  chunk_id: number;
  document_id: number;
  source_id: number;
  title: string;
  snippet: string;
  score: number;
  scope_type: string;
  scope_id?: string | null;
}

export interface MCPToolDetailDTO {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  read_only: boolean;
  requires_approval: boolean;
  has_external_effects: boolean;
}

export interface MCPServerDetailDTO extends MCPServerDTO {
  tools: MCPToolDetailDTO[];
  discovered_tools?: MCPToolDetailDTO[];
  server?: MCPServerDTO;
  latency_ms?: number | null;
}

export interface ProviderLiveTestResultDTO {
  endpoint: string;
  model: string;
  provider_detected: string;
  connection_status: 'connected' | 'failed' | 'not_configured' | string;
  connected?: boolean;
  latency_ms?: number | null;
  preview?: string | null;
  response_preview?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  usage_source?: string;
  native_tool_calling: 'supported' | 'unsupported' | 'not_verified' | 'error' | string;
  tool_calling_status?: string;
  embeddings: 'connected' | 'not_configured' | 'unsupported' | 'error' | string;
  embedding_status?: string;
  tested_at: string;
  error?: string | null;
  error_message?: string | null;
}

export interface EvaluationRunDTO {
  id: number;
  eval_type: string;
  status: string;
  provider?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  dataset_version?: string | null;
  total_cases: number;
  passed_cases: number;
  pass_rate: number;
  decision_accuracy: number;
  average_latency_ms: number;
  total_tokens: number | null;
  estimated_cost?: number | null;
  started_at: string;
  completed_at?: string | null;
  results: EvaluationResultCaseDTO[] | Record<string, unknown>[];
}

export interface TrainingStatsDTO {
  total_approved_examples: number;
  languages?: Record<string, number>;
}

export interface KnowledgeSourceDTO {
  id: number;
  title: string;
  source_type: string;
  source_uri?: string | null;
  language: string;
  status: string;
  trust_level: string;
  version: number;
  document_count?: number;
  documents_count?: number;
  chunk_count?: number;
  chunks_count?: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryItemDTO {
  id: number;
  scope_type: 'user' | 'group' | 'global';
  scope_id: string;
  content: string;
  memory_type: string;
  confidence?: number;
  importance: number;
  sensitivity?: string;
  status?: string;
  is_pii_redacted?: boolean;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

export interface SkillDTO {
  name: string;
  description: string;
  version: string;
  scope: string;
  is_enabled: boolean;
  instructions_preview?: string;
  body?: string | null;
}

export interface MCPServerDTO {
  id: number;
  name: string;
  transport?: string;
  transport_type?: string;
  command_or_url?: string;
  endpoint_url?: string | null;
  command?: string | null;
  status: string;
  is_enabled: boolean;
  tools_count?: number;
  tool_count?: number;
  last_connected_at?: string | null;
  last_health_check?: string | null;
  error_message?: string | null;
}

export interface LearningCandidateDTO {
  id: number;
  conversation_id: number;
  customer_question: string;
  human_answer: string;
  suggested_faq_q?: string | null;
  suggested_faq_a?: string | null;
  category: string;
  language: string;
  source_quality: string;
  status: 'pending' | 'promoted' | 'approved' | 'rejected';
  created_at: string;
}

export interface EvaluationResultCaseDTO {
  case_id: string;
  case_name: string;
  passed: boolean;
  decision_correct: boolean;
  actual_decision: string;
  keyword_score: number;
  latency_ms: number;
  tokens: number;
}

export interface EvaluationSummaryDTO {
  total_cases: number;
  passed_cases: number;
  pass_rate: number;
  decision_accuracy: number;
  average_latency_ms: number;
  total_tokens: number | null;
  results: EvaluationResultCaseDTO[];
}

export interface PromptVersionDTO {
  id: number;
  version: string;
  name: string;
  template: string;
  is_active: boolean;
  created_by: string;
  created_at: string;
  activated_at?: string | null;
}

export interface AIDiagnosticsDTO {
  llm: { name?: string; model?: string; status: string };
  llm_provider?: { name?: string; model?: string; status: string };
  embedding: { name?: string; model?: string; status: string };
  embedding_provider?: { name?: string; model?: string; status: string };
  vector_store: { provider: string; status: string };
  rag_index: { documents_count: number; chunks_count: number; status: string };
  mcp: { active_servers: number; total_servers: number; status: string };
  signal_gateway: { status: string; api_url?: string; phone_number?: string };
  realtime?: {
    active_subscribers: number;
    total_events_emitted: number;
    dropped_events: number;
    status?: string;
  };
  capabilities?: {
    text?: string;
    streaming?: string;
    vision?: string;
    audio?: string;
    multimodal?: string;
  };
}



