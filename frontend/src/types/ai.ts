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
  created_at: string;
}

export interface AIOverviewMetricsDTO {
  total_runs: number;
  avg_latency_ms: number;
  total_tokens: number;
  copilot_suggestions_count: number;
  copilot_acceptance_rate: number;
  copilot_avg_edit_ratio: number;
  knowledge_sources_count: number;
  knowledge_chunks_count: number;
  memory_items_count: number;
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
  chunk_count?: number;
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
  importance: number;
  is_pii_redacted: boolean;
  created_by: string;
  created_at: string;
}

export interface SkillDTO {
  name: string;
  description: string;
  version: string;
  scope: string;
  is_enabled: boolean;
  instructions_preview?: string;
}

export interface MCPServerDTO {
  id: number;
  name: string;
  transport_type: string;
  endpoint_url?: string | null;
  command?: string | null;
  status: string;
  is_enabled: boolean;
  tool_count?: number;
  last_health_check?: string | null;
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
  total_tokens: number;
  results: EvaluationResultCaseDTO[];
}
