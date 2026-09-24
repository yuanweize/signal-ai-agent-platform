import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AIStudioPage from './AIStudioPage';
import { api } from './api';

vi.mock('./api', () => ({
  api: {
    getAIOverview: vi.fn(),
    getAIRunsPage: vi.fn(),
    getAIRuns: vi.fn(),
    getAIRunDetail: vi.fn(),
    getAIDiagnostics: vi.fn(),
    getKnowledgeSources: vi.fn(),
    getKnowledgeSourceDetail: vi.fn(),
    getMemories: vi.fn(),
    getSkills: vi.fn(),
    getMCPServers: vi.fn(),
    getMCPServerDetail: vi.fn(),
    getLearningCandidates: vi.fn(),
    getPromptVersions: vi.fn(),
    getEvaluationRuns: vi.fn(),
    getUsageSummary: vi.fn(),
    getUsageTimeseries: vi.fn(),
    getModelUsage: vi.fn(),
  },
}));

describe('AI Studio Contract & Null Safety Regression', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAIOverview).mockResolvedValue({
      total_runs: 10,
      copilot_acceptance_rate: 0.85,
      memory_items_count: 5,
      avg_latency_ms: 150,
      total_tokens: 1200,
      time_range: '24h',
    });
  });

  it('renders evaluation history with total_tokens = null without crashing and displays placeholder', async () => {
    vi.mocked(api.getEvaluationRuns).mockResolvedValue([
      {
        id: 42,
        eval_type: 'live',
        status: 'completed',
        provider: 'openai',
        model: 'gpt-4o-mini',
        prompt_version: 'v1.0.0',
        dataset_version: 'golden_v1',
        total_cases: 10,
        passed_cases: 9,
        pass_rate: 0.9,
        decision_accuracy: 0.9,
        average_latency_ms: 245.4,
        total_tokens: null, // Critical: Backend allows null tokens
        estimated_cost: null,
        started_at: '2026-09-24T12:00:00Z',
        completed_at: '2026-09-24T12:00:05Z',
        results: [],
      },
    ]);

    render(
      <MemoryRouter>
        <AIStudioPage initialTab="evaluation" />
      </MemoryRouter>
    );

    // Wait for the evaluation run row to appear
    await waitFor(() => {
      expect(screen.getByText('#42')).toBeDefined();
    });

    // Check that average_latency_ms is rendered formatted
    expect(screen.getByText('245 ms')).toBeDefined();

    // Check that null total_tokens rendered '—' rather than crashing or rendering 'null'/'0'
    const dashElements = screen.getAllByText('—');
    expect(dashElements.length).toBeGreaterThan(0);
  });

  it('renders runs with real pagination totals from getAIRunsPage', async () => {
    vi.mocked(api.getAIRunsPage).mockResolvedValue({
      items: [
        {
          id: 101,
          trace_id: 'tr_test_101',
          conversation_id: 1,
          decision: 'reply',
          confidence: 0.95,
          latency_ms: 120,
          tokens: 50,
          total_tokens: 50,
          input_tokens: 30,
          output_tokens: 20,
          usage_source: 'provider',
          llm_call_count: 1,
          traffic_source: 'production',
          created_at: '2026-09-24T12:00:00Z',
          model: 'gpt-4o-mini',
          provider: 'openai',
          errors: null,
          retrieval: [],
          citations: [],
          memory: [],
          memories: [],
          tool_calls: [],
          model_calls: [],
        },
      ],
      total: 55,
    });

    render(
      <MemoryRouter>
        <AIStudioPage initialTab="runs" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/tr_test_10/i)).toBeDefined();
    });

    // Check pagination displays total runs and page count
    expect(screen.getByText(/Showing 1 of 55 runs • Page 1 of 3/i)).toBeDefined();
  });
});
