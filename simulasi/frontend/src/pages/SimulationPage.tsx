import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FileText,
  BookOpen,
  Users,
  Eye,
  ShieldCheck,
  Save,
  Download,
  Terminal,
  Clock,
  Cpu,
  Settings,
  ExternalLink,
  AlertTriangle,
  Loader2,
  X,
  Plus,
  Play,
  RefreshCw,
  Gavel,
  CheckCircle2,
  XCircle,
  MinusCircle,
  ChevronDown,
  ChevronUp,
  SendHorizontal,
  Sparkles
} from 'lucide-react';
import { useProject, useProjectFiles, useSimulation, useSettings } from '../hooks/useApi';
import { type HumanTurnState, type LlmConfig, type Scores, JUDGE_PERSONA_OPTIONS } from '../types';

type SimulationSettings = {
  provider: string;
  apiKey: string;
  model: string;
  customModelId: string;
  llmUrl: string;
  hakimCount: number;
  judgePersonas: string[];
  simMode: string;
  hearingMode?: string;
};

const HEARING_MODE_OPTIONS = [
  { id: 'pemeriksaan_pendahuluan', label: 'Pendahuluan' },
  { id: 'perbaikan_permohonan', label: 'Perbaikan' },
  { id: 'keterangan_pemerintah_dpr', label: 'Pemerintah/DPR' },
  { id: 'pemeriksaan_ahli', label: 'Ahli' },
  { id: 'pembuktian', label: 'Pembuktian' },
  { id: 'putusan', label: 'Putusan' },
  { id: 'full_training_simulation', label: 'Simulasi Lengkap' },
] as const;

type PreviewDocument = {
  fileId: string;
  filename: string;
  url: string;
  mimeType: string;
};

type LegalReference = {
  title: string;
  snippet: string;
  content?: string;
  full_content?: string;
  relevant_content?: string;
  source_url?: string;
  source_pdf_url?: string;
  content_source?: string;
  content_error?: string;
  content_truncated?: boolean;
  articles_count?: number;
  matching_pasals: string;
  query: string;
  source: string;
  score?: number;
  url?: string;
};

const getDefaultModel = (provider: string) => {
  if (provider === 'deepseek') return 'deepseek-v4-flash';
  if (provider === 'mimo') return 'mimo-v2-omni';
  if (provider === 'openrouter') return 'deepseek/deepseek-v4-flash';
  if (provider === 'claude') return 'claude-haiku-4-5';
  return 'local-model';
};

const normalizeModelForProvider = (provider: string, model: string) => {
  const fallback = getDefaultModel(provider);
  if (!model) return fallback;
  if (provider === 'deepseek' && !model.startsWith('deepseek-v4-')) return fallback;
  if (provider === 'mimo' && !model.startsWith('mimo-')) return fallback;
  if (provider === 'openrouter' && !model.includes('/')) return fallback;
  if (provider === 'claude' && !model.startsWith('claude-')) return fallback;
  return model;
};

const formatDuration = (totalSeconds: number) => {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds || 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const getTranscriptStyle = (speaker = '', role = '') => {
  const identity = `${speaker} ${role}`.toLowerCase();
  if (identity.includes('pemohon') || identity.includes('kuasa hukum pemohon')) {
    return {
      side: 'right',
      label: 'bg-amber-100 text-amber-800 border-amber-200',
      bubble: 'bg-amber-50 border-amber-200 text-slate-950 shadow-[0_10px_26px_rgba(180,124,24,0.12)]',
      avatar: 'bg-amber-500 text-white',
    };
  }
  if (identity.includes('presiden') || identity.includes('pemerintah') || identity.includes('dpr')) {
    return {
      side: 'left',
      label: 'bg-rose-100 text-rose-800 border-rose-200',
      bubble: 'bg-rose-50 border-rose-200 text-slate-950 shadow-[0_10px_26px_rgba(190,18,60,0.08)]',
      avatar: 'bg-rose-600 text-white',
    };
  }
  if (identity.includes('hakim') || identity.includes('ketua')) {
    return {
      side: 'left',
      label: 'bg-blue-100 text-blue-800 border-blue-200',
      bubble: 'bg-blue-50 border-blue-200 text-slate-950 shadow-[0_10px_26px_rgba(37,99,235,0.08)]',
      avatar: 'bg-blue-700 text-white',
    };
  }
  if (identity.includes('ahli')) {
    return {
      side: 'left',
      label: 'bg-violet-100 text-violet-800 border-violet-200',
      bubble: 'bg-violet-50 border-violet-200 text-slate-950 shadow-[0_10px_26px_rgba(124,58,237,0.08)]',
      avatar: 'bg-violet-600 text-white',
    };
  }
  if (identity.includes('pihak terkait')) {
    return {
      side: 'left',
      label: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      bubble: 'bg-emerald-50 border-emerald-200 text-slate-950 shadow-[0_10px_26px_rgba(5,150,105,0.08)]',
      avatar: 'bg-emerald-600 text-white',
    };
  }
  if (identity.includes('amicus')) {
    return {
      side: 'left',
      label: 'bg-cyan-100 text-cyan-800 border-cyan-200',
      bubble: 'bg-cyan-50 border-cyan-200 text-slate-950 shadow-[0_10px_26px_rgba(8,145,178,0.08)]',
      avatar: 'bg-cyan-600 text-white',
    };
  }
  return {
    side: 'left',
    label: 'bg-slate-100 text-slate-700 border-slate-200',
    bubble: 'bg-white border-slate-200 text-slate-950 shadow-sm',
    avatar: 'bg-slate-500 text-white',
  };
};

const getInitials = (speaker = '', role = '') => {
  const text = speaker || role || '?';
  const words = text.replace(/[()—–-]/g, ' ').split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  if (words[0]?.toLowerCase() === 'kuasa') return 'KP';
  if (words[0]?.toLowerCase() === 'hakim') return 'HK';
  if (words[0]?.toLowerCase() === 'ahli') return 'AH';
  if (words[0]?.toLowerCase() === 'amicus') return 'AC';
  return words.slice(0, 2).map(word => word[0]).join('').toUpperCase();
};

const SimulationPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { 
    isRunning, 
    transcript, 
    scores, 
    progress, 
    error, 
    currentSimulationId,
    currentProjectId,
    currentDraft,
    simulationMetadata,
    humanTurn,
    setCurrentDraft,
    startSimulation, 
    stopSimulation,
    syncSimulation,
    submitHumanInput,
    setTranscript,
    setScores,
    setProgress,
    setError,
    setSimulationMetadata
  } = useSimulation();

  const projectId = searchParams.get('project') || currentProjectId || '';
  const savedSimulationId = searchParams.get('saved');


  const { project } = useProject(projectId);
  const { files, uploadFile: uploadProjectFile, uploading: projectUploading, getFileContent } = useProjectFiles(projectId);

  // Re-sync if there's an active simulation id but no local transcript
  useEffect(() => {
    if (!savedSimulationId && currentSimulationId && transcript.length === 0) {
      syncSimulation(currentSimulationId);
    }
  }, [currentSimulationId, savedSimulationId, syncSimulation, transcript.length]);
  const { settings } = useSettings();
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [draft, setDraft] = useState(currentDraft);
  
  // Sync local draft with context when context changes (e.g. on resume)
  useEffect(() => {
    if (currentDraft && !draft) {
      setDraft(currentDraft);
    }
  }, [currentDraft, draft]);

  // Update context draft when local draft changes
  useEffect(() => {
    setCurrentDraft(draft);
  }, [draft, setCurrentDraft]);

  useEffect(() => {
    if (!savedSimulationId) return;

    const loadSavedSimulation = async () => {
      try {
        setError(null);
        const res = await fetch(`/api/saved-simulations/${savedSimulationId}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const loadedScores = {
          ...(data.scores || {}),
          breakdown: data.scores?.breakdown || {
            legal_standing: data.scores?.legal_standing || 0,
            kerugian_konstitusional: data.scores?.kerugian_konstitusional || 0,
            substansi_argumen: data.scores?.substansi_argumen || 0,
            konsistensi_putusan: data.scores?.konsistensi_putusan || 0,
            kelengkapan_formil: data.scores?.kelengkapan_formil || 0,
          },
          individual: data.individual_scores || [],
          feedback: data.feedback || null,
          dissenting_opinions: data.dissenting_opinions || [],
        } as Scores;

        setDraft(data.draft || '');
        setCurrentDraft(data.draft || '');
        setTranscript(data.transcript || []);
        setScores(loadedScores);
        setSimulationMetadata({
          ...(data.metadata || {}),
          llm_provider: data.metadata?.llm_provider || data.config?.llm_config?.provider,
          llm_model: data.metadata?.llm_model || data.config?.llm_config?.model_name,
          llm_base_url: data.metadata?.llm_base_url || data.config?.llm_config?.base_url,
        });
        setProgress({ phase: 'Riwayat', message: 'Simulasi tersimpan dimuat', status: 'done' });
        setActionMessage('Riwayat simulasi berhasil dimuat.');
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Gagal memuat riwayat simulasi');
      }
    };

    loadSavedSimulation();
  }, [savedSimulationId, setCurrentDraft, setError, setProgress, setScores, setSimulationMetadata, setTranscript]);

  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [hakimCount, setHakimCount] = useState(settings.hakimCount || 3);
  const [simMode, setSimMode] = useState(settings.simMode || 'ai');
  const [hearingMode, setHearingMode] = useState(settings.hearingMode || 'pemeriksaan_pendahuluan');
  const [judgePersonas, setJudgePersonas] = useState<string[]>(settings.judgePersonas || [...JUDGE_PERSONA_OPTIONS]);
  const [showConfig, setShowConfig] = useState(false);
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [actionBusy, setActionBusy] = useState<'save' | 'download' | null>(null);
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0);
  const [previewDoc, setPreviewDoc] = useState<PreviewDocument | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const [legalReferences, setLegalReferences] = useState<LegalReference[]>([]);
  const [legalReferenceQueries, setLegalReferenceQueries] = useState<string[]>([]);
  const [legalReferenceWarnings, setLegalReferenceWarnings] = useState<string[]>([]);
  const [legalReferencesLoading, setLegalReferencesLoading] = useState(false);
  const [legalReferencesError, setLegalReferencesError] = useState<string | null>(null);
  const [selectedLegalReference, setSelectedLegalReference] = useState<LegalReference | null>(null);
  const [humanReplyState, setHumanReplyState] = useState({ turnKey: '', value: '' });
  const [humanInputErrorState, setHumanInputErrorState] = useState<{ turnKey: string; message: string | null }>({ turnKey: '', message: null });
  const [humanInputSubmitting, setHumanInputSubmitting] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const projectFileInputRef = useRef<HTMLInputElement>(null);
  const hasSimulationActivity = isRunning || transcript.length > 0 || !!scores || !!savedSimulationId;
  const showLegalReferences = hasSimulationActivity;
  const referenceTranscriptContext = useMemo(() => {
    return transcript
      .slice(-8)
      .map((entry) => {
        const identity = [entry.speaker, entry.role].filter(Boolean).join(' ');
        const content = (entry.content || '').replace(/\s+/g, ' ').trim().slice(0, 900);
        return content ? `${identity}: ${content}` : '';
      })
      .filter(Boolean)
      .join('\n');
  }, [transcript]);
  const humanTurnKey = humanTurn?.turn_id || String(humanTurn?.requested_at || '');
  const humanReply = humanReplyState.turnKey === humanTurnKey ? humanReplyState.value : '';
  const humanInputError = humanInputErrorState.turnKey === humanTurnKey ? humanInputErrorState.message : null;
  const setHumanReplyForTurn = useCallback((value: string) => {
    setHumanReplyState({ turnKey: humanTurnKey, value });
  }, [humanTurnKey]);
  const setHumanErrorForTurn = useCallback((message: string | null) => {
    setHumanInputErrorState({ turnKey: humanTurnKey, message });
  }, [humanTurnKey]);

  const loadLegalReferences = useCallback(async (signal?: AbortSignal) => {
    if (!draft.trim()) {
      setLegalReferences([]);
      setLegalReferenceQueries([]);
      setLegalReferenceWarnings([]);
      setLegalReferencesError(null);
      return;
    }

    setLegalReferencesLoading(true);
    setLegalReferencesError(null);
    try {
      const res = await fetch('/api/legal-references', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft, transcript: referenceTranscriptContext }),
        signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setLegalReferences(Array.isArray(data.references) ? data.references : []);
      setLegalReferenceQueries(Array.isArray(data.queries) ? data.queries : []);
      setLegalReferenceWarnings(Array.isArray(data.warnings) ? data.warnings : []);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setLegalReferencesError(err instanceof Error ? err.message : 'Gagal memuat referensi peraturan.');
    } finally {
      if (!signal?.aborted) setLegalReferencesLoading(false);
    }
  }, [draft, referenceTranscriptContext]);

  useEffect(() => {
    if (!showLegalReferences) {
      setLegalReferences([]);
      setLegalReferenceQueries([]);
      setLegalReferenceWarnings([]);
      setLegalReferencesError(null);
      setLegalReferencesLoading(false);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => loadLegalReferences(controller.signal),
      referenceTranscriptContext ? 600 : 0
    );
    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [currentSimulationId, loadLegalReferences, referenceTranscriptContext, showLegalReferences]);

  const handleProjectFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadProjectFile(file);
    if (projectFileInputRef.current) projectFileInputRef.current.value = '';
  }, [uploadProjectFile]);

  const handleSelectFile = async (fileId: string, filename: string, mimeType: string) => {
    if (isRunning || isExtracting) return;
    setSelectedFileId(fileId);
    if (!hasSimulationActivity) {
      setPreviewDoc({
        fileId,
        filename,
        mimeType,
        url: `/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/raw`,
      });
    }
    setIsExtracting(true);
    try {
      const content = await getFileContent(fileId);
      if (content !== null) setDraft(content);
    } finally {
      setIsExtracting(false);
    }
  };

  const handlePreviewFile = async (e: React.MouseEvent<HTMLButtonElement>, fileId: string, filename: string, mimeType: string) => {
    e.stopPropagation();
    if (previewLoadingId || hasSimulationActivity) return;
    setPreviewLoadingId(fileId);
    try {
      setPreviewDoc({
        fileId,
        filename,
        mimeType,
        url: `/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/raw`,
      });
    } finally {
      setPreviewLoadingId(null);
    }
  };

  // Sync with settings when they load
  useEffect(() => {
    if (settings.hakimCount) setHakimCount(settings.hakimCount);
    if (settings.simMode) setSimMode(settings.simMode);
    if (settings.hearingMode) setHearingMode(settings.hearingMode);
    if (settings.judgePersonas) setJudgePersonas(settings.judgePersonas);
  }, [settings]);

  // Auto scroll to bottom of transcript
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, humanTurn]);

  useEffect(() => {
    const getElapsed = () => {
      if (simulationMetadata?.duration_seconds !== undefined) {
        return simulationMetadata.duration_seconds;
      }
      if (!simulationMetadata?.started_at) return 0;
      const startedAt = new Date(simulationMetadata.started_at).getTime();
      if (!Number.isFinite(startedAt)) return 0;
      return Math.max(0, Math.round((Date.now() - startedAt) / 1000));
    };

    setLiveElapsedSeconds(getElapsed());
    if (!isRunning || !simulationMetadata?.started_at || simulationMetadata.duration_seconds !== undefined) {
      return;
    }

    const interval = window.setInterval(() => setLiveElapsedSeconds(getElapsed()), 1000);
    return () => window.clearInterval(interval);
  }, [isRunning, simulationMetadata?.duration_seconds, simulationMetadata?.started_at]);

  const handleStart = async () => {
    if (!draft.trim()) return;

    const simId = `sim_${Date.now()}`;

    let latestSettings: SimulationSettings = settings;
    try {
      const savedSettings = localStorage.getItem('simulasiMK_settings');
      if (savedSettings) {
        const parsed = JSON.parse(savedSettings);
        if (parsed && typeof parsed === 'object') {
          latestSettings = { ...settings, ...parsed };
        }
      }
    } catch (err) {
      console.error('Failed to read latest settings:', err);
    }

    const provider = latestSettings.provider || 'local';
    const selectedModel = latestSettings.customModelId || latestSettings.model || getDefaultModel(provider);
    const llmConfig: LlmConfig = {
      provider,
      model_name: normalizeModelForProvider(provider, selectedModel),
      api_key: latestSettings.apiKey || '',
      base_url: provider === 'local' ? (latestSettings.llmUrl || 'http://localhost:1234/v1') : ''
    };

    setActionMessage(`Memulai simulasi dengan ${llmConfig.provider}: ${llmConfig.model_name}`);
    setPreviewDoc(null);

    await startSimulation(
      draft,
      hakimCount,
      llmConfig,
      simMode === 'ai' ? 'judicial_review' : 'interactive', // mode mapping
      simId,
      projectId,
      judgePersonas,
      hearingMode
    );
  };

  const handleSubmitHumanReply = useCallback(async (replyText?: string) => {
    const text = (replyText ?? humanReply).trim();
    if (!text || humanInputSubmitting) return;

    setHumanInputSubmitting(true);
    setHumanErrorForTurn(null);
    try {
      await submitHumanInput(text);
      setHumanReplyForTurn('');
      setActionMessage('Jawaban Pemohon dikirim.');
    } catch (err: unknown) {
      setHumanErrorForTurn(err instanceof Error ? err.message : 'Gagal mengirim jawaban Pemohon.');
    } finally {
      setHumanInputSubmitting(false);
    }
  }, [humanInputSubmitting, humanReply, setActionMessage, setHumanErrorForTurn, setHumanReplyForTurn, submitHumanInput]);

  const buildResultPayload = useCallback(() => {
    if (!scores) return null;
    const { individual, feedback, dissenting_opinions, ...scoreFields } = scores;
    return {
      simulation_id: savedSimulationId || currentSimulationId || `manual_${Date.now()}`,
      draft,
      transcript,
      scores: scoreFields,
      individual_scores: Array.isArray(individual) ? individual : Object.values(individual || {}),
      dissenting_opinions: dissenting_opinions || [],
      feedback: feedback || {},
      metadata: {
        ...(simulationMetadata || {}),
        duration_seconds: simulationMetadata?.duration_seconds ?? liveElapsedSeconds,
      },
    };
  }, [currentSimulationId, draft, liveElapsedSeconds, savedSimulationId, scores, simulationMetadata, transcript]);

  const handleSaveSimulation = useCallback(async () => {
    const payload = buildResultPayload();
    if (!payload) {
      setActionMessage('Belum ada hasil simulasi untuk disimpan.');
      return;
    }

    setActionBusy('save');
    setActionMessage(null);
    try {
      const res = await fetch('/api/saved-simulations/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sim_id: payload.simulation_id,
          simulation_data: payload,
          draft,
          config: {
            jumlah_hakim: hakimCount,
            mode: simMode,
            hearing_mode: hearingMode,
            judge_personas: judgePersonas,
            project_id: projectId || null,
            llm_config: simulationMetadata ? {
              provider: simulationMetadata.llm_provider || '',
              model_name: simulationMetadata.llm_model || '',
              base_url: simulationMetadata.llm_base_url || '',
            } : undefined,
          },
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      setActionMessage(`Simulasi tersimpan: ${data.id || payload.simulation_id}`);
    } catch (err: unknown) {
      setActionMessage(err instanceof Error ? err.message : 'Gagal menyimpan simulasi.');
    } finally {
      setActionBusy(null);
    }
  }, [buildResultPayload, draft, hakimCount, hearingMode, judgePersonas, projectId, setActionMessage, simMode, simulationMetadata]);

  const handleDownloadPdf = useCallback(async () => {
    const payload = buildResultPayload();
    if (!payload) {
      setActionMessage('Belum ada hasil simulasi untuk diunduh.');
      return;
    }

    setActionBusy('download');
    setActionMessage(null);
    try {
      const res = await fetch('/api/export-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || `HTTP ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `putusan_mk_${payload.simulation_id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setActionMessage('PDF hasil simulasi berhasil diunduh.');
    } catch (err: unknown) {
      setActionMessage(err instanceof Error ? err.message : 'Gagal mengunduh PDF.');
    } finally {
      setActionBusy(null);
    }
  }, [buildResultPayload, setActionMessage]);

  const updatePersona = (index: number, value: string) => {
    const newPersonas = [...judgePersonas];
    newPersonas[index] = value;
    setJudgePersonas(newPersonas);
  };


  const personaOptions = [...JUDGE_PERSONA_OPTIONS];
  const roundSteps = [
    { phase: 'round1', label: 'Pendahuluan', short: 'R1' },
    { phase: 'round2', label: 'Perbaikan', short: 'R2' },
    { phase: 'round2b', label: 'Ahli', short: 'R2B' },
    { phase: 'round3', label: 'Pokok Perkara', short: 'R3' },
    { phase: 'round4', label: 'Kesimpulan & RPH', short: 'R4' },
    { phase: 'feedback', label: 'Umpan Balik', short: 'FB' },
  ];
  const currentPhase = progress?.phase || (scores ? 'done' : 'idle');
  const currentRoundIndex = roundSteps.findIndex(step => step.phase === currentPhase);
  const visibleRoundIndex = currentPhase === 'done'
    ? roundSteps.length
    : currentRoundIndex >= 0 ? currentRoundIndex : -1;
  const activeRound = roundSteps[currentRoundIndex];
  const progressPercent = currentPhase === 'done'
    ? 100
    : currentRoundIndex >= 0
    ? Math.round(((currentRoundIndex + 1) / roundSteps.length) * 100)
    : 0;
  const individualScores = scores
    ? Array.isArray(scores.individual)
      ? scores.individual
      : Object.values(scores.individual || {})
    : [];
  const majorityCount = scores?.voting_detail && scores.amar
    ? scores.voting_detail[scores.amar] || 0
    : 0;
  const verdictLabel = (amar?: string) => {
    if (amar === 'dikabulkan') return 'Dikabulkan';
    if (amar === 'ditolak') return 'Ditolak';
    if (amar === 'tidak_dapat_diterima') return 'Tidak Dapat Diterima';
    return amar ? amar.replace(/_/g, ' ') : '-';
  };
  const scoreColor = (score: number) => {
    if (score >= 70) return '#10b981';
    if (score >= 50) return '#f59e0b';
    return '#ef4444';
  };
  const previewFilename = previewDoc?.filename.toLowerCase() || '';
  const canPreviewInline = !!previewDoc && (
    previewDoc.mimeType.includes('pdf') ||
    previewDoc.mimeType.startsWith('image/') ||
    previewDoc.mimeType.startsWith('text/') ||
    previewFilename.endsWith('.pdf') ||
    previewFilename.endsWith('.txt')
  );

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col gap-6 animate-slide-in relative">
      {/* Simulation Config Panel (Floating Overlay) */}
      {showConfig && (
        <div className="absolute top-20 right-6 w-80 bg-white rounded-2xl border border-primary/20 shadow-2xl z-50 p-5 animate-slide-down">
          <div className="flex justify-between items-center mb-4 pb-2 border-b border-border">
            <h3 className="font-black text-xs text-primary uppercase tracking-widest">Parameter Simulasi</h3>
            <button onClick={() => setShowConfig(false)} className="text-text-muted hover:text-pemerintah">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-text-muted uppercase mb-2">Jumlah Hakim Panel</label>
              <div className="grid grid-cols-4 gap-2">
                {[3, 5, 7, 9].map(n => (
                  <button
                    key={n}
                    onClick={() => setHakimCount(n)}
                    className={`py-1.5 rounded-lg text-xs font-bold transition-all ${hakimCount === n ? 'bg-primary text-white shadow-md' : 'bg-bg-secondary text-text-muted hover:bg-slate-200'}`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-text-muted uppercase mb-2">Mode Persidangan</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setSimMode('ai')}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${simMode === 'ai' ? 'bg-primary text-white shadow-md' : 'bg-bg-secondary text-text-muted hover:bg-slate-200'}`}
                >
                  AI vs AI
                </button>
                <button
                  onClick={() => setSimMode('human')}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${simMode === 'human' ? 'bg-primary text-white shadow-md' : 'bg-bg-secondary text-text-muted hover:bg-slate-200'}`}
                >
                  Interaktif
                </button>
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-text-muted uppercase mb-2">Profil Sidang</label>
              <select
                value={hearingMode}
                onChange={(e) => setHearingMode(e.target.value)}
                className="w-full bg-bg-secondary border border-border rounded-lg px-3 py-2 text-xs font-bold text-primary outline-none focus:border-primary/50"
              >
                {HEARING_MODE_OPTIONS.map(option => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-text-muted uppercase mb-2">Persona Hakim (Panel {hakimCount})</label>
              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                {Array(hakimCount).fill(0).map((_, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 p-2 bg-bg-secondary rounded-lg border border-border/50">
                    <span className="text-[10px] font-bold text-text-muted shrink-0">H{i + 1}</span>
                    <select
                      value={judgePersonas[i] || 'formalis'}
                      onChange={(e) => updatePersona(i, e.target.value)}
                      className="flex-1 bg-transparent text-[10px] font-bold text-primary outline-none cursor-pointer"
                    >
                      {personaOptions.map(opt => (
                        <option key={opt} value={opt}>{opt.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-[9px] text-text-muted italic leading-relaxed pt-2 border-t border-border">
              * Persona hakim menentukan paradigma hukum (Formalis, Progresif, atau Positivis) dalam menilai permohonan.
            </p>
          </div>
        </div>
      )}

      {/* Simulation Header */}
      <div className="flex justify-between items-center bg-white p-4 rounded-2xl border border-border shadow-sm">
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-primary/5 flex items-center justify-center text-primary border border-primary/10">
            <Terminal className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h2 className="font-bold text-text-primary flex items-center gap-2">
              {project?.name || 'Simulation Workspace'}
              {isRunning && (
                <span className="text-[10px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-bold uppercase animate-pulse">
                  Simulation Active
                </span>
              )}
            </h2>
            <div className="flex items-center gap-3 mt-1">
              <span className="text-xs text-text-muted flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {progress?.phase || 'Idle'}
              </span>
              <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
              <span className="text-xs text-text-muted flex items-center gap-1">
                <Users className="w-3 h-3" /> {hakimCount} Hakim MK
              </span>
              {(simulationMetadata?.started_at || liveElapsedSeconds > 0) && (
                <>
                  <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                  <span className="text-xs text-text-muted flex items-center gap-1 tabular-nums">
                    <Clock className="w-3 h-3" />
                    {formatDuration(liveElapsedSeconds)}
                  </span>
                </>
              )}
              {(simulationMetadata?.llm_provider || simulationMetadata?.llm_model) && (
                <>
                  <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                  <span
                    className="text-xs text-text-muted flex items-center gap-1 min-w-0"
                    title={`${simulationMetadata?.llm_provider || 'LLM'}: ${simulationMetadata?.llm_model || '-'}`}
                  >
                    <Cpu className="w-3 h-3 shrink-0" />
                    <span className="truncate max-w-[220px]">
                      {simulationMetadata?.llm_provider || 'LLM'}: {simulationMetadata?.llm_model || '-'}
                    </span>
                  </span>
                </>
              )}
              {(simulationMetadata?.hearing_mode || simulationMetadata?.turn_count !== undefined) && (
                <>
                  <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                  <span className="text-xs text-text-muted flex items-center gap-1">
                    <Gavel className="w-3 h-3" />
                    {simulationMetadata?.hearing_mode || hearingMode}
                    {simulationMetadata?.turn_count !== undefined ? ` · ${simulationMetadata.turn_count} turn` : ''}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="hidden xl:flex items-center gap-2 ml-3 pl-4 border-l border-border">
            {roundSteps.map((step, idx) => {
              const isActive = currentPhase === step.phase;
              const isDone = visibleRoundIndex > idx;
              return (
                <div key={step.phase} className="flex items-center gap-2">
                  <div className={`h-7 min-w-7 px-2 rounded-full border flex items-center justify-center text-[9px] font-black transition-all ${
                    isActive
                      ? 'bg-primary text-white border-primary shadow-sm'
                      : isDone
                      ? 'bg-dikabulkan text-white border-dikabulkan'
                      : 'bg-white text-text-muted border-slate-200'
                  }`}>
                    {isDone && !isActive ? <CheckCircle2 className="w-3.5 h-3.5" /> : step.short}
                  </div>
                  {idx < roundSteps.length - 1 && (
                    <div className={`h-px w-4 ${visibleRoundIndex > idx ? 'bg-dikabulkan' : 'bg-slate-200'}`} />
                  )}
                </div>
              );
            })}
          </div>
          <div className="hidden lg:flex xl:hidden items-center gap-2 ml-3 pl-4 border-l border-border">
            <span className={`h-2 w-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : currentPhase === 'done' ? 'bg-dikabulkan' : 'bg-slate-300'}`} />
            <span className="text-[10px] font-black uppercase tracking-widest text-primary whitespace-nowrap">
              {currentPhase === 'done' ? 'Selesai' : activeRound?.label || progress?.message || 'Idle'}
            </span>
            <span className="text-[10px] font-black text-text-muted tabular-nums">{progressPercent}%</span>
          </div>
        </div>
        <div className="flex items-center gap-3 min-w-0">
          {actionMessage && (
            <div
              className="hidden md:block max-w-[420px] truncate rounded-xl border border-primary/10 bg-primary/5 px-3 py-2 text-xs font-bold text-text-secondary"
              title={actionMessage}
            >
              {actionMessage}
            </div>
          )}
          <button
            onClick={() => setShowConfig(!showConfig)}
            className={`p-2.5 rounded-xl transition-all border ${showConfig ? 'bg-primary/10 border-primary/30 text-primary' : 'text-text-muted border-transparent hover:bg-bg-primary hover:border-border'}`}
            title="Konfigurasi Simulasi"
          >
            <Settings className="w-5 h-5" />
          </button>
          {error && (
            <div className="flex items-center gap-2 text-pemerintah px-3 py-1 bg-red-50 rounded-lg text-xs font-bold mr-2">
              <AlertTriangle className="w-4 h-4" />
              {error}
            </div>
          )}
          <button
            onClick={handleSaveSimulation}
            disabled={!scores || actionBusy !== null}
            className="p-2.5 text-text-muted hover:text-primary hover:bg-bg-primary rounded-xl transition-all border border-transparent hover:border-border disabled:opacity-40 disabled:hover:text-text-muted"
            title="Simpan hasil simulasi ke riwayat"
          >
            {actionBusy === 'save' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
          </button>
          <button
            onClick={handleDownloadPdf}
            disabled={!scores || actionBusy !== null}
            className="p-2.5 text-text-muted hover:text-primary hover:bg-bg-primary rounded-xl transition-all border border-transparent hover:border-border disabled:opacity-40 disabled:hover:text-text-muted"
            title="Download hasil simulasi sebagai PDF"
          >
            {actionBusy === 'download' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Download className="w-5 h-5" />}
          </button>
          <div className="w-[1px] h-6 bg-border mx-1"></div>
        </div>
      </div>

      <div className="flex-1 flex gap-6 overflow-hidden">
        {/* Left: Document Sidebar */}
        <aside className="w-72 shrink-0 bg-white rounded-2xl border border-border flex flex-col shadow-sm overflow-hidden">
              <div className="p-4 border-b border-border bg-bg-primary flex justify-between items-center gap-2">
                <h3 className="font-bold text-sm text-text-primary flex items-center gap-2 min-w-0">
                  {showLegalReferences ? (
                    <>
                      <BookOpen className="w-4 h-4 shrink-0" /> <span className="truncate">Referensi Peraturan</span>
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 shrink-0" /> <span className="truncate">Daftar Dokumen</span>
                    </>
                  )}
                </h3>
                <div className="flex items-center gap-1.5 shrink-0">
                  {showLegalReferences ? (
                    <button
                      onClick={() => loadLegalReferences()}
                      disabled={legalReferencesLoading}
                      className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary hover:text-white transition-all disabled:opacity-50"
                      title="Muat ulang referensi Pasal.id"
                    >
                      {legalReferencesLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    </button>
                  ) : (
                    <button
                      onClick={() => projectFileInputRef.current?.click()}
                      disabled={projectUploading}
                      className="p-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary hover:text-white transition-all disabled:opacity-50"
                      title="Upload Dokumen Baru"
                    >
                      {projectUploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                    </button>
                  )}
                </div>
                <input
                  ref={projectFileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.doc,.txt"
                  onChange={handleProjectFileUpload}
                />
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {showLegalReferences ? (
                  <LegalReferencePanel
                    references={legalReferences}
                    queries={legalReferenceQueries}
                    warnings={legalReferenceWarnings}
                    error={legalReferencesError}
                    loading={legalReferencesLoading}
                    onOpenReference={setSelectedLegalReference}
                  />
                ) : (
                  files.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 text-center space-y-2">
                      <FileText className="w-8 h-8 text-text-muted opacity-10" />
                      <p className="text-[10px] text-text-muted italic">Belum ada dokumen di project ini.</p>
                    </div>
                  ) : (
                    files.map((file, idx) => (
                      <div
                        key={idx}
                        onClick={() => handleSelectFile(file.id, file.filename, file.mime_type || '')}
                        className={`relative h-10 px-3 rounded-lg transition-all cursor-pointer group flex items-center gap-2 ${
                          selectedFileId === file.id
                          ? 'bg-primary/[0.06]'
                          : 'hover:bg-primary/[0.035]'
                        }`}
                      >
                        {selectedFileId === file.id && (
                          <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-primary" />
                        )}
                        <FileText className={`w-3.5 h-3.5 shrink-0 ${selectedFileId === file.id ? 'text-primary' : 'text-text-muted'}`} />
                        <p className={`flex-1 min-w-0 text-xs font-bold truncate ${selectedFileId === file.id ? 'text-primary' : 'text-text-primary'}`}>
                          {file.filename}
                        </p>
                        {isExtracting && selectedFileId === file.id && (
                          <Loader2 className="w-3.5 h-3.5 text-primary animate-spin shrink-0" />
                        )}
                        <button
                          type="button"
                          onClick={(e) => handlePreviewFile(e, file.id, file.filename, file.mime_type || '')}
                          disabled={hasSimulationActivity}
                          className={`w-7 h-7 rounded-md flex items-center justify-center transition-all shrink-0 ${
                            previewDoc?.fileId === file.id && !hasSimulationActivity
                              ? 'bg-white text-primary shadow-sm'
                              : 'text-text-muted hover:text-primary hover:bg-white/80 disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-text-muted'
                          }`}
                          title={hasSimulationActivity ? 'Transkrip sidang sedang aktif' : 'Tampilkan preview dokumen'}
                        >
                          {previewLoadingId === file.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Eye className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    ))
                  )
                )}
              </div>
              <div className="p-4 border-t border-border bg-bg-primary space-y-3">
                {showLegalReferences ? (
                  isRunning ? (
                    <button
                      onClick={() => stopSimulation()}
                      className="w-full bg-pemerintah text-white py-3 rounded-xl font-bold text-sm shadow-lg shadow-pemerintah/20 hover:bg-red-700 transition-all flex items-center justify-center gap-2"
                    >
                      <X className="w-4 h-4" /> Hentikan Simulasi
                    </button>
                  ) : (
                    <p className="text-[10px] text-text-muted text-center leading-relaxed">
                      Referensi mengikuti draft simulasi saat ini.
                    </p>
                  )
                ) : (
                <>
                  {!selectedFileId && !isRunning && (
                  <p className="text-[10px] text-pemerintah text-center font-bold animate-pulse">
                    Pilih dokumen untuk disimulasikan
                  </p>
                  )}
                  {isRunning ? (
                    <button
                      onClick={() => stopSimulation()}
                      className="w-full bg-pemerintah text-white py-3 rounded-xl font-bold text-sm shadow-lg shadow-pemerintah/20 hover:bg-red-700 transition-all flex items-center justify-center gap-2"
                    >
                      <X className="w-4 h-4" /> Hentikan Simulasi
                    </button>
                  ) : (
                    <button
                      onClick={handleStart}
                      disabled={!selectedFileId || isExtracting}
                      className="w-full bg-primary text-white py-3 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:bg-primary-light transition-all disabled:opacity-50 disabled:grayscale flex items-center justify-center gap-2"
                    >
                      {isExtracting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                      {isExtracting ? 'Mengekstrak...' : 'Mulai Simulasi'}
                    </button>
                  )}
                </>
                  )}
                </div>
        </aside>

        {/* Right: Document Preview / Chat Transcript */}
        <div className="flex-1 bg-white rounded-2xl border border-border flex flex-col shadow-sm overflow-hidden">
          {!hasSimulationActivity ? (
            previewDoc ? (
              <div className="flex h-full min-h-0 flex-col">
                <div className="px-5 py-4 border-b border-border bg-bg-primary flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="text-sm font-black text-primary uppercase tracking-widest">Preview Dokumen</h3>
                    <p className="text-xs font-bold text-text-primary truncate mt-1">{previewDoc.filename}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <a
                      href={previewDoc.url}
                      target="_blank"
                      rel="noreferrer"
                      className="w-9 h-9 rounded-lg border border-border text-text-muted hover:text-primary hover:bg-white transition-all flex items-center justify-center"
                      title="Buka file asli"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                    <button
                      type="button"
                      onClick={() => setPreviewDoc(null)}
                      className="w-9 h-9 rounded-lg border border-border text-text-muted hover:text-pemerintah hover:bg-white transition-all flex items-center justify-center"
                      title="Tutup preview"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="flex-1 min-h-0 bg-slate-100">
                  {canPreviewInline ? (
                    <iframe
                      src={previewDoc.url}
                      title={`Preview ${previewDoc.filename}`}
                      className="w-full h-full bg-white border-0"
                    />
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-center p-8">
                      <FileText className="w-14 h-14 text-text-muted opacity-30 mb-4" />
                      <h4 className="text-sm font-black text-primary uppercase tracking-widest mb-2">Preview Asli Tidak Didukung Browser</h4>
                      <p className="text-sm text-text-secondary max-w-md leading-relaxed mb-4">
                        Format ini perlu dibuka dengan aplikasi dokumen. File asli tetap tersedia tanpa konversi.
                      </p>
                      <a
                        href={previewDoc.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-xs font-black uppercase tracking-widest text-white transition-all hover:bg-primary-light"
                      >
                        <ExternalLink className="w-4 h-4" />
                        Buka File Asli
                      </a>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 text-text-muted bg-gradient-to-b from-white to-slate-50/80">
                <FileText className="w-16 h-16 mb-4 opacity-20" />
                <h3 className="text-sm font-black text-primary uppercase tracking-widest">Preview Dokumen</h3>
                <p className="mt-2 text-sm font-serif italic opacity-70">
                  {selectedFileId ? 'Preview dokumen ditutup.' : 'Belum ada dokumen yang dipilih.'}
                </p>
              </div>
            )
          ) : (
            <div className="flex h-full min-h-0 flex-col">
            <div className="flex-1 overflow-y-auto p-6 space-y-5 scroll-smooth bg-gradient-to-b from-white to-slate-50/80">
            {transcript.length === 0 && !isRunning && (
              <div className="h-full flex flex-col items-center justify-center text-text-muted opacity-40">
                <Terminal className="w-16 h-16 mb-4" />
                <p className="text-sm font-serif italic">Belum ada aktivitas sidang. Masukkan draf untuk memulai.</p>
              </div>
            )}
            {transcript.map((msg, idx) => {
              const style = getTranscriptStyle(msg.speaker, msg.role);
              const isRight = style.side === 'right';
              return (
                <div key={idx} className={`flex ${isRight ? 'justify-end' : 'justify-start'} animate-fade-in`}>
                  <div className={`flex max-w-[86%] gap-3 ${isRight ? 'flex-row-reverse' : 'flex-row'}`}>
                    <div className={`mt-7 h-9 w-9 shrink-0 rounded-full ${style.avatar} flex items-center justify-center text-[11px] font-black shadow-sm`}>
                      {getInitials(msg.speaker, msg.role)}
                    </div>
                    <div className={`flex min-w-0 flex-col ${isRight ? 'items-end' : 'items-start'}`}>
                      <span className={`mb-1.5 max-w-full truncate rounded-full border px-2.5 py-0.5 text-[10px] font-black uppercase tracking-widest ${style.label}`}>
                        {msg.speaker || msg.role}
                      </span>
                      <div
                        className={`rounded-2xl border px-4 py-3 text-sm leading-relaxed ${style.bubble} ${
                          isRight ? 'rounded-tr-sm' : 'rounded-tl-sm'
                        }`}
                      >
                        {msg.content}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            {isRunning && !humanTurn && (
              <div className="flex justify-start animate-fade-in">
                <div className="flex max-w-[86%] gap-3">
                  <div className="mt-6 h-9 w-9 shrink-0 rounded-full bg-slate-600 text-white flex items-center justify-center text-[11px] font-black shadow-sm">
                    MK
                  </div>
                  <div className="flex flex-col items-start">
                    <span className="mb-1.5 rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-widest text-slate-600">
                      {progress?.phase === 'done' ? 'Memproses hasil' : progress?.message || 'Sidang berjalan'}
                    </span>
                    <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
                      <div className="flex items-center gap-1.5">
                        {[0, 1, 2].map((dot) => (
                          <span
                            key={dot}
                            className="h-2 w-2 rounded-full bg-slate-400 animate-bounce"
                            style={{ animationDelay: `${dot * 120}ms` }}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Verdict / Amar Putusan */}
            {!isRunning && scores && scores.amar && typeof scores.amar === 'string' && (
              <div className="mt-6 space-y-4 animate-fade-in">
                {/* Amar Banner */}
                <div className={`rounded-2xl p-6 border-2 text-center ${
                  scores.amar === 'dikabulkan'
                    ? 'bg-emerald-50 border-emerald-300'
                    : scores.amar === 'ditolak'
                    ? 'bg-red-50 border-red-300'
                    : 'bg-amber-50 border-amber-300'
                }`}>
                  <div className="flex items-center justify-center gap-3 mb-3">
                    <Gavel className={`w-8 h-8 ${
                      scores.amar === 'dikabulkan' ? 'text-emerald-600' :
                      scores.amar === 'ditolak' ? 'text-red-600' : 'text-amber-600'
                    }`} />
                    <h2 className="text-2xl font-black uppercase tracking-wide">Amar Putusan</h2>
                  </div>
                  <p className={`text-3xl font-black uppercase ${
                    scores.amar === 'dikabulkan' ? 'text-emerald-700' :
                    scores.amar === 'ditolak' ? 'text-red-700' : 'text-amber-700'
                  }`}>
                    {scores.amar === 'dikabulkan' ? 'DIKABULKAN' :
                     scores.amar === 'ditolak' ? 'DITOLAK' :
                     scores.amar === 'tidak_dapat_diterima' ? 'TIDAK DAPAT DITERIMA' :
                     scores.amar.toUpperCase()}
                  </p>
                  {typeof scores.total === 'number' && (
                    <p className="text-sm text-text-muted mt-2 font-bold">
                      Total Skor: <span className="text-primary">{scores.total.toFixed(1)}</span> / 100
                    </p>
                  )}
                </div>

                {/* Voting Detail */}
                {scores.voting_detail && typeof scores.voting_detail === 'object' && !Array.isArray(scores.voting_detail) && Object.keys(scores.voting_detail).length > 0 && (
                  <div className="bg-white rounded-2xl p-5 border border-border shadow-sm">
                    <h3 className="text-xs font-black text-primary uppercase tracking-widest mb-4 flex items-center gap-2">
                      <Users className="w-4 h-4" /> Rekapitulasi Voting Hakim
                    </h3>
                    <div className="space-y-3">
                      {Object.entries(scores.voting_detail).map(([amarKey, count]) => (
                        <div key={amarKey} className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {amarKey === 'dikabulkan' ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> :
                             amarKey === 'ditolak' ? <XCircle className="w-4 h-4 text-red-500" /> :
                             <MinusCircle className="w-4 h-4 text-amber-500" />}
                            <span className="text-sm font-bold text-text-primary capitalize">
                              {amarKey === 'dikabulkan' ? 'Dikabulkan' :
                               amarKey === 'ditolak' ? 'Ditolak' :
                               amarKey === 'tidak_dapat_diterima' ? 'Tidak Dapat Diterima' :
                               amarKey === 'invalid' ? 'Tidak Valid' : amarKey}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  amarKey === 'dikabulkan' ? 'bg-emerald-500' :
                                  amarKey === 'ditolak' ? 'bg-red-500' : 'bg-amber-500'
                                }`}
                                style={{ width: `${((count as number) / hakimCount) * 100}%` }}
                              />
                            </div>
                            <span className="text-sm font-black text-text-primary w-8 text-right">
                              {count as number}
                            </span>
                            <span className="text-[10px] text-text-muted">hakim</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Score Breakdown */}
                {scores.breakdown && typeof scores.breakdown === 'object' && (
                  <div className="bg-white rounded-2xl p-5 border border-border shadow-sm">
                    <button
                      onClick={() => setShowBreakdown(!showBreakdown)}
                      className="w-full flex items-center justify-between text-xs font-black text-primary uppercase tracking-widest"
                    >
                      <span className="flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4" /> Breakdown Skor
                      </span>
                      {showBreakdown ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    {showBreakdown && (
                      <div className="mt-4 space-y-3">
                        {[
                          { key: 'legal_standing', label: 'Legal Standing', max: 25 },
                          { key: 'kerugian_konstitusional', label: 'Kerugian Konstitusional', max: 20 },
                          { key: 'substansi_argumen', label: 'Substansi Argumen', max: 30 },
                          { key: 'konsistensi_putusan', label: 'Konsistensi Putusan', max: 15 },
                          { key: 'kelengkapan_formil', label: 'Kelengkapan Formil', max: 10 },
                        ].map(dim => {
                          const val = (scores.breakdown as unknown as Record<string, number>)[dim.key] || 0;
                          const pct = (val / dim.max) * 100;
                          return (
                            <div key={dim.key}>
                              <div className="flex justify-between items-center mb-1">
                                <span className="text-xs text-text-secondary font-bold">{dim.label}</span>
                                <span className="text-xs font-black text-text-primary">{val} / {dim.max}</span>
                              </div>
                              <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-700 ${
                                    pct > 70 ? 'bg-emerald-500' : pct > 40 ? 'bg-amber-500' : 'bg-red-500'
                                  }`}
                                  style={{ width: `${pct}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Catatan Hakim */}
                {Array.isArray(scores.catatan_hakim) && scores.catatan_hakim.length > 0 && (
                  <div className="bg-white rounded-2xl p-5 border border-border shadow-sm">
                    <h3 className="text-xs font-black text-primary uppercase tracking-widest mb-3 flex items-center gap-2">
                      <FileText className="w-4 h-4" /> Catatan Hakim
                    </h3>
                    <div className="space-y-2">
                      {scores.catatan_hakim.map((catatan, idx) => (
                        <p key={idx} className="text-xs text-text-secondary leading-relaxed p-2 bg-bg-secondary rounded-lg">
                          {catatan}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dissenting Opinions */}
                {Array.isArray(scores.dissenting_opinions) && scores.dissenting_opinions.length > 0 && (
                  <div className="bg-white rounded-2xl p-5 border border-border shadow-sm">
                    <h3 className="text-xs font-black text-pemerintah uppercase tracking-widest mb-3 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" /> Dissenting Opinion
                    </h3>
                    <div className="space-y-4">
                      {scores.dissenting_opinions.map((op, idx) => (
                        <div key={idx} className="p-3 bg-red-50 rounded-xl border border-red-100">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-[10px] font-black text-pemerintah uppercase">{op?.hakim || `Hakim ${idx + 1}`}</span>
                            <span className="text-[10px] text-text-muted">—</span>
                            <span className="text-[10px] font-bold text-text-muted capitalize">
                              Voting: {(op?.amar_hakim || '').replace(/_/g, ' ')}
                            </span>
                          </div>
                          <p className="text-xs text-text-secondary leading-relaxed">{op?.opinion || '-'}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Feedback Hakim */}
                {scores.feedback && typeof scores.feedback === 'object' && !Array.isArray(scores.feedback) && !((scores.feedback as Record<string, unknown>)?.error) && (
                  <div className="bg-white rounded-2xl p-5 border border-border shadow-sm">
                    <h3 className="text-xs font-black text-primary uppercase tracking-widest mb-3 flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4" /> Umpan Balik Panel Hakim
                    </h3>
                    <div className="space-y-2">
                      {Object.entries(scores.feedback as Record<string, unknown>).map(([key, val]) => {
                        if (!val || key === 'error') return null;
                        const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                        return (
                          <div key={key} className="p-2 bg-bg-secondary rounded-lg">
                            <span className="text-[10px] font-black text-primary uppercase block mb-1">{label}</span>
                            <p className="text-xs text-text-secondary leading-relaxed">
                              {typeof val === 'string' ? val : JSON.stringify(val)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div ref={chatEndRef} />
            </div>
            {humanTurn && (
              <HumanTurnComposer
                turn={humanTurn}
                value={humanReply}
                error={humanInputError}
                isSubmitting={humanInputSubmitting}
                onChange={setHumanReplyForTurn}
                onSelectSuggestion={(suggestion) => {
                  setHumanReplyForTurn(suggestion);
                  setHumanErrorForTurn(null);
                }}
                onSubmit={() => handleSubmitHumanReply()}
              />
            )}
            </div>
          )}
        </div>

        {scores && (
          <aside className="w-80 shrink-0 bg-white rounded-2xl border border-border flex flex-col shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-bg-primary flex justify-between items-center">
              <h3 className="font-bold text-sm text-text-primary flex items-center gap-2">
                <ShieldCheck className="w-4 h-4" /> Indikasi Skor Hakim
              </h3>
              <span className="text-[10px] font-black text-primary bg-primary/10 px-2 py-1 rounded-full uppercase">
                {isRunning ? 'Live' : 'Final'}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div className="grid grid-cols-3 gap-3">
                {individualScores.slice(0, hakimCount).map((judgeScore, idx) => {
                  const total = Number(judgeScore.total || 0);
                  const color = scoreColor(total);
                  return (
                    <div key={idx} className="text-center">
                      <div
                        className="mx-auto w-16 h-16 rounded-full border-4 bg-white flex flex-col items-center justify-center shadow-sm"
                        style={{ borderColor: color }}
                      >
                        <span className="text-lg font-black leading-none" style={{ color }}>{Math.round(total)}</span>
                        <span className="text-[9px] text-text-muted font-bold">/100</span>
                      </div>
                      <p className="mt-2 text-[10px] font-black text-primary uppercase">Hakim {idx + 1}</p>
                      <p className="text-[9px] font-bold text-text-muted uppercase">{judgePersonas[idx] || 'hakim'}</p>
                      <p className={`text-[9px] font-black uppercase ${judgeScore.amar === 'dikabulkan' ? 'text-emerald-600' : judgeScore.amar === 'ditolak' ? 'text-red-600' : 'text-amber-600'}`}>
                        {verdictLabel(judgeScore.amar)}
                      </p>
                    </div>
                  );
                })}
              </div>

              <div className="rounded-2xl border border-border bg-bg-primary p-4">
                <h4 className="text-[10px] font-black text-primary uppercase tracking-widest mb-3">
                  Analisis Kecenderungan
                </h4>
                <div className="flex items-center justify-between text-xs mb-2">
                  <span className="text-text-secondary">Probabilitas Amar</span>
                  <span className="font-black text-emerald-600">
                    {hakimCount ? Math.round((majorityCount / hakimCount) * 100) : 0}% {verdictLabel(scores.amar)}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mb-4">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{ width: `${hakimCount ? (majorityCount / hakimCount) * 100 : 0}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-primary uppercase">Amar: {verdictLabel(scores.amar)}</span>
                  <span className="text-text-primary">{majorityCount} hakim</span>
                </div>
                <p className="text-[10px] text-text-muted leading-relaxed mt-3">
                  Panel hakim telah memutus. Lihat detail lengkap di area transkrip.
                </p>
              </div>

              {individualScores.length > 0 && (
                <div className="rounded-2xl border border-border bg-bg-primary p-4">
                  <h4 className="text-[10px] font-black text-primary uppercase tracking-widest mb-3">
                    Detail Skor Per Hakim
                  </h4>
                  <div className="space-y-3">
                    {individualScores.slice(0, hakimCount).map((judgeScore, idx) => (
                      <div key={idx} className="bg-white rounded-xl border border-border p-3">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-[10px] font-black text-primary uppercase">Hakim {idx + 1}</span>
                          <span className={`text-[10px] font-black uppercase ${judgeScore.amar === 'dikabulkan' ? 'text-emerald-600' : judgeScore.amar === 'ditolak' ? 'text-red-600' : 'text-amber-600'}`}>
                            {verdictLabel(judgeScore.amar)}
                          </span>
                        </div>
                        <div className="grid grid-cols-5 gap-2 text-center mb-3">
                          <div>
                            <p className="text-[9px] font-black text-text-muted">LS</p>
                            <p className="text-[10px] font-black text-text-primary">{judgeScore.legal_standing}</p>
                          </div>
                          <div>
                            <p className="text-[9px] font-black text-text-muted">KK</p>
                            <p className="text-[10px] font-black text-text-primary">{judgeScore.kerugian_konstitusional}</p>
                          </div>
                          <div>
                            <p className="text-[9px] font-black text-text-muted">SA</p>
                            <p className="text-[10px] font-black text-text-primary">{judgeScore.substansi_argumen}</p>
                          </div>
                          <div>
                            <p className="text-[9px] font-black text-text-muted">KP</p>
                            <p className="text-[10px] font-black text-text-primary">{judgeScore.konsistensi_putusan}</p>
                          </div>
                          <div>
                            <p className="text-[9px] font-black text-text-muted">KF</p>
                            <p className="text-[10px] font-black text-text-primary">{judgeScore.kelengkapan_formil}</p>
                          </div>
                        </div>
                        {judgeScore.catatan && (
                          <p className="text-[10px] text-text-secondary italic leading-relaxed line-clamp-4">
                            "{judgeScore.catatan}"
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {selectedLegalReference && (
        <LegalReferenceDialog
          reference={selectedLegalReference}
          onClose={() => setSelectedLegalReference(null)}
        />
      )}
    </div>
  );
};

type LegalReferencePanelProps = {
  references: LegalReference[];
  queries: string[];
  warnings: string[];
  error: string | null;
  loading: boolean;
  onOpenReference: (reference: LegalReference) => void;
};

function LegalReferencePanel({
  references,
  queries,
  warnings,
  error,
  loading,
  onOpenReference,
}: LegalReferencePanelProps) {
  if (loading && references.length === 0) {
    return (
      <div className="space-y-3">
        {[0, 1, 2, 3].map((idx) => (
          <div key={idx} className="rounded-xl border border-border bg-white p-3 shadow-sm">
            <div className="mb-3 h-2 w-24 rounded-full bg-slate-100" />
            <div className="space-y-2">
              <div className="h-2 rounded-full bg-slate-100" />
              <div className="h-2 w-5/6 rounded-full bg-slate-100" />
              <div className="h-2 w-2/3 rounded-full bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {queries.length > 0 && (
        <div className="rounded-xl border border-primary/10 bg-primary/[0.03] p-3">
          <p className="mb-2 text-[9px] font-black uppercase tracking-widest text-primary">Query Pasal.id</p>
          <div className="space-y-1.5">
            {queries.slice(0, 3).map((query, idx) => (
              <p key={`${query}-${idx}`} className="line-clamp-2 text-[10px] font-bold leading-snug text-text-secondary">
                {query}
              </p>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-100 bg-red-50 p-3 text-[10px] font-bold leading-relaxed text-pemerintah">
          {error}
        </div>
      )}

      {warnings.slice(0, 2).map((warning, idx) => (
        <div key={`${warning}-${idx}`} className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] font-bold leading-relaxed text-amber-800">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{warning}</span>
        </div>
      ))}

      {references.length === 0 && !error && !loading && (
        <div className="flex flex-col items-center justify-center py-10 text-center space-y-2">
          <BookOpen className="w-8 h-8 text-text-muted opacity-15" />
          <p className="text-[10px] text-text-muted italic">Belum ada referensi Pasal.id yang cocok.</p>
        </div>
      )}

      {references.map((reference, idx) => {
        const score = typeof reference.score === 'number' ? reference.score : null;
        const scoreLabel = score === null
          ? ''
          : score <= 1
            ? `${Math.round(score * 100)}%`
            : score.toFixed(2);
        return (
          <button
            key={`${reference.title}-${idx}`}
            type="button"
            onClick={() => onOpenReference(reference)}
            className="block w-full text-left"
            title="Lihat isi referensi"
          >
          <div className="rounded-xl border border-border bg-white p-3 shadow-sm transition-all hover:border-primary/30 hover:bg-primary/[0.02] focus-within:border-primary/30">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="line-clamp-2 text-xs font-black leading-snug text-primary">
                  {reference.title}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {reference.matching_pasals && (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-slate-600">
                      {reference.matching_pasals}
                    </span>
                  )}
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-emerald-700">
                    {reference.source || 'Pasal.id'}
                  </span>
                  {scoreLabel && (
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-blue-700">
                      {scoreLabel}
                    </span>
                  )}
                </div>
              </div>
              {reference.url ? <ExternalLink className="h-3.5 w-3.5 shrink-0 text-text-muted" /> : <BookOpen className="h-3.5 w-3.5 shrink-0 text-text-muted" />}
            </div>
            {reference.snippet && (
              <p className="line-clamp-4 text-[10px] font-medium leading-relaxed text-text-secondary">
                {reference.snippet}
              </p>
            )}
          </div>
          </button>
        );
      })}
    </div>
  );
}

type LegalReferenceDialogProps = {
  reference: LegalReference;
  onClose: () => void;
};

function LegalReferenceDialog({ reference, onClose }: LegalReferenceDialogProps) {
  const bodyText = (reference.content || reference.full_content || reference.snippet || '').trim();
  const sourceHref = reference.url || reference.source_url || reference.source_pdf_url || '';

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="legal-reference-title"
      onClick={onClose}
    >
      <div
        className="flex h-[min(82vh,760px)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border bg-bg-primary px-5 py-4">
          <div className="min-w-0">
            <p className="mb-1 text-[10px] font-black uppercase tracking-widest text-primary">Isi Referensi Pasal.id</p>
            <h3 id="legal-reference-title" className="line-clamp-2 text-sm font-black leading-snug text-text-primary">
              {reference.title}
            </h3>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {reference.matching_pasals && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-slate-600">
                  {reference.matching_pasals}
                </span>
              )}
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-emerald-700">
                {reference.source || 'Pasal.id'}
              </span>
              {reference.query && (
                <span className="max-w-full truncate rounded-full bg-primary/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-wider text-primary">
                  {reference.query}
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {sourceHref && (
              <a
                href={sourceHref}
                target="_blank"
                rel="noreferrer"
                className="w-9 h-9 rounded-lg border border-border text-text-muted hover:text-primary hover:bg-white transition-all flex items-center justify-center"
                title="Buka sumber Pasal.id"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="w-9 h-9 rounded-lg border border-border text-text-muted hover:text-pemerintah hover:bg-white transition-all flex items-center justify-center"
              title="Tutup referensi"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-slate-100 p-5">
          <div className="min-h-full rounded-xl border border-border bg-white p-6 shadow-sm">
            {reference.relevant_content && reference.full_content && reference.relevant_content !== reference.full_content && (
              <div className="mb-5 rounded-lg border border-primary/20 bg-primary/[0.03] p-4">
                <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-primary">Bagian Relevan</p>
                <p className="whitespace-pre-wrap text-sm leading-7 text-slate-900">
                  {reference.relevant_content}
                </p>
              </div>
            )}
            {reference.content_truncated && (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-bold text-amber-800">
                Naskah lengkap terlalu panjang untuk ditampilkan seluruhnya di modal. Gunakan tautan sumber untuk membaca dokumen penuh.
              </div>
            )}
            {reference.content_error && (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-bold text-amber-800">
                Detail Pasal.id belum bisa dimuat: {reference.content_error}
              </div>
            )}
            {bodyText ? (
              <p className="whitespace-pre-wrap text-sm leading-7 text-slate-900">
                {bodyText}
              </p>
            ) : (
              <div className="flex min-h-64 flex-col items-center justify-center text-center">
                <BookOpen className="mb-3 h-10 w-10 text-text-muted opacity-25" />
                <p className="text-xs font-bold text-text-muted">Pasal.id belum mengirim isi lengkap untuk referensi ini.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

type HumanTurnComposerProps = {
  turn: HumanTurnState;
  value: string;
  error: string | null;
  isSubmitting: boolean;
  onChange: (value: string) => void;
  onSelectSuggestion: (value: string) => void;
  onSubmit: () => void;
};

function HumanTurnComposer({
  turn,
  value,
  error,
  isSubmitting,
  onChange,
  onSelectSuggestion,
  onSubmit,
}: HumanTurnComposerProps) {
  const canSubmit = value.trim().length > 0 && !isSubmitting;

  return (
    <div className="border-t border-amber-200 bg-amber-50/85 px-5 py-4 shadow-[0_-14px_30px_rgba(180,124,24,0.10)]">
      <div className="mx-auto max-w-5xl space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-amber-300 bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-amber-800">
                Giliran Anda sebagai Pemohon
              </span>
              <span className="text-[11px] font-bold text-amber-900/70">
                {turn.agent_name || 'Kuasa Hukum Pemohon'}
              </span>
              {turn.is_generating_suggestions && (
                <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-amber-700">
                  <Sparkles className="h-3 w-3" />
                  Menyiapkan opsi
                </span>
              )}
            </div>
            {turn.prompt && (
              <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-700">
                {turn.prompt}
              </p>
            )}
          </div>
        </div>

        {(turn.suggestions.length > 0 || turn.is_generating_suggestions) && (
          <div className="grid gap-2 lg:grid-cols-3">
            {turn.suggestions.slice(0, 3).map((suggestion, idx) => (
              <button
                key={`${turn.turn_id || turn.requested_at || 'turn'}-${idx}`}
                type="button"
                onClick={() => onSelectSuggestion(suggestion)}
                className="min-h-20 rounded-xl border border-amber-200 bg-white px-3 py-2 text-left text-xs font-semibold leading-relaxed text-slate-800 shadow-sm transition-all hover:border-amber-400 hover:bg-amber-50"
                title={`Pilih opsi ${idx + 1}`}
              >
                <span className="mb-1 block text-[9px] font-black uppercase tracking-widest text-amber-700">
                  Opsi {idx + 1}
                </span>
                {suggestion}
              </button>
            ))}
            {turn.is_generating_suggestions && turn.suggestions.length === 0 && [0, 1, 2].map((idx) => (
              <div key={idx} className="min-h-20 rounded-xl border border-amber-200 bg-white px-3 py-3 shadow-sm">
                <div className="mb-3 h-2 w-16 rounded-full bg-amber-100" />
                <div className="space-y-2">
                  <div className="h-2 rounded-full bg-slate-100" />
                  <div className="h-2 w-4/5 rounded-full bg-slate-100" />
                  <div className="h-2 w-2/3 rounded-full bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-3">
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                onSubmit();
              }
            }}
            rows={3}
            placeholder="Tulis jawaban Pemohon..."
            className="min-h-24 flex-1 resize-none rounded-xl border border-amber-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-950 outline-none transition-all placeholder:text-slate-400 focus:border-amber-500 focus:ring-4 focus:ring-amber-100"
          />
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="h-12 w-12 shrink-0 rounded-xl bg-primary text-white shadow-lg shadow-primary/20 transition-all hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-45"
            title="Kirim jawaban Pemohon"
          >
            {isSubmitting ? (
              <Loader2 className="mx-auto h-5 w-5 animate-spin" />
            ) : (
              <SendHorizontal className="mx-auto h-5 w-5" />
            )}
          </button>
        </div>
        {error && (
          <p className="text-xs font-bold text-pemerintah">{error}</p>
        )}
      </div>
    </div>
  );
}

export default SimulationPage;
