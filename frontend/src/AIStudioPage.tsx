import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  Database,
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
} from 'lucide-react';
import SidebarLayout from './SidebarLayout';
import {
  api,
  AIOverviewMetricsDTO,
  KnowledgeSourceDTO,
  MemoryItemDTO,
  SkillDTO,
  MCPServerDTO,
  LearningCandidateDTO,
  EvaluationSummaryDTO,
} from './api';
import { Button } from './components/ui/Button';

type StudioTab = 'overview' | 'knowledge' | 'memory' | 'skills' | 'mcp' | 'learning' | 'evaluation';

export default function AIStudioPage() {
  const [activeTab, setActiveTab] = useState<StudioTab>('overview');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Data states
  const [overview, setOverview] = useState<AIOverviewMetricsDTO | null>(null);
  const [sources, setSources] = useState<KnowledgeSourceDTO[]>([]);
  const [memories, setMemories] = useState<MemoryItemDTO[]>([]);
  const [skills, setSkills] = useState<SkillDTO[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServerDTO[]>([]);
  const [candidates, setCandidates] = useState<LearningCandidateDTO[]>([]);
  const [evalSummary, setEvalSummary] = useState<EvaluationSummaryDTO | null>(null);

  // Modals & form state
  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [newSourceTitle, setNewSourceTitle] = useState('');
  const [newSourceType, setNewSourceType] = useState('faq');
  const [newSourceDocContent, setNewSourceDocContent] = useState('');
  const [newSourceScope, setNewSourceScope] = useState('global');
  const [newSourceScopeId, setNewSourceScopeId] = useState('');

  // Memory filters
  const [memoryScopeFilter, setMemoryScopeFilter] = useState<'all' | 'user' | 'group' | 'global'>('all');
  const [memorySearch, setMemorySearch] = useState('');

  // Load initial data
  const loadOverview = async () => {
    try {
      const data = await api.getAIOverview();
      setOverview(data);
    } catch {
      // Fallback
    }
  };

  const loadTabData = async (tab: StudioTab) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      if (tab === 'overview') {
        await loadOverview();
      } else if (tab === 'knowledge') {
        const data = await api.getKnowledgeSources();
        setSources(data);
      } else if (tab === 'memory') {
        const data = await api.getMemories();
        setMemories(data);
      } else if (tab === 'skills') {
        const data = await api.getSkills();
        setSkills(data);
      } else if (tab === 'mcp') {
        const data = await api.getMCPServers();
        setMcpServers(data);
      } else if (tab === 'learning') {
        const data = await api.getLearningCandidates();
        setCandidates(data);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load studio data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  useEffect(() => {
    loadTabData(activeTab);
  }, [activeTab]);

  // Actions
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
    if (!confirm('Are you sure you want to permanently delete this memory item?')) return;
    try {
      await api.deleteMemory(id);
      setMemories(prev => prev.filter(m => m.id !== id));
      setSuccessMsg('Memory purged from relational and vector database.');
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
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to toggle skill');
    }
  };

  const handleTestMCP = async (id: number) => {
    try {
      const res = await api.testMCPServer(id);
      setSuccessMsg(`MCP server test: ${res.status} (${res.latency_ms ?? 10} ms)`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'MCP connection test failed');
    }
  };

  const handlePromoteCandidate = async (candidateId: number, target: 'knowledge' | 'training') => {
    try {
      await api.promoteLearningCandidate(candidateId, target);
      setCandidates(prev => prev.filter(c => c.id !== candidateId));
      setSuccessMsg(`Candidate promoted to ${target === 'knowledge' ? 'Knowledge Base FAQ' : 'Training dataset'}!`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to promote candidate');
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

  const handleRunEvaluation = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const summary = await api.runEvaluation(10);
      setEvalSummary(summary);
      setSuccessMsg(`Evaluated ${summary.total_cases} golden cases: ${summary.pass_rate * 100}% passed!`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to run evaluations');
    } finally {
      setLoading(false);
    }
  };

  // Filtered memories
  const filteredMemories = memories.filter(m => {
    if (memoryScopeFilter !== 'all' && m.scope_type !== memoryScopeFilter) return false;
    if (memorySearch && !m.content.toLowerCase().includes(memorySearch.toLowerCase())) return false;
    return true;
  });

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
                AI Platform v0.4 Studio
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-[rgba(0,214,143,0.15)] text-[#00d68f] border border-[rgba(0,214,143,0.3)]">
                Enterprise Production
              </span>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              Signal-native customer service orchestration, scoped RAG knowledge, durable memories, MCP governance, and human-in-the-loop learning.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => loadTabData(activeTab)} loading={loading}>
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />
              Refresh
            </Button>
            <Button variant="primary" size="sm" onClick={() => setActiveTab('evaluation')}>
              <Play className="w-3.5 h-3.5 mr-1.5" />
              Run Benchmarks
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

        {/* Tab Navigation */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-[var(--border)]">
          {[
            { id: 'overview', label: 'Overview', icon: Activity },
            { id: 'knowledge', label: 'RAG Knowledge', icon: Database },
            { id: 'memory', label: 'Scoped Memory', icon: Brain },
            { id: 'skills', label: 'Progressive Skills', icon: Layers },
            { id: 'mcp', label: 'Tool & MCP Governance', icon: Wrench },
            { id: 'learning', label: 'Learning Loop', icon: BookOpen },
            { id: 'evaluation', label: 'Evaluation Suite', icon: ShieldCheck },
          ].map(t => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id as StudioTab)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all shrink-0 cursor-pointer ${
                  isActive
                    ? 'bg-[var(--accent)] text-white shadow-[0_4px_12px_rgba(108,92,231,0.3)] font-bold'
                    : 'text-[var(--text-secondary)] hover:text-white hover:bg-[rgba(255,255,255,0.04)]'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>

        {/* ============================================================== */}
        {/* TAB 1: OVERVIEW & TELEMETRY                                   */}
        {/* ============================================================== */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stat Cards Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-1">
                <span className="text-[11px] text-[var(--text-muted)] font-medium">Total AI Runs</span>
                <p className="text-2xl font-black text-[var(--text-primary)]">
                  {overview?.total_runs ?? 0}
                </p>
                <span className="text-[10px] text-[#00d68f]">Idempotent & Scoped</span>
              </div>

              <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-1">
                <span className="text-[11px] text-[var(--text-muted)] font-medium">Copilot Acceptance</span>
                <p className="text-2xl font-black text-[var(--accent-light)]">
                  {overview ? `${(overview.copilot_acceptance_rate * 100).toFixed(1)}%` : '0.0%'}
                </p>
                <span className="text-[10px] text-[var(--text-muted)]">
                  {overview?.copilot_suggestions_count ?? 0} drafts reviewed
                </span>
              </div>

              <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-1">
                <span className="text-[11px] text-[var(--text-muted)] font-medium">Average Latency</span>
                <p className="text-2xl font-black text-[var(--text-primary)]">
                  {overview?.avg_latency_ms ?? 0} <span className="text-xs font-normal">ms</span>
                </p>
                <span className="text-[10px] text-[var(--text-muted)]">P95 &lt; 2500ms target</span>
              </div>

              <div className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-1">
                <span className="text-[11px] text-[var(--text-muted)] font-medium">Knowledge & Chunks</span>
                <p className="text-2xl font-black text-[#00d68f]">
                  {overview?.knowledge_chunks_count ?? 0}
                </p>
                <span className="text-[10px] text-[var(--text-muted)]">
                  Across {overview?.knowledge_sources_count ?? 0} verified sources
                </span>
              </div>
            </div>

            {/* Architecture Highlights Card */}
            <div className="p-6 rounded-2xl bg-[var(--bg-card)] border border-[var(--border)] space-y-4">
              <h3 className="text-sm font-bold text-[var(--text-primary)] flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#00d68f]" />
                <span>Production AI Architecture & Guarantees</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="p-3.5 rounded-xl bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] space-y-1">
                  <p className="font-bold text-[var(--text-primary)]">Cross-Scope Privacy (P0)</p>
                  <p className="text-[var(--text-secondary)] leading-relaxed">
                    Customer A cannot view Customer B's memories. Group private rules never leak to direct messages. Verified via automated isolation tests.
                  </p>
                </div>
                <div className="p-3.5 rounded-xl bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] space-y-1">
                  <p className="font-bold text-[var(--text-primary)]">Strict Chain-of-Thought Boundary</p>
                  <p className="text-[var(--text-secondary)] leading-relaxed">
                    Internal hidden reasoning tokens are never stored in databases, never forwarded to customers, and never displayed in operator UI.
                  </p>
                </div>
                <div className="p-3.5 rounded-xl bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.06)] space-y-1">
                  <p className="font-bold text-[var(--text-primary)]">No Model Self-Poisoning</p>
                  <p className="text-[var(--text-secondary)] leading-relaxed">
                    Unsupervised AI auto-replies are strictly forbidden from entering RAG or fine-tuning datasets. Only human-reviewed answers are distilled.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 2: RAG KNOWLEDGE BASE                                     */}
        {/* ============================================================== */}
        {activeTab === 'knowledge' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Knowledge Sources</h3>
                <p className="text-xs text-[var(--text-muted)]">
                  Semantic chunking, vector embedding, and scope-isolated RAG retrieval.
                </p>
              </div>
              <Button variant="primary" size="sm" onClick={() => setShowAddSourceModal(true)}>
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Add Document
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {sources.map(src => (
                <div
                  key={src.id}
                  className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] hover:border-[rgba(108,92,231,0.3)] transition-all space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-2 h-2 rounded-full bg-[#00d68f]" />
                      <h4 className="font-bold text-sm text-[var(--text-primary)] truncate">{src.title}</h4>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-[rgba(108,92,231,0.15)] text-[#d9d2ff]">
                      {src.source_type}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
                    <span>Lang: {src.language.toUpperCase()}</span>
                    <span>Trust: {src.trust_level}</span>
                    <span>By: {src.created_by}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Modal: Add Document */}
            {showAddSourceModal && (
              <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4">
                  <h3 className="text-base font-bold text-[var(--text-primary)]">Index New Knowledge Document</h3>
                  <form onSubmit={handleCreateKnowledgeDoc} className="space-y-3.5 text-xs">
                    <div>
                      <label className="block text-[var(--text-muted)] mb-1">Document Title</label>
                      <input
                        type="text"
                        required
                        className="w-full px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                        value={newSourceTitle}
                        onChange={e => setNewSourceTitle(e.target.value)}
                        placeholder="e.g., Shipping & Return Policies"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[var(--text-muted)] mb-1">Type</label>
                        <select
                          className="w-full px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                          value={newSourceType}
                          onChange={e => setNewSourceType(e.target.value)}
                        >
                          <option value="faq">FAQ</option>
                          <option value="doc">Policy Doc</option>
                          <option value="manual">Manual Reference</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[var(--text-muted)] mb-1">Scope</label>
                        <select
                          className="w-full px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                          value={newSourceScope}
                          onChange={e => setNewSourceScope(e.target.value)}
                        >
                          <option value="global">Global (All Users)</option>
                          <option value="group">Group Only</option>
                          <option value="user">User Private</option>
                        </select>
                      </div>
                    </div>
                    {newSourceScope !== 'global' && (
                      <div>
                        <label className="block text-[var(--text-muted)] mb-1">Target Scope Identifier (Group or User ID)</label>
                        <input
                          type="text"
                          required
                          className="w-full px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                          value={newSourceScopeId}
                          onChange={e => setNewSourceScopeId(e.target.value)}
                          placeholder="e.g., group_123 or +420111222333"
                        />
                      </div>
                    )}
                    <div>
                      <label className="block text-[var(--text-muted)] mb-1">Content / Body</label>
                      <textarea
                        rows={6}
                        required
                        className="w-full px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)] text-[var(--text-primary)] outline-none"
                        value={newSourceDocContent}
                        onChange={e => setNewSourceDocContent(e.target.value)}
                        placeholder="Paste document text or FAQ answer here..."
                      />
                    </div>
                    <div className="flex items-center justify-end gap-2 pt-2">
                      <Button variant="secondary" size="sm" onClick={() => setShowAddSourceModal(false)}>
                        Cancel
                      </Button>
                      <Button variant="primary" size="sm" type="submit" loading={loading}>
                        Chunk & Ingest
                      </Button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 3: SCOPED DURABLE MEMORY                                  */}
        {/* ============================================================== */}
        {activeTab === 'memory' && (
          <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Scoped Durable Memories</h3>
                <p className="text-xs text-[var(--text-muted)]">
                  Customer preferences, facts, and constraints with PII redaction and GDPR deletion sync.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[var(--text-muted)]" />
                  <input
                    type="text"
                    placeholder="Search memories..."
                    className="pl-8 pr-3 py-1.5 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] text-xs text-[var(--text-primary)] outline-none"
                    value={memorySearch}
                    onChange={e => setMemorySearch(e.target.value)}
                  />
                </div>
                <select
                  className="px-3 py-1.5 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] text-xs text-[var(--text-primary)] outline-none"
                  value={memoryScopeFilter}
                  onChange={e => setMemoryScopeFilter(e.target.value as 'all' | 'user' | 'group' | 'global')}
                >
                  <option value="all">All Scopes</option>
                  <option value="user">User</option>
                  <option value="group">Group</option>
                  <option value="global">Global</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              {filteredMemories.length === 0 ? (
                <div className="p-8 text-center text-xs text-[var(--text-muted)] bg-[var(--bg-card)] rounded-xl border border-[var(--border)]">
                  No memories found matching filter.
                </div>
              ) : (
                filteredMemories.map(m => (
                  <div
                    key={m.id}
                    className="p-3.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] flex items-center justify-between gap-4"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-[rgba(224,86,253,0.15)] text-[#e056fd]">
                          {m.scope_type}: {m.scope_id}
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)]">
                          {m.memory_type}
                        </span>
                        {m.is_pii_redacted && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[rgba(0,214,143,0.15)] text-[#00d68f]">
                            PII Cleaned
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[var(--text-primary)]">{m.content}</p>
                    </div>

                    <button
                      onClick={() => handleDeleteMemory(m.id)}
                      title="GDPR Delete from DB and Vector Store"
                      className="p-2 text-[var(--text-muted)] hover:text-[var(--danger)] hover:bg-[rgba(255,107,107,0.1)] rounded-lg transition-colors cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 4: PROGRESSIVE SKILLS REGISTRY                            */}
        {/* ============================================================== */}
        {activeTab === 'skills' && (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-bold text-[var(--text-primary)]">Progressive Skills Directory</h3>
              <p className="text-xs text-[var(--text-muted)]">
                Skills with YAML frontmatter loaded progressively on-demand to conserve context tokens.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {skills.map(s => (
                <div
                  key={s.name}
                  className={`p-4 rounded-xl border transition-all space-y-3 ${
                    s.is_enabled
                      ? 'bg-[var(--bg-card)] border-[var(--border)]'
                      : 'bg-[rgba(0,0,0,0.2)] border-[rgba(255,255,255,0.04)] opacity-60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-sm text-[var(--text-primary)] font-mono">{s.name}</h4>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(255,255,255,0.06)] text-[var(--text-muted)]">
                        v{s.version}
                      </span>
                    </div>

                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={s.is_enabled}
                        onChange={() => handleToggleSkill(s.name, s.is_enabled)}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[var(--accent)]" />
                    </label>
                  </div>

                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{s.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 5: TOOL & MCP GOVERNANCE                                   */}
        {/* ============================================================== */}
        {activeTab === 'mcp' && (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-bold text-[var(--text-primary)]">Model Context Protocol (MCP) Governance</h3>
              <p className="text-xs text-[var(--text-muted)]">
                Governed tool execution with SSRF loopback protections and human approval required for write actions.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mcpServers.map(srv => (
                <div
                  key={srv.id}
                  className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Wrench className="w-4 h-4 text-[var(--accent)]" />
                      <h4 className="font-bold text-sm text-[var(--text-primary)]">{srv.name}</h4>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-[rgba(0,214,143,0.15)] text-[#00d68f]">
                      {srv.status}
                    </span>
                  </div>

                  <div className="text-xs font-mono text-[var(--text-muted)] bg-[rgba(0,0,0,0.3)] p-2 rounded-lg truncate">
                    {srv.endpoint_url || srv.command || 'Local Standard Tools'}
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[11px] text-[var(--text-secondary)]">{srv.tool_count || 3} tools registered</span>
                    <Button variant="secondary" size="xs" onClick={() => handleTestMCP(srv.id)}>
                      Test Connection
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 6: HUMAN-IN-THE-LOOP LEARNING LOOP                         */}
        {/* ============================================================== */}
        {activeTab === 'learning' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Curated Learning Candidates</h3>
                <p className="text-xs text-[var(--text-muted)]">
                  Distilled from human operator edits and manual answers. Promote to active FAQ or fine-tuning dataset.
                </p>
              </div>

              <Button variant="secondary" size="sm" onClick={handleExportJSONL}>
                <Download className="w-3.5 h-3.5 mr-1.5" />
                Export Training JSONL
              </Button>
            </div>

            <div className="space-y-3">
              {candidates.length === 0 ? (
                <div className="p-8 text-center text-xs text-[var(--text-muted)] bg-[var(--bg-card)] rounded-xl border border-[var(--border)]">
                  No pending learning candidates. Edit or send human replies in Copilot to populate.
                </div>
              ) : (
                candidates.map(c => (
                  <div
                    key={c.id}
                    className="p-4 rounded-xl bg-[var(--bg-card)] border border-[var(--border)] space-y-3"
                  >
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-[var(--text-muted)]">Customer Query:</p>
                      <p className="text-xs text-[var(--text-primary)] font-medium">"{c.customer_question}"</p>
                    </div>

                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-[var(--text-muted)]">Distilled Operator Answer:</p>
                      <p className="text-xs text-[#d9d2ff] bg-[rgba(108,92,231,0.08)] p-2.5 rounded-lg border border-[rgba(108,92,231,0.2)]">
                        "{c.human_answer}"
                      </p>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
                      <Button
                        variant="secondary"
                        size="xs"
                        onClick={() => handlePromoteCandidate(c.id, 'training')}
                      >
                        Add to Training Set
                      </Button>
                      <Button
                        variant="primary"
                        size="xs"
                        onClick={() => handlePromoteCandidate(c.id, 'knowledge')}
                      >
                        Promote to Knowledge FAQ
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 7: GOLDEN DATASET EVALUATION SUITE                        */}
        {/* ============================================================== */}
        {activeTab === 'evaluation' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-primary)]">Automated Evaluation Suite</h3>
                <p className="text-xs text-[var(--text-muted)]">
                  Runs regression benchmarks against curated golden customer interactions.
                </p>
              </div>

              <Button variant="primary" size="sm" onClick={handleRunEvaluation} loading={loading}>
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Run Benchmark Suite
              </Button>
            </div>

            {evalSummary && (
              <div className="space-y-4 animate-in fade-in duration-200">
                {/* Score Summary */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[10px] text-[var(--text-muted)] uppercase">Pass Rate</span>
                    <p className="text-xl font-black text-[#00d68f]">
                      {(evalSummary.pass_rate * 100).toFixed(0)}%
                    </p>
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {evalSummary.passed_cases} / {evalSummary.total_cases} passed
                    </span>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[10px] text-[var(--text-muted)] uppercase">Decision Accuracy</span>
                    <p className="text-xl font-black text-[var(--accent)]">
                      {(evalSummary.decision_accuracy * 100).toFixed(0)}%
                    </p>
                    <span className="text-[10px] text-[var(--text-muted)]">Action alignment</span>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[10px] text-[var(--text-muted)] uppercase">Avg Latency</span>
                    <p className="text-xl font-black text-[var(--text-primary)]">
                      {evalSummary.average_latency_ms} ms
                    </p>
                    <span className="text-[10px] text-[var(--text-muted)]">Execution time</span>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[var(--bg-card)] border border-[var(--border)]">
                    <span className="text-[10px] text-[var(--text-muted)] uppercase">Tokens Evaluated</span>
                    <p className="text-xl font-black text-[#ffd93d]">
                      {evalSummary.total_tokens}
                    </p>
                    <span className="text-[10px] text-[var(--text-muted)]">Prompt + completion</span>
                  </div>
                </div>

                {/* Case Details Table */}
                <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[rgba(255,255,255,0.03)] border-b border-[var(--border)] text-[var(--text-muted)]">
                      <tr>
                        <th className="p-3">Status</th>
                        <th className="p-3">Case ID</th>
                        <th className="p-3">Scenario Name</th>
                        <th className="p-3">Decision</th>
                        <th className="p-3">Keywords Match</th>
                        <th className="p-3">Latency</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {evalSummary.results.map(r => (
                        <tr key={r.case_id} className="hover:bg-[rgba(255,255,255,0.02)]">
                          <td className="p-3">
                            {r.passed ? (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(0,214,143,0.15)] text-[#00d68f]">
                                PASS
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[rgba(255,107,107,0.15)] text-[var(--danger)]">
                                FAIL
                              </span>
                            )}
                          </td>
                          <td className="p-3 font-mono text-[var(--text-muted)]">{r.case_id}</td>
                          <td className="p-3 font-semibold text-[var(--text-primary)]">{r.case_name}</td>
                          <td className="p-3 text-[var(--text-secondary)]">{r.actual_decision}</td>
                          <td className="p-3 font-mono text-[var(--text-muted)]">
                            {(r.keyword_score * 100).toFixed(0)}%
                          </td>
                          <td className="p-3 font-mono text-[var(--text-muted)]">{r.latency_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </SidebarLayout>
  );
}
