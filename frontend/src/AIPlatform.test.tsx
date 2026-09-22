import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProvenanceBadge } from './components/ProvenanceBadge';
import { CopilotDraftCard } from './components/CopilotDraftCard';
import { ExplainabilityDrawer } from './components/ExplainabilityDrawer';
import AIStudioPage from './AIStudioPage';
import { api } from './api';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    api: {
      getAIOverview: vi.fn(),
      getKnowledgeSources: vi.fn(),
      getMemories: vi.fn(),
      getSkills: vi.fn(),
      getMCPServers: vi.fn(),
      getLearningCandidates: vi.fn(),
      runEvaluation: vi.fn(),
      isAuthenticated: vi.fn().mockReturnValue(true),
    },
  };
});

describe('AI Platform v0.4 UI Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 1. ProvenanceBadge
  it('renders ProvenanceBadge for Customer, AI Auto, and Human+AI with Explain button', () => {
    const handleExplain = vi.fn();

    // Customer
    const { rerender } = render(<ProvenanceBadge origin="customer" />);
    expect(screen.getByText('Customer')).toBeInTheDocument();

    // AI Auto with Why button
    rerender(
      <ProvenanceBadge
        origin="ai_auto"
        model="gpt-4o-mini"
        promptVersion="v1.0"
        aiRunId={101}
        onExplain={handleExplain}
      />
    );
    expect(screen.getByText('AI Auto')).toBeInTheDocument();
    const whyBtn = screen.getByRole('button', { name: 'Why?' });
    expect(whyBtn).toBeInTheDocument();
    fireEvent.click(whyBtn);
    expect(handleExplain).toHaveBeenCalledOnce();

    // Human + AI
    rerender(
      <ProvenanceBadge
        origin="human_ai_assisted"
        adminIdentity="operator_jane"
      />
    );
    expect(screen.getByText('Human + AI')).toBeInTheDocument();
  });

  // 2. CopilotDraftCard
  it('renders CopilotDraftCard with Accept, Edit, and toggles Evidence', () => {
    const handleAccept = vi.fn();
    const handleEdit = vi.fn();
    const handleReject = vi.fn();
    const handleRegen = vi.fn();

    const mockSuggestion = {
      id: 55,
      conversation_id: 1,
      suggested_text: 'Thank you for reaching out! We offer organic beans.',
      status: 'pending' as const,
      generated_at: new Date().toISOString(),
      metadata: {
        skills_used: ['product-sales'],
        citations: [{ title: 'Catalog FAQ', snippet: 'Arabica beans are $15/bag.' }],
        memories_used: [{ content: 'Prefers dark roast' }],
        tools_called: [{ name: 'catalog_search' }],
      },
    };

    render(
      <CopilotDraftCard
        suggestion={mockSuggestion}
        onAccept={handleAccept}
        onEdit={handleEdit}
        onReject={handleReject}
        onRegenerate={handleRegen}
      />
    );

    // Text rendered
    expect(screen.getByText(/We offer organic beans/)).toBeInTheDocument();
    expect(screen.getByText('AI Copilot Draft')).toBeInTheDocument();

    // Toggle evidence
    const evidenceBtn = screen.getByText(/Evidence/);
    fireEvent.click(evidenceBtn);
    expect(screen.getByText('Catalog FAQ')).toBeInTheDocument();
    expect(screen.getByText(/Prefers dark roast/)).toBeInTheDocument();
    expect(screen.getByText(/catalog_search/)).toBeInTheDocument();

    // Accept action
    const acceptBtn = screen.getByRole('button', { name: /Accept & Send/i });
    fireEvent.click(acceptBtn);
    expect(handleAccept).toHaveBeenCalledOnce();

    // Edit in composer
    const editBtn = screen.getByRole('button', { name: /Edit in Composer/i });
    fireEvent.click(editBtn);
    expect(handleEdit).toHaveBeenCalledWith(mockSuggestion.suggested_text);
  });

  // 3. ExplainabilityDrawer
  it('renders ExplainabilityDrawer with telemetry, citations, and privacy boundaries', () => {
    const handleClose = vi.fn();
    const mockRun = {
      id: 101,
      trace_id: 'tr_778899aabbcc',
      conversation_id: 2,
      model: 'gpt-4o-mini',
      prompt_version: '1.0.0',
      decision: 'reply',
      latency_ms: 380,
      tokens: 145,
      skills: ['customer-support'],
      citations: [
        {
          chunk_id: 12,
          title: 'Warranty Policy',
          snippet: 'All products carry a 1-year warranty.',
          score: 0.88,
        },
      ],
      memories: [{ id: 1, content: 'VIP customer', type: 'fact' }],
      tool_calls: [{ name: 'check_warranty' }],
      created_at: new Date().toISOString(),
    };

    render(
      <ExplainabilityDrawer
        run={mockRun}
        isOpen={true}
        onClose={handleClose}
      />
    );

    expect(screen.getByText('AI Decision Context')).toBeInTheDocument();
    expect(screen.getByText('380 ms')).toBeInTheDocument();
    expect(screen.getByText('145 tokens used')).toBeInTheDocument();
    expect(screen.getByText('Warranty Policy')).toBeInTheDocument();
    expect(screen.getByText(/88% match/)).toBeInTheDocument();
    expect(screen.getByText(/VIP customer/)).toBeInTheDocument();
    expect(screen.getByText('Privacy Guard')).toBeInTheDocument();
  });

  // 4. AIStudioPage
  it('renders AIStudioPage tabs and switches views', async () => {
    (api.getAIOverview as any).mockResolvedValue({
      total_runs: 125,
      avg_latency_ms: 320,
      total_tokens: 45000,
      copilot_suggestions_count: 35,
      copilot_acceptance_rate: 0.82,
      copilot_avg_edit_ratio: 0.12,
      knowledge_sources_count: 6,
      knowledge_chunks_count: 48,
      memory_items_count: 14,
    });

    (api.getSkills as any).mockResolvedValue([
      {
        name: 'product-sales',
        description: 'Handles product inquiry and recommendations',
        version: '1.0.0',
        scope: 'all',
        is_enabled: true,
      },
    ]);

    render(
      <MemoryRouter>
        <AIStudioPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('AI Platform v0.4 Studio')).toBeInTheDocument();
      expect(screen.getByText('125')).toBeInTheDocument();
      expect(screen.getByText('82.0%')).toBeInTheDocument();
    });

    // Switch to Progressive Skills tab
    const skillsTab = screen.getByRole('button', { name: /Progressive Skills/i });
    fireEvent.click(skillsTab);

    await waitFor(() => {
      expect(screen.getByText('product-sales')).toBeInTheDocument();
      expect(screen.getByText('Handles product inquiry and recommendations')).toBeInTheDocument();
    });
  });
});
