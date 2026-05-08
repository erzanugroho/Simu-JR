import { useState, useCallback, useEffect } from 'react';
import type {
    LlmConfig,
    HealthStatus,
    HistoryEntry,
    Project,
    ProjectFile,
    ResearchFinding,
    AuditResult,
    PermohonanCorpusStatus,
    PermohonanDraftPayload,
    PermohonanDraftRecord,
} from '../types';
import { JUDGE_PERSONA_OPTIONS } from '../types';
import { consumeSSEStream } from '../utils/sseParser';

const API_BASE = '';

export function useHealthCheck(defaultUrl?: string) {
    const [health, setHealth] = useState<HealthStatus | null>(null);
    const [loading, setLoading] = useState(true);

    const check = useCallback(async (url?: string) => {
        try {
            const checkUrl = url ?? defaultUrl;
            const res = await fetch(`${API_BASE}/api/health${checkUrl ? `?url=${encodeURIComponent(checkUrl)}` : ''}`);
            const data = await res.json();
            setHealth(data);
            return data;
        } catch (e) {
            setHealth({
                status: 'error',
                rag: 'error',
                rag_vectors: 0,
                intelligence_banks: {},
                rag_data: { status: 'missing', manifest_path: '', data_version: null, built_at: null },
                llm: 'error',
                llm_url: '',
            });
            return null;
        } finally {
            setLoading(false);
        }
    }, [defaultUrl]);

    useEffect(() => {
        check(defaultUrl);
        const interval = setInterval(() => check(defaultUrl), 30000);
        return () => clearInterval(interval);
    }, [check, defaultUrl]);

    return { health, loading, check };
}

import { useSimulationContext } from '../context/SimulationContext';

export function useSimulation() {
    const context = useSimulationContext();
    return {
        ...context
    };
}

export function useDraftImprovement() {
    const [isImproving, setIsImproving] = useState(false);
    const [improvedDraft, setImprovedDraft] = useState('');
    const [error, setError] = useState<string | null>(null);

    const improveDraft = useCallback(async (
        draft: string,
        notes: string,
        llmConfig: LlmConfig,
        onChunk?: (chunk: string) => void
    ) => {
        setIsImproving(true);
        setError(null);
        setImprovedDraft('');

        try {
            const response = await fetch(`${API_BASE}/api/improve-draft-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ draft, notes, llm_config: llmConfig }),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            let fullDraft = '';

            await consumeSSEStream(response, ({ type, data }) => {
                if (type === 'draft_chunk') {
                    fullDraft += data.chunk;
                    onChunk?.(data.chunk);
                } else if (type === 'draft_final') {
                    fullDraft = data.draft;
                    setImprovedDraft(data.draft);
                }
            });

            setImprovedDraft(fullDraft);
            return fullDraft;
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Gagal meningkatkan draf');
            return '';
        } finally {
            setIsImproving(false);
        }
    }, []);

    return { isImproving, improvedDraft, error, improveDraft };
}

export function useFileUpload() {
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState<string | null>(null);

    const uploadFile = useCallback(async (file: File): Promise<string | null> => {
        setUploading(true);
        setUploadError(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${API_BASE}/api/extract-text`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Gagal ekstraksi');
            }

            const data = await response.json();
            return data.text || null;
        } catch (e: unknown) {
            setUploadError(e instanceof Error ? e.message : 'Gagal upload');
            return null;
        } finally {
            setUploading(false);
        }
    }, []);

    return { uploading, uploadError, uploadFile };
}

export function usePermohonanCorpus() {
    const [status, setStatus] = useState<PermohonanCorpusStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [reindexing, setReindexing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/permohonan-corpus/status`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setStatus(data);
            setError(null);
            return data as PermohonanCorpusStatus;
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Gagal memuat status korpus');
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    const reindex = useCallback(async () => {
        setReindexing(true);
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/api/permohonan-corpus/reindex`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setStatus(data);
            return data as PermohonanCorpusStatus;
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Gagal memulai re-index');
            return null;
        } finally {
            setReindexing(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 8000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    return { status, loading, reindexing, error, fetchStatus, reindex };
}

export function usePermohonanDrafts(projectId: string) {
    const [drafts, setDrafts] = useState<PermohonanDraftRecord[]>([]);
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [draftText, setDraftText] = useState('');
    const [streamStatus, setStreamStatus] = useState('');
    const [warnings, setWarnings] = useState<string[]>([]);
    const [sourceStatus, setSourceStatus] = useState<Record<string, boolean>>({});
    const [savedDraft, setSavedDraft] = useState<PermohonanDraftRecord | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchDrafts = useCallback(async () => {
        if (!projectId) return;
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/permohonan-drafts`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setDrafts(Array.isArray(data.drafts) ? data.drafts : []);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Gagal memuat draft permohonan');
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    const generateDraft = useCallback(async (payload: PermohonanDraftPayload): Promise<string> => {
        if (!projectId || generating) return '';
        setGenerating(true);
        setDraftText('');
        setStreamStatus('');
        setWarnings([]);
        setSourceStatus({});
        setSavedDraft(null);
        setError(null);

        try {
            const response = await fetch(`${API_BASE}/api/projects/${projectId}/permohonan-drafts/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            let finalText = '';
            await consumeSSEStream(response, ({ type, data }) => {
                if (type === 'status') {
                    setStreamStatus(data.message || data.phase || '');
                } else if (type === 'warning') {
                    setWarnings(prev => [...prev, data.message || 'Peringatan tidak dikenal']);
                } else if (type === 'sources') {
                    setSourceStatus(data || {});
                } else if (type === 'draft_chunk') {
                    finalText += data.chunk || '';
                    setDraftText(prev => prev + (data.chunk || ''));
                } else if (type === 'draft_final') {
                    finalText = data.draft || finalText;
                    setDraftText(finalText);
                } else if (type === 'draft_saved') {
                    setSavedDraft(data as PermohonanDraftRecord);
                } else if (type === 'error') {
                    setError(data.message || 'Gagal membuat draft');
                }
            });

            await fetchDrafts();
            return finalText;
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Gagal membuat draft');
            return '';
        } finally {
            setGenerating(false);
        }
    }, [fetchDrafts, generating, projectId]);

    useEffect(() => {
        fetchDrafts();
    }, [fetchDrafts]);

    return {
        drafts,
        loading,
        generating,
        draftText,
        streamStatus,
        warnings,
        sourceStatus,
        savedDraft,
        error,
        setDraftText,
        fetchDrafts,
        generateDraft,
    };
}

export function useHistory() {
    const [history, setHistory] = useState<HistoryEntry[]>([]);

    const loadHistory = useCallback(() => {
        try {
            const saved = localStorage.getItem('simulasiMK_history');
            if (saved) {
                setHistory(JSON.parse(saved));
            }
        } catch (e) {
            console.error('Failed to load history:', e);
        }
    }, []);

    const saveToHistory = useCallback((entry: HistoryEntry) => {
        setHistory(prev => {
            const index = prev.findIndex(h => h.id === entry.id);
            const updated = index >= 0
                ? prev.map((h, i) => i === index ? entry : h)
                : [...prev, entry];
            const trimmed = updated.slice(-20);
            localStorage.setItem('simulasiMK_history', JSON.stringify(trimmed));
            return trimmed;
        });
    }, []);

    const deleteHistory = useCallback((id: string) => {
        setHistory(prev => {
            const updated = prev.filter(h => h.id !== id);
            localStorage.setItem('simulasiMK_history', JSON.stringify(updated));
            return updated;
        });
    }, []);

    useEffect(() => {
        loadHistory();
    }, [loadHistory]);

    return { history, loadHistory, saveToHistory, deleteHistory };
}

export function useSettings() {
    const [settings, setSettings] = useState({
        provider: 'local',
        apiKey: '',
        model: '',
        customModelId: '',
        llmUrl: 'http://127.0.0.1:1234/v1',
        hakimCount: 3,
        judgePersonas: [...JUDGE_PERSONA_OPTIONS, ...JUDGE_PERSONA_OPTIONS, ...JUDGE_PERSONA_OPTIONS] as string[],
        simMode: 'ai',
        hearingMode: 'pemeriksaan_pendahuluan'
    });

    useEffect(() => {
        try {
            const saved = localStorage.getItem('simulasiMK_settings');
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed && typeof parsed === 'object') {
                    setSettings(prev => ({ ...prev, ...parsed }));
                }
            }
        } catch (e) {
            console.error("Failed to load settings:", e);
        }
    }, []);

    const saveSettings = useCallback((newSettings: typeof settings) => {
        setSettings(newSettings);
        localStorage.setItem('simulasiMK_settings', JSON.stringify(newSettings));
    }, []);

    return { settings, saveSettings };
}

// ─── Project Hooks ─────────────────────────────────────────────

export function useProjects() {
    const [projects, setProjects] = useState<Project[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);

    const fetchProjects = useCallback(async () => {
        try {
            setLoading(true);
            const res = await fetch(`${API_BASE}/api/projects`);
            const data = await res.json();
            setProjects(data.projects || []);
            setTotal(data.total || 0);
        } catch (e) {
            console.error('Failed to fetch projects:', e);
        } finally {
            setLoading(false);
        }
    }, []);

    const createProject = useCallback(async (name: string, description?: string): Promise<Project | null> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Gagal membuat project');
            }
            const project = await res.json();
            setProjects(prev => [project, ...prev]);
            setTotal(prev => prev + 1);
            return project;
        } catch (e: unknown) {
            console.error('Failed to create project:', e);
            return null;
        }
    }, []);

    const deleteProject = useCallback(async (id: string): Promise<boolean> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${id}`, { method: 'DELETE' });
            if (!res.ok) return false;
            setProjects(prev => prev.filter(p => p.id !== id));
            setTotal(prev => prev - 1);
            return true;
        } catch (e) {
            console.error('Failed to delete project:', e);
            return false;
        }
    }, []);

    const updateProject = useCallback(async (id: string, data: { name?: string; description?: string }): Promise<Project | null> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) return null;
            const updated = await res.json();
            setProjects(prev => prev.map(p => p.id === id ? { ...p, ...updated } : p));
            return updated;
        } catch (e) {
            console.error('Failed to update project:', e);
            return null;
        }
    }, []);

    useEffect(() => {
        fetchProjects();
    }, [fetchProjects]);

    return { projects, total, loading, fetchProjects, createProject, deleteProject, updateProject };
}

export function useProject(projectId: string) {
    const [project, setProject] = useState<Project | null>(null);
    const [loading, setLoading] = useState(false);

    const fetchProject = useCallback(async () => {
        if (!projectId) { setProject(null); return; }
        try {
            setLoading(true);
            const res = await fetch(`${API_BASE}/api/projects/${projectId}`);
            if (!res.ok) return setProject(null);
            setProject(await res.json());
        } catch (e) {
            console.error('Failed to fetch project:', e);
            setProject(null);
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    const updateProject = useCallback(async (data: { name?: string; description?: string }): Promise<Project | null> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) return null;
            const updated = await res.json();
            setProject(updated);
            return updated;
        } catch (e) {
            console.error('Failed to update project:', e);
            return null;
        }
    }, [projectId]);

    useEffect(() => {
        fetchProject();
    }, [fetchProject]);

    return { project, loading, fetchProject, updateProject };
}

export function useProjectFiles(projectId: string) {
    const [files, setFiles] = useState<ProjectFile[]>([]);
    const [uploading, setUploading] = useState(false);

    const fetchFiles = useCallback(async () => {
        if (!projectId) { setFiles([]); return; }
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/files`);
            const data = await res.json();
            setFiles(data.files || []);
        } catch (e) {
            console.error('Failed to fetch files:', e);
        }
    }, [projectId]);

    const uploadFile = useCallback(async (file: File): Promise<boolean> => {
        setUploading(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/files`, {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) return false;
            await fetchFiles();
            return true;
        } catch (e) {
            return false;
        } finally {
            setUploading(false);
        }
    }, [projectId, fetchFiles]);

    const deleteFile = useCallback(async (fileId: string): Promise<boolean> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/files/${fileId}`, { method: 'DELETE' });
            if (!res.ok) return false;
            setFiles(prev => prev.filter(f => f.id !== fileId));
            return true;
        } catch (e) {
            return false;
        }
    }, [projectId]);

    const getFileContent = useCallback(async (fileId: string): Promise<string | null> => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/files/${fileId}/content`);
            if (!res.ok) return null;
            const data = await res.json();
            return data.text;
        } catch (e) {
            return null;
        }
    }, [projectId]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    return { files, uploading, fetchFiles, uploadFile, deleteFile, getFileContent };
}

export function useProjectSimulations(projectId: string) {
    const [simulations, setSimulations] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchSimulations = useCallback(async () => {
        try {
            setLoading(true);
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/simulations`);
            const data = await res.json();
            setSimulations(data.simulations || []);
        } catch (e) {
            console.error('Failed to fetch project simulations:', e);
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchSimulations();
    }, [fetchSimulations]);

    return { simulations, loading, fetchSimulations };
}

export function useProjectResearch(projectId: string) {
    const [findings, setFindings] = useState<ResearchFinding[]>([]);
    const [querying, setQuerying] = useState(false);
    const [streamingText, setStreamingText] = useState('');
    const [externalError, setExternalError] = useState<string | null>(null);

    const fetchResearch = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/research`);
            const data = await res.json();
            setFindings(data.research || []);
        } catch (e) {
            console.error('Failed to fetch research:', e);
        }
    }, [projectId]);

    const runResearch = useCallback(async (query: string, llmConfig?: LlmConfig): Promise<ResearchFinding | null> => {
        setQuerying(true);
        setStreamingText('');
        setExternalError(null);
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/research`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, llm_config: llmConfig }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${res.status}`);
            }

            let fullAnswer = '';
            let savedResult: any = null;

            await consumeSSEStream(res, ({ type, data }) => {
                if (type === 'research_chunk') {
                    fullAnswer += data.chunk;
                    setStreamingText(fullAnswer);
                } else if (type === 'research_saved') {
                    savedResult = data;
                } else if (type === 'pasal_id_error') {
                    setExternalError(data.error || 'Gagal mengambil data dari pasal.id');
                }
            });

            if (savedResult) {
                setFindings(prev => [savedResult, ...prev]);
                setStreamingText('');
                return savedResult;
            } else if (fullAnswer) {
                const fallback = { id: Date.now().toString(), query, answer: fullAnswer, timestamp: new Date().toISOString() } as ResearchFinding;
                setFindings(prev => [fallback, ...prev]);
                setStreamingText('');
                return fallback;
            }
            setStreamingText('');
            return null;
        } catch (e: unknown) {
            console.error('Research error:', e);
            setStreamingText('');
            return null;
        } finally {
            setQuerying(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchResearch();
    }, [fetchResearch]);

    return { findings, querying, streamingText, externalError, fetchResearch, runResearch };
}

export function useProjectAudit(projectId: string) {
    const [audits, setAudits] = useState<AuditResult[]>([]);
    const [running, setRunning] = useState(false);

    const fetchAudits = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/audit`);
            const data = await res.json();
            setAudits(data.audits || []);
        } catch (e) {
            console.error('Failed to fetch audits:', e);
        }
    }, [projectId]);

    const runAudit = useCallback(async (draft: string, llmConfig?: LlmConfig): Promise<AuditResult | null> => {
        setRunning(true);
        try {
            const res = await fetch(`${API_BASE}/api/projects/${projectId}/audit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ draft, llm_config: llmConfig }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Gagal menjalankan audit');
            }
            const result = await res.json();
            setAudits(prev => [result, ...prev]);
            return result;
        } catch (e: unknown) {
            console.error('Audit error:', e);
            return null;
        } finally {
            setRunning(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchAudits();
    }, [fetchAudits]);

    return { audits, running, fetchAudits, runAudit };
}
