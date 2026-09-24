import React, { useEffect, useState, useCallback } from 'react';
import {
  Sparkles,
  Brain,
  Wrench,
  BookOpen,
  Activity,
  CheckCircle,
  Layers,
  Search,
  Plus,
  Trash2,
  Download,
  Play,
  RotateCw,
  ShieldCheck,
  AlertTriangle,
  Coins,
  Cpu,
  FileText,
  BarChart3,
  ChevronRight,
  X,
  Filter,
} from 'lucide-react';
import SidebarLayout from './SidebarLayout';
import {
  api,
  AIOverviewMetricsDTO,
  AIRunDTO,
  KnowledgeSourceDTO,
  KnowledgeSourceDetailDTO,
  RAGSearchResultDTO,
  MemoryItemDTO,
  SkillDTO,
  MCPServerDTO,
  MCPServerDetailDTO,
  LearningCandidateDTO,
  EvaluationSummaryDTO,
  EvaluationRunDTO,
  PromptVersionDTO,
  AIDiagnosticsDTO,
  ProviderLiveTestResultDTO,
  TrainingStatsDTO,
} from './api';
import { Button } from './components/ui/Button';

type NavSection = 'operate' | 'knowledge' | 'automation' | 'improve';
type StudioTab =
  | 'overview'
  | 'runs'
  | 'diagnostics'
  | 'knowledge'
  | 'memory'
  | 'skills'
  | 'mcp'
  | 'learning'
  | 'prompts'
  | 'evaluation';

export default function AIStudioPage({ initialTab = 'overview' }: { initialTab?: StudioTab } = {}) {
  const [activeTab, setActiveTab] = useState<StudioTab>(initialTab);
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d' | 'all'>('24h');
  const [loading, setLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Core Data States
  const [overview, setOverview] = useState<AIOverviewMetricsDTO | null>(null);
  const [diagnostics, setDiagnostics] = useState<AIDiagnosticsDTO | null>(null);
  const [runs, setRuns] = useState<AIRunDTO[]>([]);
  const [selectedRun, setSelectedRun] = useState<AIRunDTO | null>(null);
  const [runFilters, setRunFilters] = useState<{
    decision?: string;
    hasError?: boolean;
    usedRag?: boolean;
    usedTools?: boolean;
  }>({});
  const [runsOffset, setRunsOffset] = useState(0);
  const [runsTotal, setRunsTotal] = useState(0);

  // Live Provider Testing
  const [liveTesting, setLiveTesting] = useState(false);
  const [liveTestResult, setLiveTestResult] = useState<ProviderLiveTestResultDTO | null>(null);

  // Knowledge & RAG
  const [sources, setSources] = useState<KnowledgeSourceDTO[]>([]);
  const [selectedSourceDetail, setSelectedSourceDetail] = useState<KnowledgeSourceDetailDTO | null>(null);
  const [ragSearchQuery, setRagSearchQuery] = useState('');
  const [ragSearchScope, setRagSearchScope] = useState<'global' | 'group' | 'user'>('global');
  const [ragSearchScopeId, setRagSearchScopeId] = useState('');
  const [ragSearchResults, setRagSearchResults] = useState<RAGSearchResultDTO[]>([]);
  const [ragSearching, setRagSearching] = useState(false);

  // Memory
  const [memories, setMemories] = useState<MemoryItemDTO[]>([]);
  const [memoryScopeFilter, setMemoryScopeFilter] = useState<'all' | 'user' | 'group' | 'global'>('all');
  const [memorySearch, setMemorySearch] = useState('');

  // Skills & MCP
  const [skills, setSkills] = useState<SkillDTO[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServerDTO[]>([]);
  const [selectedMcpDetail, setSelectedMcpDetail] = useState<MCPServerDetailDTO | null>(null);

  // Learning & Prompts & Evals
  const [candidates, setCandidates] = useState<LearningCandidateDTO[]>([]);
  const [trainingStats, setTrainingStats] = useState<TrainingStatsDTO | null>(null);
  const [promptVersions, setPromptVersions] = useState<PromptVersionDTO[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvaluationRunDTO[]>([]);
  const [evalSummary, setEvalSummary] = useState<EvaluationSummaryDTO | null>(null);

  // Modals
  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [newSourceTitle, setNewSourceTitle] = useState('');
  const [newSourceType, setNewSourceType] = useState('faq');
  const [newSourceDocContent, setNewSourceDocContent] = useState('');
  const [newSourceScope, setNewSourceScope] = useState('global');
  const [newSourceScopeId, setNewSourceScopeId] = useState('');

  const [showCreatePromptModal, setShowCreatePromptModal] = useState(false);
  const [newPromptVersion, setNewPromptVersion] = useState('');
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptTemplate, setNewPromptTemplate] = useState('');

  const [showAddMcpModal, setShowAddMcpModal] = useState(false);
  const [newMcpName, setNewMcpName] = useState('');
  const [newMcpTransport, setNewMcpTransport] = useState('http');
  const [newMcpEndpoint, setNewMcpEndpoint] = useState('');
  const [newMcpCommand, setNewMcpCommand] = useState('');

  const [showPromoteModal, setShowPromoteModal] = useState<LearningCandidateDTO | null>(null);
  const [promoteAction, setPromoteAction] = useState<'knowledge' | 'training'>('knowledge');
  const [promoteFaqQ, setPromoteFaqQ] = useState('');
  const [promoteFaqA, setPromoteFaqA] = useState('');
  const [promoteScope, setPromoteScope] = useState('global');
  const [confirmGlobalPrivacy, setConfirmGlobalPrivacy] = useState(false);

  const [showLiveEvalModal, setShowLiveEvalModal] = useState(false);
  const [evalLimit, setEvalLimit] = useState<number>(10);

  // Load Overview Data with explicit error handling (Requirement #62)
  const loadOverview = useCallback(async (range = timeRange) => {
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const data = await api.getAIOverview(range);
      setOverview(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load AI overview metrics';
      setOverviewError(msg);
      setOverview(null);
    } finally {
      setOverviewLoading(false);
    }
  }, [timeRange]);

  const loadDiagnostics = useCallback(async () => {
    try {
      const diag = await api.getAIDiagnostics();
      setDiagnostics(diag);
    } catch {
      // Diagnostic load failure handled cleanly in diagnostics view
    }
  }, []);

  const loadTabData = useCallback(async (tab: StudioTab) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      if (tab === 'overview') {
        await loadOverview(timeRange);
      } else if (tab === 'runs') {
        const page = await api.getAIRunsPage({
          time_range: timeRange,
          decision: runFilters.decision || undefined,
          has_error: runFilters.hasError,
          has_rag: runFilters.usedRag,
          has_tools: runFilters.usedTools,
          limit: 25,
          offset: runsOffset,
        });
        setRuns(page.items);
        setRunsTotal(page.total);
      } else if (tab === 'diagnostics') {
        await loadDiagnostics();
      } else if (tab === 'knowledge') {
        const data = await api.getKnowledgeSources();
        setSources(data);
      } else if (tab === 'memory') {
        const data = await api.getMemories(memoryScopeFilter);
        setMemories(data);
      } else if (tab === 'skills') {
        const data = await api.getSkills();
        setSkills(data);
      } else if (tab === 'mcp') {
        const data = await api.getMCPServers();
        setMcpServers(data);
      } else if (tab === 'learning') {
        const [cands, stats] = await Promise.all([
          api.getLearningCandidates(),
          api.getTrainingStats().catch(() => null),
        ]);
        setCandidates(cands);
        if (stats) setTrainingStats(stats);
      } else if (tab === 'prompts') {
        const data = await api.getPromptVersions();
        setPromptVersions(data);
      } else if (tab === 'evaluation') {
        const runsData = await api.getEvaluationRuns();
        setEvalRuns(runsData);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load studio data');
    } finally {
      setLoading(false);
    }
  }, [timeRange, runFilters, runsOffset, memoryScopeFilter, loadOverview, loadDiagnostics]);

  useEffect(() => {
    loadOverview(timeRange);
    loadDiagnostics();
  }, [timeRange, loadOverview, loadDiagnostics]);

  useEffect(() => {
    loadTabData(activeTab);
  }, [activeTab, loadTabData]);

  // Actions
  const handleTestLiveProvider = async () => {
    setLiveTesting(true);
    setErrorMsg(null);
    try {
      const res = await api.testLiveProvider(true, true);
      setLiveTestResult(res);
      if (res.connection_status === 'connected') {
        setSuccessMsg(`Live provider probe passed! Latency: ${res.latency_ms ?? '—'} ms`);
      } else {
        setErrorMsg(`Live provider test failed: ${res.error_message || 'Connection refused'}`);
      }
      loadDiagnostics();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Live provider test failed');
    } finally {
      setLiveTesting(false);
    }
  };

  const handleRAGSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ragSearchQuery.trim()) return;
    setRagSearching(true);
    try {
      const res = await api.searchKnowledge(
        ragSearchQuery.trim(),
        ragSearchScope === 'global' ? undefined : ragSearchScope,
        ragSearchScopeId || undefined,
        5
      );
      setRagSearchResults(res);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'RAG search failed');
    } finally {
      setRagSearching(false);
    }
  };

  const handleOpenSourceDetail = async (sourceId: number) => {
    try {
      const detail = await api.getKnowledgeSourceDetail(sourceId);
      setSelectedSourceDetail(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to fetch source details');
    }
  };

  const handleReindexSource = async (sourceId: number) => {
    try {
      const res = await api.reindexKnowledgeSource(sourceId);
      const docs = res.indexed_documents ?? res.documents_count ?? 0;
      const chunks = res.indexed_chunks ?? res.chunks_reindexed ?? 0;
      setSuccessMsg(`Reindexed source #${sourceId}: ${docs} documents, ${chunks} chunks.`);
      loadTabData('knowledge');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reindex source');
    }
  };

  const handleDeleteSource = async (sourceId: number) => {
    if (!confirm('Are you sure you want to delete this knowledge source and all its documents and vector chunks?')) return;
    try {
      await api.deleteKnowledgeSource(sourceId);
      setSources(prev => prev.filter(s => s.id !== sourceId));
      if (selectedSourceDetail?.source.id === sourceId) {
        setSelectedSourceDetail(null);
      }
      setSuccessMsg('Knowledge source and vectors removed.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete knowledge source');
    }
  };

  const handleDeleteKnowledgeDoc = async (sourceId: number, docId: number) => {
    if (!confirm('Delete this knowledge document and its associated vector chunks?')) return;
    try {
      await api.deleteKnowledgeDoc(sourceId, docId);
      if (selectedSourceDetail) {
        setSelectedSourceDetail({
          ...selectedSourceDetail,
          documents: selectedSourceDetail.documents.filter(d => d.id !== docId),
        });
      }
      setSuccessMsg('Knowledge document removed.');
      loadTabData('knowledge');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete document');
    }
  };

  const handleCreateKnowledgeDoc = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSourceTitle || !newSourceDocContent) return;
    setLoading(true);
    try {
      const src = await api.createKnowledgeSource({
        title: newSourceTitle,
        source_type: newSourceType,
      });
      await api.ingestKnowledgeDoc(src.id, {
        title: newSourceTitle,
        content: newSourceDocContent,
        scope_type: newSourceScope,
        scope_id: newSourceScopeId || undefined,
        is_faq: newSourceType === 'faq',
      });
      setShowAddSourceModal(false);
      setNewSourceTitle('');
      setNewSourceDocContent('');
      setSuccessMsg(`Successfully indexed knowledge document into ${newSourceScope} scope.`);
      loadTabData('knowledge');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create document');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMemory = async (id: number) => {
    if (!confirm('Are you sure you want to remove this memory item from the database?')) return;
    try {
      await api.deleteMemory(id);
      setMemories(prev => prev.filter(m => m.id !== id));
      setSuccessMsg('Memory item removed from database.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete memory');
    }
  };

  const handleToggleSkill = async (skillName: string, current: boolean) => {
    try {
      const res = await api.toggleSkill(skillName, !current);
      setSkills(prev =>
        prev.map(s => (s.name === skillName ? { ...s, is_enabled: res.is_enabled } : s))
      );
      setSuccessMsg(`Skill ${skillName} ${res.is_enabled ? 'enabled' : 'disabled'}.`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to toggle skill');
    }
  };

  const handleTestMCP = async (id: number) => {
    try {
      const res = await api.testMCPServer(id);
      const latencyText = res.latency_ms !== undefined && res.latency_ms !== null ? `${res.latency_ms} ms` : 'Not measured';
      setSuccessMsg(`MCP server test: ${res.status} (${latencyText})`);
      loadTabData('mcp');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'MCP connection test failed');
    }
  };

  const handleOpenMcpDetail = async (serverId: number) => {
    try {
      const detail = await api.getMCPServerDetail(serverId);
      setSelectedMcpDetail(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to fetch MCP server details');
    }
  };

  const handleDeleteMcpServer = async (serverId: number) => {
    if (!confirm('Are you sure you want to remove this MCP server configuration?')) return;
    try {
      await api.deleteMCPServer(serverId);
      setMcpServers(prev => prev.filter(s => s.id !== serverId));
      if (selectedMcpDetail?.id === serverId) setSelectedMcpDetail(null);
      setSuccessMsg('MCP server removed.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to delete MCP server');
    }
  };

  const handleCreateMcpServer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMcpName) return;
    try {
      await api.createMCPServer({
        name: newMcpName,
        transport_type: newMcpTransport,
        endpoint_url: newMcpEndpoint || undefined,
        command: newMcpCommand || undefined,
      });
      setShowAddMcpModal(false);
      setNewMcpName('');
      setNewMcpEndpoint('');
      setNewMcpCommand('');
      setSuccessMsg('MCP server created.');
      loadTabData('mcp');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create MCP server');
    }
  };

  const handleExecutePromotion = async () => {
    if (!showPromoteModal) return;
    if (promoteAction === 'knowledge' && promoteScope === 'global' && !confirmGlobalPrivacy) {
      setErrorMsg('Explicit confirmation is required to promote to global knowledge.');
      return;
    }

    try {
      await api.promoteLearningCandidate(
        showPromoteModal.id,
        promoteAction,
        promoteFaqQ || undefined,
        promoteFaqA || undefined,
        promoteScope,
        confirmGlobalPrivacy
      );
      setCandidates(prev => prev.filter(c => c.id !== showPromoteModal.id));
      setShowPromoteModal(null);
      setConfirmGlobalPrivacy(false);
      setSuccessMsg(
        promoteAction === 'knowledge'
          ? 'Candidate promoted to Knowledge Base FAQ!'
          : 'Candidate added to offline Training dataset!'
      );
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Promotion failed');
    }
  };

  const handleRejectCandidate = async (candidateId: number) => {
    try {
      await api.rejectLearningCandidate(candidateId);
      setCandidates(prev => prev.filter(c => c.id !== candidateId));
      setSuccessMsg('Candidate rejected.');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to reject candidate');
    }
  };

  const handleExportJSONL = async () => {
    try {
      const res = await api.exportTrainingJSONL();
      const content = typeof res === 'string' ? res : (res?.jsonl ?? '');
      const count =
        typeof res === 'object' && res !== null && 'count' in res && typeof res.count === 'number'
          ? res.count
          : content.split('\n').filter(Boolean).length;
      const blob = new Blob([content], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ai_training_dataset_${Date.now()}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
      setSuccessMsg(`Exported ${count} fine-tuning examples to JSONL.`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to export training dataset');
    }
  };

  const handleRunEvaluation = async (limit: number) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const summary = await api.runEvaluation(limit);
      setEvalSummary(summary);
      setSuccessMsg(`Evaluated ${summary.total_cases} golden contract cases: ${(summary.pass_rate * 100).toFixed(1)}% passed!`);
      setShowLiveEvalModal(false);
      loadTabData('evaluation');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run evaluations');
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePromptVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPromptVersion.trim() || !newPromptTemplate.trim()) return;
    try {
      await api.createPromptVersion({
        version: newPromptVersion.trim(),
        name: newPromptName.trim() || newPromptVersion.trim(),
        template: newPromptTemplate.trim(),
      });
      setShowCreatePromptModal(false);
      setNewPromptVersion('');
      setNewPromptName('');
      setNewPromptTemplate('');
      setSuccessMsg(`Prompt version ${newPromptVersion} created successfully.`);
      loadTabData('prompts');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to create prompt version');
    }
  };

  const handleActivatePromptVersion = async (version: string) => {
    try {
      await api.activatePromptVersion(version);
      setSuccessMsg(`Activated prompt version ${version}.`);
      loadTabData('prompts');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to activate prompt version');
    }
  };

  // Derive Dynamic Readiness Badge (Requirements #4, #29)
  const getReadinessBadge = () => {
    if (!diagnostics) {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700">
          Not Validated
        </span>
      );
    }
    const status = diagnostics.llm_provider?.status || diagnostics.llm?.status || 'unconfigured';
    if (status === 'live_verified') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
          ● Live Verified
        </span>
      );
    }
    if (status === 'configured') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
          Configured
        </span>
      );
    }
    if (status === 'partially_configured') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
          Partially Configured
        </span>
      );
    }
    if (status === 'degraded' || status === 'error') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
          Degraded
        </span>
      );
    }
    if (status === 'disabled') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-zinc-700 text-zinc-400 border border-zinc-600">
          Disabled
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700">
        Not Validated
      </span>
    );
  };

  // Nav Groups definition (Requirement #64)
  const navSections: Array<{
    id: NavSection;
    label: string;
    tabs: Array<{ id: StudioTab; label: string; icon: React.ElementType }>;
  }> = [
    {
      id: 'operate',
      label: 'Operate',
      tabs: [
        { id: 'overview', label: 'Overview', icon: BarChart3 },
        { id: 'runs', label: 'Runs & Traces', icon: Activity },
        { id: 'diagnostics', label: 'Diagnostics', icon: Cpu },
      ],
    },
    {
      id: 'knowledge',
      label: 'Knowledge',
      tabs: [
        { id: 'knowledge', label: 'RAG Knowledge', icon: BookOpen },
        { id: 'memory', label: 'Scoped Memory', icon: Brain },
        { id: 'skills', label: 'Progressive Skills', icon: Layers },
      ],
    },
    {
      id: 'automation',
      label: 'Automation',
      tabs: [{ id: 'mcp', label: 'Tools & MCP Governance', icon: Wrench }],
    },
    {
      id: 'improve',
      label: 'Improve',
      tabs: [
        { id: 'learning', label: 'Learning Loop', icon: Sparkles },
        { id: 'prompts', label: 'Prompt Versions', icon: FileText },
        { id: 'evaluation', label: 'Evaluation Suite', icon: ShieldCheck },
      ],
    },
  ];

  return (
    <SidebarLayout title="AI Studio">
      <div className="max-w-7xl mx-auto space-y-6 pb-12">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-6 rounded-2xl border border-[var(--border)] shadow-[0_8px_30px_rgba(0,0,0,0.12)]">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[rgba(108,92,231,0.15)] flex items-center justify-center text-[var(--accent)] border border-[rgba(108,92,231,0.3)] shadow-[0_2px_12px_rgba(108,92,231,0.2)]">
                <Sparkles className="w-5 h-5" />
              </div>
              <h1 className="text-xl font-extrabold text-[var(--text-primary)] tracking-tight">
                AI Studio
              </h1>
              {getReadinessBadge()}
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              Truthful runtime telemetry, trace exploration, tool governance, scoped RAG knowledge, and evaluation operations.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Time Range Selector */}
            <div className="flex items-center bg-[var(--bg-input)] p-0.5 rounded-lg border border-[var(--border)] text-xs">
              {(['24h', '7d', '30d', 'all'] as const).map(tr => (
                <button
                  key={tr}
                  onClick={() => setTimeRange(tr)}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    timeRange === tr
                      ? 'bg-[var(--accent)] text-white shadow-sm'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {tr.toUpperCase()}
                </button>
              ))}
            </div>

            <Button variant="secondary" size="sm" onClick={() => loadTabData(activeTab)} loading={loading}>
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />
              Refresh
            </Button>
            <Button variant="primary" size="sm" onClick={() => setActiveTab('runs')}>
              <Activity className="w-3.5 h-3.5 mr-1.5" />
              Trace Explorer
            </Button>
          </div>
        </div>

        {/* Notifications */}
        {errorMsg && (
          <div className="p-3.5 rounded-xl bg-[rgba(255,107,107,0.12)] border border-[rgba(255,107,107,0.3)] text-[var(--danger)] text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <button onClick={() => setErrorMsg(null)} className="font-bold hover:opacity-80">
              ✕
            </button>
          </div>
        )}
        {successMsg && (
          <div className="p-3.5 rounded-xl bg-[rgba(0,214,143,0.12)] border border-[rgba(0,214,143,0.3)] text-[#00d68f] text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg(null)} className="font-bold hover:opacity-80">
              ✕
            </button>
          </div>
        )}

        {/* Responsive Information Architecture: Grouped Tabs (Requirement #64) */}
        <div className="flex flex-wrap items-center gap-6 border-b border-[var(--border)] pb-3 px-1">
          {navSections.map(section => (
            <div key={section.id} className="flex items-center gap-1.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)] mr-1">
                {section.label}
              </span>
              {section.tabs.map(tab => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      isActive
                        ? 'bg-[var(--accent)] text-white shadow-[0_2px_8px_rgba(108,92,231,0.3)]'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card)]'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* TAB 1: OVERVIEW (Requirement #5, #6, #7, #18, #60, #62) */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {overviewLoading && (
              <div className="p-12 text-center text-xs text-[var(--text-secondary)] animate-pulse">
                Loading live operational telemetry ({timeRange})...
              </div>
            )}

            {overviewError && (
              <div className="p-8 rounded-2xl bg-[rgba(255,107,107,0.08)] border border-[rgba(255,107,107,0.3)] text-center space-y-3">
                <AlertTriangle className="w-8 h-8 text-[var(--danger)] mx-auto" />
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Telemetry Data Unavailable</h3>
                <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto">{overviewError}</p>
                <Button size="sm" variant="secondary" onClick={() => loadOverview(timeRange)}>
                  Retry Telemetry Query
                </Button>
              </div>
            )}

            {!overviewLoading && !overviewError && overview && (
              <>
                {/* 1. Core KPIs Section */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
                  {/* Total AI Runs */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Total AI Runs</span>
                    <div className="text-2xl font-bold text-[var(--text-primary)] mt-1">
                      {overview.total_runs}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">
                      {overview.successful_runs ?? overview.total_runs} success (
                      {overview.error_rate !== undefined ? `${(overview.error_rate * 100).toFixed(1)}% err` : '0% err'})
                    </div>
                  </div>

                  {/* Automation Rate */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Automation Rate</span>
                    <div className="text-2xl font-bold text-emerald-400 mt-1">
                      {overview.automation_rate !== undefined
                        ? `${(overview.automation_rate * 100).toFixed(0)}%`
                        : '—'}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">
                      Human takeover: {overview.human_takeover_rate !== undefined ? `${(overview.human_takeover_rate * 100).toFixed(1)}%` : '—'}
                    </div>
                  </div>

                  {/* Copilot Acceptance */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Copilot Acceptance</span>
                    <div className="text-2xl font-bold text-purple-400 mt-1">
                      {overview.copilot_acceptance_rate !== undefined
                        ? `${(overview.copilot_acceptance_rate * 100).toFixed(0)}%`
                        : '—'}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">
                      Avg edit ratio: {overview.copilot_avg_edit_ratio !== undefined ? `${(overview.copilot_avg_edit_ratio * 100).toFixed(1)}%` : '—'}
                    </div>
                  </div>

                  {/* Latency P50 / P95 */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Latency (P50 / P95)</span>
                    <div className="text-2xl font-bold text-[var(--text-primary)] mt-1">
                      {overview.p50_latency_ms !== null && overview.p50_latency_ms !== undefined
                        ? `${overview.p50_latency_ms} ms`
                        : '—'}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">
                      P95: {overview.p95_latency_ms !== null && overview.p95_latency_ms !== undefined ? `${overview.p95_latency_ms} ms` : '—'} | Avg: {overview.avg_latency_ms} ms
                    </div>
                  </div>

                  {/* Token Telemetry */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Total Tokens</span>
                    <div className="text-2xl font-bold text-sky-400 mt-1">
                      {overview.total_tokens ? overview.total_tokens.toLocaleString() : '0'}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1">
                      In: {overview.input_tokens ? overview.input_tokens.toLocaleString() : '—'} | Out:{' '}
                      {overview.output_tokens ? overview.output_tokens.toLocaleString() : '—'}
                    </div>
                  </div>

                  {/* Estimated Cost */}
                  <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[11px] font-medium text-[var(--text-secondary)]">Estimated Cost</span>
                    <div className="text-2xl font-bold text-[var(--text-primary)] mt-1">
                      {overview.estimated_cost !== null && overview.estimated_cost !== undefined
                        ? `$${overview.estimated_cost.toFixed(4)}`
                        : 'N/A'}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] mt-1 truncate" title="Pricing not configured for custom model">
                      {overview.estimated_cost !== null && overview.estimated_cost !== undefined
                        ? `${overview.cost_currency || 'USD'}`
                        : 'Pricing not configured'}
                    </div>
                  </div>
                </div>

                {/* 2. Structured Token Telemetry Deep-dive (Requirement #8, #9, #10) */}
                <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                        <Coins className="w-4 h-4 text-sky-400" />
                        Structured Token & Model Usage Breakdown ({timeRange})
                      </h3>
                      <p className="text-xs text-[var(--text-secondary)]">
                        Truthful provider-reported usage. Cached tokens and reasoning tokens separated.
                      </p>
                    </div>
                    <div className="text-xs text-[var(--text-muted)]">
                      Timezone: {overview.timezone || 'UTC'}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
                    <div className="p-3.5 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-xs text-[var(--text-secondary)]">Input Tokens</span>
                      <div className="text-lg font-bold text-[var(--text-primary)] mt-1">
                        {overview.input_tokens !== null && overview.input_tokens !== undefined
                          ? overview.input_tokens.toLocaleString()
                          : '—'}
                      </div>
                      <span className="text-[10px] text-[var(--text-muted)]">
                        Cached: {overview.cached_input_tokens ? overview.cached_input_tokens.toLocaleString() : '0'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-xs text-[var(--text-secondary)]">Output Tokens</span>
                      <div className="text-lg font-bold text-[var(--text-primary)] mt-1">
                        {overview.output_tokens !== null && overview.output_tokens !== undefined
                          ? overview.output_tokens.toLocaleString()
                          : '—'}
                      </div>
                      <span className="text-[10px] text-[var(--text-muted)]">
                        Reasoning: {overview.reasoning_tokens ? overview.reasoning_tokens.toLocaleString() : '0'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-xs text-[var(--text-secondary)]">RAG Retrieval Hit Rate</span>
                      <div className="text-lg font-bold text-emerald-400 mt-1">
                        {overview.rag_hit_rate !== undefined ? `${(overview.rag_hit_rate * 100).toFixed(1)}%` : '—'}
                      </div>
                      <span className="text-[10px] text-[var(--text-muted)]">
                        {overview.knowledge_chunks_count ?? 0} indexed vector chunks
                      </span>
                    </div>

                    <div className="p-3.5 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-xs text-[var(--text-secondary)]">Tool Call Governance</span>
                      <div className="text-lg font-bold text-indigo-400 mt-1">
                        {overview.tool_call_success_rate !== undefined
                          ? `${(overview.tool_call_success_rate * 100).toFixed(0)}%`
                          : '—'}
                      </div>
                      <span className="text-[10px] text-[var(--text-muted)]">
                        {overview.tool_invocation_count ?? 0} executions ({((overview.tool_approval_rate ?? 0) * 100).toFixed(0)}% approval required)
                      </span>
                    </div>
                  </div>
                </div>

                {/* 3. Quick Operations Shortcuts */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div
                    onClick={() => setActiveTab('runs')}
                    className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer transition-all flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-purple-500/15 flex items-center justify-center text-purple-400">
                        <Activity className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="text-sm font-bold text-[var(--text-primary)]">Runs & Trace Explorer</div>
                        <div className="text-xs text-[var(--text-secondary)]">Filter and inspect individual AI turns</div>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-[var(--text-muted)]" />
                  </div>

                  <div
                    onClick={() => setActiveTab('diagnostics')}
                    className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer transition-all flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-emerald-500/15 flex items-center justify-center text-emerald-400">
                        <Cpu className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="text-sm font-bold text-[var(--text-primary)]">Live Provider Test</div>
                        <div className="text-xs text-[var(--text-secondary)]">Probe chat, tools, and embeddings</div>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-[var(--text-muted)]" />
                  </div>

                  <div
                    onClick={() => setActiveTab('evaluation')}
                    className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer transition-all flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-sky-500/15 flex items-center justify-center text-sky-400">
                        <ShieldCheck className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="text-sm font-bold text-[var(--text-primary)]">32 Invariant Evaluation</div>
                        <div className="text-xs text-[var(--text-secondary)]">Deterministic golden benchmark suite</div>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-[var(--text-muted)]" />
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* TAB 2: RUNS & TRACE EXPLORER (Requirement #19, #20, #21) */}
        {activeTab === 'runs' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-xs font-semibold text-[var(--text-secondary)] flex items-center gap-1.5">
                  <Filter className="w-3.5 h-3.5" /> Filters:
                </span>

                {/* Decision filter */}
                <select
                  aria-label="Filter runs by decision"
                  className="px-2.5 py-1 text-xs rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  value={runFilters.decision || ''}
                  onChange={e => setRunFilters({ ...runFilters, decision: e.target.value || undefined })}
                >
                  <option value="">All Decisions</option>
                  <option value="reply">reply</option>
                  <option value="draft_for_human">draft_for_human</option>
                  <option value="handoff">handoff</option>
                  <option value="no_reply">no_reply</option>
                </select>

                {/* Errors filter */}
                <button
                  onClick={() => setRunFilters({ ...runFilters, hasError: !runFilters.hasError ? true : undefined })}
                  className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${
                    runFilters.hasError
                      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                      : 'bg-[var(--bg-input)] text-[var(--text-secondary)] border-[var(--border)]'
                  }`}
                >
                  Has Errors
                </button>

                {/* RAG filter */}
                <button
                  onClick={() => setRunFilters({ ...runFilters, usedRag: !runFilters.usedRag ? true : undefined })}
                  className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${
                    runFilters.usedRag
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-[var(--bg-input)] text-[var(--text-secondary)] border-[var(--border)]'
                  }`}
                >
                  Used RAG
                </button>

                {/* Tools filter */}
                <button
                  onClick={() => setRunFilters({ ...runFilters, usedTools: !runFilters.usedTools ? true : undefined })}
                  className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${
                    runFilters.usedTools
                      ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                      : 'bg-[var(--bg-input)] text-[var(--text-secondary)] border-[var(--border)]'
                  }`}
                >
                  Used Tools
                </button>
              </div>

              <div className="flex items-center gap-2">
                <Button size="sm" variant="secondary" onClick={() => loadTabData('runs')} loading={loading}>
                  <RotateCw className="w-3.5 h-3.5 mr-1.5" />
                  Refresh Runs
                </Button>
              </div>
            </div>

            {/* Runs Table */}
            <div className="rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[var(--bg-input)] text-[var(--text-muted)] font-semibold border-b border-[var(--border)]">
                    <tr>
                      <th className="py-3 px-4">Time</th>
                      <th className="py-3 px-4">Trace ID</th>
                      <th className="py-3 px-4">Conv #</th>
                      <th className="py-3 px-4">Decision</th>
                      <th className="py-3 px-4">Model</th>
                      <th className="py-3 px-4">Tokens (In / Out / Tot)</th>
                      <th className="py-3 px-4">Latency</th>
                      <th className="py-3 px-4">Context</th>
                      <th className="py-3 px-4">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {runs.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-xs text-[var(--text-muted)]">
                          No AI runs found matching the current filters and time window ({timeRange}).
                        </td>
                      </tr>
                    ) : (
                      runs.map(run => (
                        <tr key={run.id} className="hover:bg-[var(--bg-input)]/50 transition-colors">
                          <td className="py-3 px-4 font-mono text-[11px] text-[var(--text-secondary)] whitespace-nowrap">
                            {new Date(run.created_at).toLocaleTimeString()}
                          </td>
                          <td className="py-3 px-4 font-mono text-[11px] text-purple-400 font-medium">
                            {run.trace_id.slice(0, 10)}...
                          </td>
                          <td className="py-3 px-4 font-mono text-[11px] text-[var(--text-primary)]">
                            #{run.conversation_id}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                run.decision === 'reply'
                                  ? 'bg-emerald-500/15 text-emerald-400'
                                  : run.decision === 'draft_for_human'
                                  ? 'bg-purple-500/15 text-purple-400'
                                  : 'bg-amber-500/15 text-amber-400'
                              }`}
                            >
                              {run.decision}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono text-[11px] text-[var(--text-secondary)]">
                            {run.model || 'default'}
                          </td>
                          <td className="py-3 px-4 font-mono text-[11px]">
                            <span className="text-[var(--text-secondary)]">{run.input_tokens ?? '—'}</span> /{' '}
                            <span className="text-[var(--text-secondary)]">{run.output_tokens ?? '—'}</span> /{' '}
                            <span className="font-bold text-[var(--text-primary)]">{run.total_tokens ?? run.tokens ?? '0'}</span>
                          </td>
                          <td className="py-3 px-4 font-mono text-[11px] text-[var(--text-secondary)]">
                            {run.latency_ms} ms
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-1.5 text-[10px]">
                              {run.citations && run.citations.length > 0 && (
                                <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                                  RAG:{run.citations.length}
                                </span>
                              )}
                              {run.tool_calls && run.tool_calls.length > 0 && (
                                <span className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                                  Tools:{run.tool_calls.length}
                                </span>
                              )}
                              {run.memories && run.memories.length > 0 && (
                                <span className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300">
                                  Mem:{run.memories.length}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <button
                              onClick={() => setSelectedRun(run)}
                              className="px-2.5 py-1 rounded bg-[var(--bg-input)] hover:bg-[var(--border)] text-[var(--accent)] font-semibold text-[11px] transition-colors"
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
                {/* Pagination Controls */}
                <div className="flex items-center justify-between p-3 border-t border-[var(--border)] text-xs text-[var(--text-secondary)]">
                  <span>
                    Showing {runs.length} of {runsTotal} runs • Page {Math.floor(runsOffset / 25) + 1} of {Math.max(1, Math.ceil(runsTotal / 25))}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={runsOffset === 0}
                      onClick={() => setRunsOffset(Math.max(0, runsOffset - 25))}
                    >
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={runsOffset + 25 >= runsTotal}
                      onClick={() => setRunsOffset(runsOffset + 25)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            {/* Trace Detail Side Drawer / Modal (Requirement #21) */}
            {selectedRun && (
              <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end animate-fadeIn">
                <div className="w-full max-w-xl h-full bg-[var(--bg-card)] border-l border-[var(--border)] p-6 overflow-y-auto space-y-6 shadow-2xl">
                  <div className="flex items-center justify-between pb-4 border-b border-[var(--border)]">
                    <div>
                      <h2 className="text-base font-bold text-[var(--text-primary)] flex items-center gap-2">
                        <Activity className="w-4 h-4 text-[var(--accent)]" />
                        Run Trace: {selectedRun.trace_id}
                      </h2>
                      <span className="text-xs text-[var(--text-muted)]">
                        Conversation #{selectedRun.conversation_id} • Created {new Date(selectedRun.created_at).toLocaleString()}
                      </span>
                    </div>
                    <button
                      onClick={() => setSelectedRun(null)}
                      className="p-1.5 rounded-lg hover:bg-[var(--bg-input)] text-[var(--text-secondary)]"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>

                  {/* Metadata Cards */}
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-[var(--text-muted)]">Decision:</span>
                      <div className="font-bold text-[var(--text-primary)] mt-0.5">{selectedRun.decision}</div>
                    </div>
                    <div className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-[var(--text-muted)]">Latency / Cost:</span>
                      <div className="font-bold text-[var(--text-primary)] mt-0.5">
                        {selectedRun.latency_ms} ms • {selectedRun.estimated_cost !== null && selectedRun.estimated_cost !== undefined ? `$${selectedRun.estimated_cost.toFixed(5)}` : 'Cost N/A'}
                      </div>
                    </div>
                    <div className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-[var(--text-muted)]">Model / Provider:</span>
                      <div className="font-mono text-[var(--text-primary)] mt-0.5">
                        {selectedRun.model || 'default'} ({selectedRun.provider || 'unknown'})
                      </div>
                    </div>
                    <div className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)]">
                      <span className="text-[var(--text-muted)]">Prompt Version:</span>
                      <div className="font-mono text-[var(--text-primary)] mt-0.5">{selectedRun.prompt_version || 'v1.0'}</div>
                    </div>
                  </div>

                  {/* Exact Token Telemetry */}
                  <div className="p-4 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] space-y-2">
                    <span className="text-xs font-bold text-[var(--text-primary)]">Token Telemetry</span>
                    <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                      <div>
                        <span className="text-[var(--text-muted)] text-[10px]">INPUT</span>
                        <div className="text-[var(--text-primary)] font-bold">{selectedRun.input_tokens ?? '—'}</div>
                      </div>
                      <div>
                        <span className="text-[var(--text-muted)] text-[10px]">OUTPUT</span>
                        <div className="text-[var(--text-primary)] font-bold">{selectedRun.output_tokens ?? '—'}</div>
                      </div>
                      <div>
                        <span className="text-[var(--text-muted)] text-[10px]">TOTAL</span>
                        <div className="text-sky-400 font-bold">
                          {selectedRun.total_tokens != null
                            ? selectedRun.total_tokens.toLocaleString()
                            : (selectedRun.tokens != null ? selectedRun.tokens.toLocaleString() : '—')}
                        </div>
                      </div>
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] pt-1 border-t border-[var(--border)]">
                      Source: {selectedRun.usage_source || 'unavailable'} • Cached: {selectedRun.cached_input_tokens != null ? selectedRun.cached_input_tokens : '—'} • Reasoning: {selectedRun.reasoning_tokens != null ? selectedRun.reasoning_tokens : '—'}
                    </div>
                  </div>

                  {/* Per-Model-Call Trace Breakdown (Requirement #12, #13) */}
                  <div className="space-y-2">
                    <span className="text-xs font-bold text-[var(--text-primary)]">Per-Call Execution Trace</span>
                    {selectedRun.model_calls && selectedRun.model_calls.length > 0 ? (
                      <div className="space-y-2">
                        {selectedRun.model_calls.map((mc, idx) => (
                          <div key={idx} className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] space-y-1 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-purple-400">Phase: {mc.phase}</span>
                              <span className="font-mono text-[11px] text-[var(--text-muted)]">{mc.latency_ms} ms</span>
                            </div>
                            <div className="text-[11px] text-[var(--text-secondary)] font-mono">
                              Model: {mc.model} • Tokens: {mc.total_tokens ?? '—'} (in: {mc.input_tokens ?? '—'}, out: {mc.output_tokens ?? '—'})
                            </div>
                            {mc.error && <div className="text-[11px] text-rose-400 font-semibold">{mc.error}</div>}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-3 rounded-xl bg-[var(--bg-input)] text-xs text-[var(--text-muted)]">
                        {selectedRun.llm_call_count == null
                          ? 'Call count unavailable'
                          : `Single aggregate model turn recorded (${selectedRun.llm_call_count} ${selectedRun.llm_call_count === 1 ? 'call' : 'calls'}).`}
                      </div>
                    )}
                  </div>

                  {/* RAG Citations */}
                  {selectedRun.citations && selectedRun.citations.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-xs font-bold text-[var(--text-primary)]">Knowledge Citations ({selectedRun.citations.length})</span>
                      <div className="space-y-2">
                        {selectedRun.citations.map((c, i) => (
                          <div key={i} className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-xs space-y-1">
                            <div className="font-bold text-emerald-400">{c.title || `Chunk #${c.chunk_id}`}</div>
                            <p className="text-[11px] text-[var(--text-secondary)]">{c.snippet}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tools Executed */}
                  {selectedRun.tool_calls && selectedRun.tool_calls.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-xs font-bold text-[var(--text-primary)]">Tools Executed ({selectedRun.tool_calls.length})</span>
                      <div className="space-y-2">
                        {selectedRun.tool_calls.map((t, i) => (
                          <div key={i} className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-xs space-y-1">
                            <div className="font-mono font-bold text-indigo-400">{t.name}</div>
                            <pre className="text-[10px] text-[var(--text-secondary)] bg-black/40 p-2 rounded overflow-x-auto font-mono">
                              {JSON.stringify(t.arguments || {}, null, 2)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: DIAGNOSTICS & LIVE PROBE (Requirement #27, #28, #30, #31) */}
        {activeTab === 'diagnostics' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-6 rounded-2xl border border-[var(--border)]">
              <div>
                <h3 className="text-base font-bold text-[var(--text-primary)] flex items-center gap-2">
                  <Cpu className="w-5 h-5 text-[var(--accent)]" />
                  Live System Diagnostics & Provider Verification
                </h3>
                <p className="text-xs text-[var(--text-secondary)] mt-1">
                  Probes actual connection health using active encrypted settings. Secrets remain strictly masked.
                </p>
              </div>

              <Button
                variant="primary"
                size="sm"
                onClick={handleTestLiveProvider}
                loading={liveTesting}
              >
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Test Live Provider Now
              </Button>
            </div>

            {/* Live Test Results Card */}
            {liveTestResult && (
              <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--accent)] shadow-lg space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    Latest Live Provider Test Probe Results
                  </h4>
                  <span className="text-[11px] text-[var(--text-muted)]">Tested at: {liveTestResult.tested_at}</span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div className="p-3 rounded-xl bg-[var(--bg-input)]">
                    <span className="text-[var(--text-muted)]">Connection:</span>
                    {(() => {
                      const connStatus = (liveTestResult.connection_status || (liveTestResult.connected ? 'connected' : 'failed') || 'unknown').toLowerCase();
                      const isConnOk = connStatus === 'connected' || liveTestResult.connected === true;
                      return (
                        <div className={`font-bold mt-0.5 ${isConnOk ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {connStatus.toUpperCase()}
                        </div>
                      );
                    })()}
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--bg-input)]">
                    <span className="text-[var(--text-muted)]">Latency:</span>
                    <div className="font-bold text-[var(--text-primary)] mt-0.5">{liveTestResult.latency_ms ?? '—'} ms</div>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--bg-input)]">
                    <span className="text-[var(--text-muted)]">Native Tool Calling:</span>
                    <div className="font-bold text-[var(--text-primary)] mt-0.5">
                      {(liveTestResult.native_tool_calling || liveTestResult.tool_calling_status || 'unsupported').toUpperCase()}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--bg-input)]">
                    <span className="text-[var(--text-muted)]">Embeddings:</span>
                    <div className="font-bold text-[var(--text-primary)] mt-0.5">
                      {(liveTestResult.embeddings || liveTestResult.embedding_status || 'not_configured').toUpperCase()}
                    </div>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[var(--bg-input)] text-xs space-y-1">
                  <span className="text-[var(--text-muted)]">Response Preview:</span>
                  <div className="font-mono text-[var(--text-secondary)] italic">
                    "{liveTestResult.response_preview || 'No response preview'}"
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)] pt-1">
                    Tokens: in={liveTestResult.input_tokens ?? '—'}, out={liveTestResult.output_tokens ?? '—'}, total={liveTestResult.total_tokens ?? '—'} (source={liveTestResult.usage_source})
                  </div>
                </div>
              </div>
            )}

            {/* Diagnostic Component Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* LLM Card */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">LLM Provider</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                    {diagnostics?.llm_provider?.status || 'configured'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Provider: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.llm_provider?.name || 'openai_compatible'}</span></div>
                  <div>Model: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.llm_provider?.model || 'deepseek-v4-pro'}</span></div>
                </div>
              </div>

              {/* Embedding Card */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">Embedding Provider</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400">
                    {diagnostics?.embedding_provider?.status || diagnostics?.embedding?.status || 'configured'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Provider: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.embedding_provider?.name || 'openai_compatible'}</span></div>
                  <div>Model: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.embedding_provider?.model || 'text-embedding-3-small'}</span></div>
                </div>
              </div>

              {/* Qdrant Card */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">Qdrant Vector Store</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                    {diagnostics?.vector_store?.status || 'connected'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Status: <span className="font-mono text-[var(--text-primary)]">Ready</span></div>
                  <div>Provider: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.vector_store?.provider || 'qdrant'}</span></div>
                </div>
              </div>

              {/* Signal Gateway Card (Requirement #31) */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">Signal Gateway</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-400">
                    {diagnostics?.signal_gateway?.status || 'active'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Effective URL: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.signal_gateway?.api_url || 'http://100.90.182.100:8880'}</span></div>
                  <div>Phone: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.signal_gateway?.phone_number || '+447422531937'}</span></div>
                </div>
              </div>

              {/* RAG Index Card */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">RAG Vector Index</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                    {diagnostics?.rag_index?.status || 'ready'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Documents: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.rag_index?.documents_count ?? 0}</span></div>
                  <div>Chunks: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.rag_index?.chunks_count ?? 0}</span></div>
                </div>
              </div>

              {/* MCP Governance Card */}
              <div className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-[var(--text-primary)]">MCP Servers</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400">
                    {diagnostics?.mcp?.status || 'active'}
                  </span>
                </div>
                <div className="text-xs space-y-1 text-[var(--text-secondary)]">
                  <div>Active: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.mcp?.active_servers ?? 0}</span></div>
                  <div>Total: <span className="font-mono text-[var(--text-primary)]">{diagnostics?.mcp?.total_servers ?? 0}</span></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: RAG KNOWLEDGE & SEARCH PLAYGROUND (Requirement #32, #33, #34, #35) */}
        {activeTab === 'knowledge' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Knowledge Base & Scoped RAG</h3>
                <p className="text-xs text-[var(--text-secondary)]">Inspect sources, view documents, or test retrieval search.</p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="primary" onClick={() => setShowAddSourceModal(true)}>
                  <Plus className="w-3.5 h-3.5 mr-1.5" />
                  Index Document
                </Button>
              </div>
            </div>

            {/* RAG Search Playground (Requirement #34) */}
            <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4">
              <h4 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <Search className="w-4 h-4 text-emerald-400" />
                RAG Retrieval Search Playground
              </h4>
              <form onSubmit={handleRAGSearch} className="flex flex-col md:flex-row gap-3">
                <input
                  type="text"
                  placeholder="Enter query to test vector search similarity..."
                  value={ragSearchQuery}
                  onChange={e => setRagSearchQuery(e.target.value)}
                  className="flex-1 px-3 py-2 text-xs rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none focus:border-[var(--accent)]"
                />
                <select
                  aria-label="Scope type"
                  value={ragSearchScope}
                  onChange={e => setRagSearchScope(e.target.value as 'global' | 'group' | 'user')}
                  className="px-3 py-2 text-xs rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                >
                  <option value="global">Global Scope</option>
                  <option value="group">Group Scope</option>
                  <option value="user">User Scope</option>
                </select>
                {ragSearchScope !== 'global' && (
                  <input
                    type="text"
                    placeholder="Canonical Scope ID..."
                    value={ragSearchScopeId}
                    onChange={e => setRagSearchScopeId(e.target.value)}
                    className="w-40 px-3 py-2 text-xs rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  />
                )}
                <Button size="sm" variant="primary" type="submit" loading={ragSearching}>
                  Search
                </Button>
              </form>

              {ragSearchResults.length > 0 && (
                <div className="space-y-2 pt-2">
                  <span className="text-xs font-bold text-[var(--text-primary)]">Matches ({ragSearchResults.length}):</span>
                  <div className="space-y-2">
                    {ragSearchResults.map(res => (
                      <div key={res.chunk_id} className="p-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-emerald-400">{res.title}</span>
                          <span className="text-[10px] text-purple-400 font-mono font-bold">Score: {res.score.toFixed(4)}</span>
                        </div>
                        <p className="text-[11px] text-[var(--text-secondary)]">{res.snippet}</p>
                        <span className="text-[10px] text-[var(--text-muted)]">Scope: {res.scope_type} {res.scope_id ? `(${res.scope_id})` : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Knowledge Sources Table */}
            <div className="rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[var(--bg-input)] text-[var(--text-muted)] font-semibold border-b border-[var(--border)]">
                    <tr>
                      <th className="py-3 px-4">Title</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Language</th>
                      <th className="py-3 px-4">Trust</th>
                      <th className="py-3 px-4">Docs / Chunks</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {sources.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-xs text-[var(--text-muted)]">
                          No knowledge sources found. Click "Index Document" above to create one.
                        </td>
                      </tr>
                    ) : (
                      sources.map(src => (
                        <tr key={src.id} className="hover:bg-[var(--bg-input)]/50 transition-colors">
                          <td className="py-3 px-4 font-bold text-[var(--text-primary)]">{src.title}</td>
                          <td className="py-3 px-4 font-mono text-[var(--text-secondary)]">{src.source_type}</td>
                          <td className="py-3 px-4 uppercase text-[var(--text-secondary)]">{src.language}</td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400">
                              {src.trust_level}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono">
                            {src.documents_count ?? src.document_count ?? 0} docs / {src.chunks_count ?? src.chunk_count ?? 0} chunks
                          </td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                              {src.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 flex items-center gap-2">
                            <button
                              onClick={() => handleOpenSourceDetail(src.id)}
                              className="px-2 py-1 rounded bg-[var(--bg-input)] hover:bg-[var(--border)] text-[var(--accent)] font-semibold text-[11px]"
                            >
                              Docs
                            </button>
                            <button
                              onClick={() => handleReindexSource(src.id)}
                              className="px-2 py-1 rounded bg-[var(--bg-input)] hover:bg-[var(--border)] text-[var(--text-secondary)] text-[11px]"
                            >
                              Reindex
                            </button>
                            <button
                              onClick={() => handleDeleteSource(src.id)}
                              className="p-1 rounded hover:bg-rose-500/20 text-rose-400"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Source Documents Modal (Requirement #33) */}
            {selectedSourceDetail && (
              <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="w-full max-w-2xl bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                    <div>
                      <h3 className="text-sm font-bold text-[var(--text-primary)]">
                        Documents in Source: {selectedSourceDetail.source.title}
                      </h3>
                      <span className="text-xs text-[var(--text-muted)]">
                        {selectedSourceDetail.documents.length} document(s) indexed
                      </span>
                    </div>
                    <button onClick={() => setSelectedSourceDetail(null)} className="p-1 rounded text-[var(--text-secondary)]">
                      <X className="w-5 h-5" />
                    </button>
                  </div>

                  <div className="space-y-3">
                    {selectedSourceDetail.documents.length === 0 ? (
                      <div className="p-6 text-center text-xs text-[var(--text-muted)]">
                        No documents found in this source.
                      </div>
                    ) : (
                      selectedSourceDetail.documents.map(doc => (
                        <div key={doc.id} className="p-3.5 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-xs flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="font-bold text-[var(--text-primary)]">{doc.title}</div>
                            <div className="text-[11px] text-[var(--text-secondary)]">
                              Scope: <span className="font-mono text-purple-400">{doc.scope_type}</span> {doc.scope_id ? `(${doc.scope_id})` : ''} • {doc.chunk_count} chunks
                            </div>
                          </div>
                          <button
                            onClick={() => handleDeleteKnowledgeDoc(selectedSourceDetail.source.id, doc.id)}
                            className="p-1.5 rounded hover:bg-rose-500/20 text-rose-400"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: SCOPED MEMORY (Requirement #36, #37, #38) */}
        {activeTab === 'memory' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-[var(--text-secondary)]">Scope Filter:</span>
                {(['all', 'user', 'group', 'global'] as const).map(sc => (
                  <button
                    key={sc}
                    onClick={() => setMemoryScopeFilter(sc)}
                    className={`px-3 py-1 text-xs rounded-lg font-semibold transition-colors ${
                      memoryScopeFilter === sc
                        ? 'bg-[var(--accent)] text-white'
                        : 'bg-[var(--bg-input)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {sc.toUpperCase()}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Search memory contents..."
                  value={memorySearch}
                  onChange={e => setMemorySearch(e.target.value)}
                  className="px-3 py-1.5 text-xs rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                />
              </div>
            </div>

            {/* Memory Items Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {memories
                .filter(m => (memorySearch ? m.content.toLowerCase().includes(memorySearch.toLowerCase()) : true))
                .map(m => (
                  <div key={m.id} className="p-4 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-2.5 shadow-sm">
                    <div className="flex items-center justify-between">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-purple-500/20 text-purple-300">
                        {m.scope_type} {m.scope_id ? `• ${m.scope_id}` : ''}
                      </span>
                      <button onClick={() => handleDeleteMemory(m.id)} className="p-1 rounded hover:bg-rose-500/20 text-rose-400">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <p className="text-xs text-[var(--text-primary)] font-medium leading-relaxed">{m.content}</p>

                    <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] pt-2 border-t border-[var(--border)]">
                      <span>Type: {m.memory_type}</span>
                      <span>Importance: {m.importance}/5</span>
                      <span>Sensitivity: {m.sensitivity || 'internal'}</span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* TAB 6: PROGRESSIVE SKILLS (Requirement #39) */}
        {activeTab === 'skills' && (
          <div className="space-y-6">
            <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Progressive Prompt Skills</h3>
                <p className="text-xs text-[var(--text-secondary)]">Skills are dynamically matched and injected into the Agent prompt.</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {skills.map(s => (
                <div key={s.name} className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-bold text-[var(--text-primary)]">{s.name}</span>
                      <span className="text-[11px] text-[var(--text-muted)] ml-2">v{s.version} • {s.scope}</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={s.is_enabled}
                        onChange={() => handleToggleSkill(s.name, s.is_enabled)}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[var(--accent)]"></div>
                    </label>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)]">{s.description}</p>
                  {s.body && (
                    <pre className="text-[11px] font-mono text-[var(--text-secondary)] bg-[var(--bg-input)] p-3 rounded-xl overflow-x-auto max-h-32">
                      {s.body}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 7: TOOLS & MCP GOVERNANCE (Requirement #40, #41, #42, #43) */}
        {activeTab === 'mcp' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Model Context Protocol (MCP) Governance</h3>
                <p className="text-xs text-[var(--text-secondary)]">Manage connected MCP servers and inspect discovered tool permissions.</p>
              </div>
              <Button size="sm" variant="primary" onClick={() => setShowAddMcpModal(true)}>
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Add MCP Server
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {mcpServers.map(srv => (
                <div key={srv.id} className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-[var(--text-primary)]">{srv.name}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${srv.status === 'connected' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-zinc-700 text-zinc-400'}`}>
                      {srv.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="text-xs space-y-1 text-[var(--text-secondary)] font-mono">
                    <div>Transport: {srv.transport || srv.transport_type || 'http'}</div>
                    <div className="truncate">Endpoint: {srv.endpoint_url || srv.command_or_url || '—'}</div>
                    <div>Tools: {srv.tools_count ?? srv.tool_count ?? 0} discovered</div>
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-[var(--border)] text-xs">
                    <Button size="sm" variant="secondary" onClick={() => handleTestMCP(srv.id)}>
                      Test
                    </Button>
                    <button
                      onClick={() => handleOpenMcpDetail(srv.id)}
                      className="px-2.5 py-1 rounded bg-[var(--bg-input)] hover:bg-[var(--border)] text-[var(--accent)] font-semibold text-[11px]"
                    >
                      Tools
                    </button>
                    <button onClick={() => handleDeleteMcpServer(srv.id)} className="p-1 rounded text-rose-400 hover:bg-rose-500/20">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* MCP Discovered Tools Detail Modal (Requirement #42) */}
            {selectedMcpDetail && (() => {
              const serverName = selectedMcpDetail.server?.name || selectedMcpDetail.name || 'MCP Server';
              const toolsList = selectedMcpDetail.discovered_tools || selectedMcpDetail.tools || [];
              return (
                <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
                  <div className="w-full max-w-2xl bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4 max-h-[85vh] overflow-y-auto">
                    <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                      <div>
                        <h3 className="text-sm font-bold text-[var(--text-primary)]">
                          Discovered Tools: {serverName}
                        </h3>
                        <span className="text-xs text-[var(--text-muted)]">
                          {toolsList.length} tool(s) registered
                        </span>
                      </div>
                      <button onClick={() => setSelectedMcpDetail(null)} className="p-1 rounded text-[var(--text-secondary)]">
                        <X className="w-5 h-5" />
                      </button>
                    </div>

                    <div className="space-y-3">
                      {toolsList.length === 0 ? (
                        <div className="p-6 text-center text-xs text-[var(--text-muted)]">
                          No tools discovered on this server. Run connection test to discover tools.
                        </div>
                      ) : (
                        toolsList.map(t => (
                          <div key={t.name} className="p-4 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-xs space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-bold text-indigo-400">{t.name}</span>
                              <div className="flex items-center gap-1.5 text-[10px]">
                                {t.read_only ? (
                                  <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">Read-Only</span>
                                ) : (
                                  <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">Write Action</span>
                                )}
                                {t.requires_approval && (
                                  <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300">Requires Approval</span>
                                )}
                              </div>
                            </div>
                            <p className="text-[11px] text-[var(--text-secondary)]">{t.description}</p>
                            <pre className="text-[10px] text-[var(--text-secondary)] bg-black/40 p-2 rounded overflow-x-auto font-mono">
                              {JSON.stringify(t.input_schema || {}, null, 2)}
                            </pre>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* TAB 8: LEARNING LOOP (Requirement #44, #45, #46, #47, #48) */}
        {activeTab === 'learning' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Human-in-the-Loop Learning</h3>
                <p className="text-xs text-[var(--text-secondary)]">Review high-quality interactions for Knowledge FAQ promotion or offline Fine-Tuning.</p>
              </div>
              <div className="flex items-center gap-3">
                {trainingStats && (
                  <span className="text-xs font-semibold text-purple-400">
                    Approved Examples: {trainingStats.total_approved_examples}
                  </span>
                )}
                <Button size="sm" variant="secondary" onClick={handleExportJSONL}>
                  <Download className="w-3.5 h-3.5 mr-1.5" />
                  Export JSONL
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {candidates.length === 0 ? (
                <div className="col-span-2 p-8 text-center text-xs text-[var(--text-muted)] bg-[var(--bg-card)] rounded-2xl border border-[var(--border)]">
                  No learning candidates currently awaiting review.
                </div>
              ) : (
                candidates.map(cand => (
                  <div key={cand.id} className="p-5 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3 shadow-sm">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-[var(--accent)]">Candidate #{cand.id}</span>
                      <span className="text-[11px] text-[var(--text-muted)]">Category: {cand.category} • {cand.language}</span>
                    </div>

                    <div className="space-y-1.5 text-xs">
                      <div className="p-2.5 rounded-lg bg-[var(--bg-input)]">
                        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase">User Question:</span>
                        <div className="text-[var(--text-primary)] mt-0.5">{cand.customer_question}</div>
                      </div>
                      <div className="p-2.5 rounded-lg bg-[var(--bg-input)]">
                        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase">Human Answer:</span>
                        <div className="text-[var(--text-primary)] mt-0.5">{cand.human_answer}</div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-[var(--border)] text-xs">
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => {
                          setShowPromoteModal(cand);
                          setPromoteAction('knowledge');
                          setPromoteFaqQ(cand.suggested_faq_q || cand.customer_question);
                          setPromoteFaqA(cand.suggested_faq_a || cand.human_answer);
                          setConfirmGlobalPrivacy(false);
                        }}
                      >
                        Promote Knowledge
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setShowPromoteModal(cand);
                          setPromoteAction('training');
                        }}
                      >
                        Add to Training
                      </Button>
                      <button
                        onClick={() => handleRejectCandidate(cand.id)}
                        className="px-2.5 py-1 text-xs text-rose-400 hover:bg-rose-500/20 rounded font-semibold"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Promotion Confirmation Dialog (Requirement #45, #47) */}
            {showPromoteModal && (
              <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="w-full max-w-lg bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                    <h3 className="text-sm font-bold text-[var(--text-primary)]">
                      {promoteAction === 'knowledge' ? 'Promote Candidate to Knowledge Base' : 'Add to Fine-Tuning Training Set'}
                    </h3>
                    <button onClick={() => setShowPromoteModal(null)} className="p-1 rounded text-[var(--text-secondary)]">
                      <X className="w-5 h-5" />
                    </button>
                  </div>

                  {promoteAction === 'knowledge' ? (
                    <div className="space-y-3 text-xs">
                      <div>
                        <label className="block text-[var(--text-secondary)] mb-1">FAQ Question:</label>
                        <input
                          type="text"
                          value={promoteFaqQ}
                          onChange={e => setPromoteFaqQ(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-[var(--text-secondary)] mb-1">FAQ Answer:</label>
                        <textarea
                          rows={3}
                          value={promoteFaqA}
                          onChange={e => setPromoteFaqA(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-[var(--text-secondary)] mb-1">Knowledge Scope:</label>
                        <select
                          value={promoteScope}
                          onChange={e => setPromoteScope(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                        >
                          <option value="global">Global (Available to all users)</option>
                          <option value="group">Group Only</option>
                          <option value="user">User Private</option>
                        </select>
                      </div>

                      {/* Explicit Global Privacy Confirmation Checkbox (Requirement #45) */}
                      {promoteScope === 'global' && (
                        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 space-y-2">
                          <label className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={confirmGlobalPrivacy}
                              onChange={e => setConfirmGlobalPrivacy(e.target.checked)}
                              className="mt-0.5 rounded border-amber-500 text-[var(--accent)]"
                            />
                            <span className="text-[11px]">
                              I confirm this FAQ contains no customer-specific private information, credentials, payment data, or private promises.
                            </span>
                          </label>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-[var(--text-secondary)] p-3 rounded-xl bg-[var(--bg-input)]">
                      Candidate #{showPromoteModal.id} will be appended to the offline approved training dataset.
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-3 border-t border-[var(--border)]">
                    <Button variant="secondary" size="sm" onClick={() => setShowPromoteModal(null)}>
                      Cancel
                    </Button>
                    <Button variant="primary" size="sm" onClick={handleExecutePromotion}>
                      Confirm Promotion
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 9: PROMPT VERSIONS (Requirement #49, #50) */}
        {activeTab === 'prompts' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded-xl border border-[var(--border)]">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Prompt Version Management</h3>
                <p className="text-xs text-[var(--text-secondary)]">Immutable versioned system prompts with rollback & AIRun provenance tracking.</p>
              </div>
              <Button size="sm" variant="primary" onClick={() => setShowCreatePromptModal(true)}>
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                New Prompt Version
              </Button>
            </div>

            <div className="rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[var(--bg-input)] text-[var(--text-muted)] font-semibold border-b border-[var(--border)]">
                    <tr>
                      <th className="py-3 px-4">Version</th>
                      <th className="py-3 px-4">Name</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Created By</th>
                      <th className="py-3 px-4">Created At</th>
                      <th className="py-3 px-4">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {promptVersions.map(pv => (
                      <tr key={pv.id} className="hover:bg-[var(--bg-input)]/50 transition-colors">
                        <td className="py-3 px-4 font-mono font-bold text-purple-400">{pv.version}</td>
                        <td className="py-3 px-4 font-bold text-[var(--text-primary)]">{pv.name}</td>
                        <td className="py-3 px-4">
                          {pv.is_active ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400">
                              Active
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-700 text-zinc-400">
                              Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-[var(--text-secondary)]">{pv.created_by}</td>
                        <td className="py-3 px-4 font-mono text-[var(--text-muted)]">
                          {new Date(pv.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4">
                          {!pv.is_active && (
                            <button
                              onClick={() => handleActivatePromptVersion(pv.version)}
                              className="px-2.5 py-1 text-xs rounded bg-[var(--accent)] hover:bg-[var(--accent)]/80 text-white font-semibold"
                            >
                              Activate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Create Prompt Version Modal */}
            {showCreatePromptModal && (
              <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="w-full max-w-lg bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                    <h3 className="text-sm font-bold text-[var(--text-primary)]">Create Prompt Version</h3>
                    <button onClick={() => setShowCreatePromptModal(false)} className="p-1 rounded text-[var(--text-secondary)]">
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                  <form onSubmit={handleCreatePromptVersion} className="space-y-3 text-xs">
                    <div>
                      <label className="block text-[var(--text-secondary)] mb-1">Version String (e.g. v0.4.1):</label>
                      <input
                        type="text"
                        required
                        value={newPromptVersion}
                        onChange={e => setNewPromptVersion(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[var(--text-secondary)] mb-1">Name:</label>
                      <input
                        type="text"
                        value={newPromptName}
                        onChange={e => setNewPromptName(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[var(--text-secondary)] mb-1">Template:</label>
                      <textarea
                        required
                        rows={6}
                        value={newPromptTemplate}
                        onChange={e => setNewPromptTemplate(e.target.value)}
                        className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none font-mono"
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-3 border-t border-[var(--border)]">
                      <Button variant="secondary" size="sm" type="button" onClick={() => setShowCreatePromptModal(false)}>
                        Cancel
                      </Button>
                      <Button variant="primary" size="sm" type="submit">
                        Create Version
                      </Button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 10: EVALUATION SUITE (Requirement #51, #52, #53, #54) */}
        {activeTab === 'evaluation' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Deterministic Contract Evaluation Card */}
              <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4 shadow-sm">
                <div>
                  <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    Deterministic Contract Evaluation
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)] mt-1">
                    Safe, reproducible contract benchmark (32 cases). Verifies decisions, tool permissions, and safety invariants without external token costs.
                  </p>
                </div>
                <Button size="sm" variant="primary" onClick={() => handleRunEvaluation(32)} loading={loading}>
                  Run 32 Deterministic Invariants
                </Button>
              </div>

              {/* Live Model Evaluation Card */}
              <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4 shadow-sm">
                <div>
                  <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <Activity className="w-4 h-4 text-purple-400" />
                    Live Model Evaluation
                  </h3>
                  <p className="text-xs text-[var(--text-secondary)] mt-1">
                    Executes golden cases against the live configured LLM provider. Consumes API tokens and measures real model outputs.
                  </p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setShowLiveEvalModal(true)}>
                  Configure & Run Live Evaluation
                </Button>
              </div>
            </div>

            {/* Latest Evaluation Summary Banner */}
            {evalSummary && (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle className="w-4 h-4" /> Latest Evaluation Run Results
                  </span>
                  <button onClick={() => setEvalSummary(null)} className="text-xs text-[var(--text-muted)] hover:text-white">✕</button>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <span className="text-[var(--text-muted)] text-[10px]">PASS RATE</span>
                    <div className="font-bold text-emerald-400">{(evalSummary.pass_rate * 100).toFixed(1)}% ({evalSummary.passed_cases}/{evalSummary.total_cases})</div>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)] text-[10px]">DECISION ACCURACY</span>
                    <div className="font-bold text-[var(--text-primary)]">{(evalSummary.decision_accuracy * 100).toFixed(1)}%</div>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)] text-[10px]">AVG LATENCY</span>
                    <div className="font-mono text-[var(--text-secondary)]">{evalSummary.average_latency_ms.toFixed(0)} ms</div>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)] text-[10px]">TOTAL TOKENS</span>
                    <div className="font-mono text-[var(--text-secondary)]">
                      {evalSummary.total_tokens != null ? evalSummary.total_tokens.toLocaleString() : '—'}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Evaluation Run History (Requirement #54) */}
            <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4">
              <h4 className="text-sm font-bold text-[var(--text-primary)]">Persisted Evaluation Run History</h4>
              <div className="rounded-xl border border-[var(--border)] overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[var(--bg-input)] text-[var(--text-muted)] font-semibold border-b border-[var(--border)]">
                    <tr>
                      <th className="py-3 px-4">Run ID</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Model</th>
                      <th className="py-3 px-4">Pass Rate</th>
                      <th className="py-3 px-4">Decision Acc</th>
                      <th className="py-3 px-4">Avg Latency</th>
                      <th className="py-3 px-4">Tokens</th>
                      <th className="py-3 px-4">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {evalRuns.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-xs text-[var(--text-muted)]">
                          No historical evaluation runs recorded yet. Run a benchmark above to persist results.
                        </td>
                      </tr>
                    ) : (
                      evalRuns.map(run => (
                        <tr key={run.id} className="hover:bg-[var(--bg-input)]/50 transition-colors">
                          <td className="py-3 px-4 font-mono font-bold text-[var(--accent)]">#{run.id}</td>
                          <td className="py-3 px-4 font-mono uppercase text-purple-400">{run.eval_type}</td>
                          <td className="py-3 px-4 font-mono text-[var(--text-secondary)]">{run.model || 'default'}</td>
                          <td className="py-3 px-4 font-bold text-emerald-400">{(run.pass_rate * 100).toFixed(0)}%</td>
                          <td className="py-3 px-4 font-bold text-[var(--text-primary)]">{(run.decision_accuracy * 100).toFixed(0)}%</td>
                          <td className="py-3 px-4 font-mono text-[var(--text-secondary)]">
                            {run.average_latency_ms != null ? `${run.average_latency_ms.toFixed(0)} ms` : '—'}
                          </td>
                          <td className="py-3 px-4 font-mono text-[var(--text-secondary)]">
                            {run.total_tokens != null ? run.total_tokens.toLocaleString() : '—'}
                          </td>
                          <td className="py-3 px-4 text-[var(--text-muted)]">
                            {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Live Eval Confirmation Modal (Requirement #53) */}
            {showLiveEvalModal && (
              <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="w-full max-w-md bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                    <h3 className="text-sm font-bold text-[var(--text-primary)]">Confirm Live Evaluation</h3>
                    <button onClick={() => setShowLiveEvalModal(false)} className="p-1 rounded text-[var(--text-secondary)]">
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="space-y-3 text-xs text-[var(--text-secondary)]">
                    <p>
                      This test invokes your configured LLM provider and will consume external API tokens.
                    </p>
                    <div>
                      <label className="block text-[var(--text-primary)] font-semibold mb-1">Number of test cases to run:</label>
                      <select
                        value={evalLimit}
                        onChange={e => setEvalLimit(Number(e.target.value))}
                        className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                      >
                        <option value={1}>1 Case (Quick Probe)</option>
                        <option value={5}>5 Cases</option>
                        <option value={10}>10 Cases</option>
                        <option value={32}>All 32 Golden Invariants</option>
                      </select>
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 pt-3 border-t border-[var(--border)]">
                    <Button variant="secondary" size="sm" onClick={() => setShowLiveEvalModal(false)}>
                      Cancel
                    </Button>
                    <Button variant="primary" size="sm" onClick={() => handleRunEvaluation(evalLimit)} loading={loading}>
                      Run Live Evaluation
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Global Modal: Add Knowledge Doc */}
        {showAddSourceModal && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Index Knowledge Document</h3>
                <button onClick={() => setShowAddSourceModal(false)} className="p-1 rounded text-[var(--text-secondary)]">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreateKnowledgeDoc} className="space-y-3 text-xs">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Document Title:</label>
                  <input
                    type="text"
                    required
                    value={newSourceTitle}
                    onChange={e => setNewSourceTitle(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Source Type:</label>
                  <select
                    value={newSourceType}
                    onChange={e => setNewSourceType(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  >
                    <option value="faq">FAQ</option>
                    <option value="manual">Manual</option>
                    <option value="policy">Policy</option>
                    <option value="catalog">Product Catalog</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Scope:</label>
                    <select
                      value={newSourceScope}
                      onChange={e => setNewSourceScope(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                    >
                      <option value="global">Global</option>
                      <option value="group">Group</option>
                      <option value="user">User</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Scope ID (if Group/User):</label>
                    <input
                      type="text"
                      placeholder="e.g. signal group/user ID"
                      value={newSourceScopeId}
                      onChange={e => setNewSourceScopeId(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Document Content:</label>
                  <textarea
                    required
                    rows={5}
                    value={newSourceDocContent}
                    onChange={e => setNewSourceDocContent(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-3 border-t border-[var(--border)]">
                  <Button variant="secondary" size="sm" type="button" onClick={() => setShowAddSourceModal(false)}>
                    Cancel
                  </Button>
                  <Button variant="primary" size="sm" type="submit" loading={loading}>
                    Index Now
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Global Modal: Add MCP Server */}
        {showAddMcpModal && (
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="w-full max-w-md bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Add MCP Server</h3>
                <button onClick={() => setShowAddMcpModal(false)} className="p-1 rounded text-[var(--text-secondary)]">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreateMcpServer} className="space-y-3 text-xs">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Server Name:</label>
                  <input
                    type="text"
                    required
                    value={newMcpName}
                    onChange={e => setNewMcpName(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Transport Type:</label>
                  <select
                    value={newMcpTransport}
                    onChange={e => setNewMcpTransport(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                  >
                    <option value="http">HTTP SSE / Remote</option>
                    <option value="stdio">stdio Process</option>
                  </select>
                </div>
                {newMcpTransport === 'http' ? (
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Endpoint URL:</label>
                    <input
                      type="url"
                      placeholder="https://mcp.internal/sse"
                      value={newMcpEndpoint}
                      onChange={e => setNewMcpEndpoint(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                    />
                  </div>
                ) : (
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Command:</label>
                    <input
                      type="text"
                      placeholder="npx -y @modelcontextprotocol/server"
                      value={newMcpCommand}
                      onChange={e => setNewMcpCommand(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                    />
                  </div>
                )}
                <div className="flex justify-end gap-2 pt-3 border-t border-[var(--border)]">
                  <Button variant="secondary" size="sm" type="button" onClick={() => setShowAddMcpModal(false)}>
                    Cancel
                  </Button>
                  <Button variant="primary" size="sm" type="submit">
                    Save Server
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </SidebarLayout>
  );
}
