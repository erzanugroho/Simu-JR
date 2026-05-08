import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import type { LlmConfig, TranscriptEntry, Scores, ProgressData, SimulationMetadata, HumanTurnState } from '../types';
import { consumeSSEStream } from '../utils/sseParser';

interface SimulationOptions {
    draft?: string;
    jumlah_hakim?: number;
    mode?: string;
    hearing_mode?: string;
    target_turn_range?: number[];
    project_id?: string | null;
    llm_config?: LlmConfig;
    judge_personas?: string[];
    reconnect?: boolean;
}

interface SimulationContextValue {
    isRunning: boolean;
    transcript: TranscriptEntry[];
    scores: Scores | null;
    progress: ProgressData | null;
    error: string | null;
    currentSimulationId: string | null;
    currentProjectId: string | null;
    currentDraft: string;
    simulationMetadata: SimulationMetadata | null;
    humanTurn: HumanTurnState | null;
    setCurrentDraft: (draft: string) => void;
    startSimulation: (
        draft: string,
        jumlahHakim: number,
        llmConfig: LlmConfig,
        mode: string,
        simulationId: string,
        projectId?: string,
        judgePersonas?: string[],
        hearingMode?: string,
        targetTurnRange?: number[]
    ) => Promise<void>;
    stopSimulation: (simulationId?: string) => Promise<void>;
    syncSimulation: (simulationId: string) => Promise<void>;
    submitHumanInput: (text: string) => Promise<void>;
    clearHumanTurn: () => void;
    setTranscript: React.Dispatch<React.SetStateAction<TranscriptEntry[]>>;
    setScores: React.Dispatch<React.SetStateAction<Scores | null>>;
    setProgress: React.Dispatch<React.SetStateAction<ProgressData | null>>;
    setError: React.Dispatch<React.SetStateAction<string | null>>;
    setSimulationMetadata: React.Dispatch<React.SetStateAction<SimulationMetadata | null>>;
}

const SimulationContext = createContext<SimulationContextValue | undefined>(undefined);

const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value);

type StoredSimulationEvent = {
    type?: string;
    data?: unknown;
} & Record<string, unknown>;

const asNumber = (value: unknown, fallback = 0): number => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return fallback;
};

const normalizeScores = (raw: unknown): Partial<Scores> => {
    if (!isRecord(raw)) return {};

    const source = isRecord(raw.scores) ? raw.scores : raw;
    const scoreKeys = [
        'legal_standing',
        'kerugian_konstitusional',
        'substansi_argumen',
        'konsistensi_putusan',
        'kelengkapan_formil',
    ];
    const breakdown = isRecord(source.breakdown)
        ? source.breakdown
        : Object.fromEntries(scoreKeys.map((key) => [key, asNumber(source[key])]));
    const votingDetail = isRecord(source.voting_detail) ? source.voting_detail : {};

    return {
        total: asNumber(source.total),
        breakdown: breakdown as unknown as Scores['breakdown'],
        amar: typeof source.amar === 'string' ? source.amar : '',
        voting_detail: votingDetail as Record<string, number>,
        catatan_hakim: Array.isArray(source.catatan_hakim) ? source.catatan_hakim as string[] : [],
        individual: (raw.individual ?? raw.individual_scores ?? []) as Scores['individual'],
        feedback: isRecord(raw.feedback) ? raw.feedback : null,
        dissenting_opinions: Array.isArray(raw.dissenting_opinions) ? raw.dissenting_opinions as Scores['dissenting_opinions'] : [],
    };
};

const sanitizeLlmConfig = (llmConfig?: LlmConfig | null): SimulationMetadata => ({
    llm_provider: llmConfig?.provider || 'local',
    llm_model: llmConfig?.model_name || '',
    llm_base_url: llmConfig?.base_url || '',
});

const normalizeMetadata = (raw: unknown): SimulationMetadata | null => {
    if (!isRecord(raw)) return null;
    const metadata = isRecord(raw.metadata) ? raw.metadata : raw;
    const llmConfig = isRecord(raw.config) && isRecord(raw.config.llm_config)
        ? raw.config.llm_config
        : isRecord(raw.llm_config)
            ? raw.llm_config
            : null;

    return {
        started_at:
            typeof metadata.started_at === 'string'
                ? metadata.started_at
                : typeof metadata.started_at_iso === 'string'
                    ? metadata.started_at_iso
                    : undefined,
        ended_at: typeof metadata.ended_at === 'string' ? metadata.ended_at : undefined,
        duration_seconds: metadata.duration_seconds !== undefined ? asNumber(metadata.duration_seconds) : undefined,
        hearing_mode: typeof metadata.hearing_mode === 'string' ? metadata.hearing_mode : undefined,
        turn_count: metadata.turn_count !== undefined ? asNumber(metadata.turn_count) : undefined,
        target_turn_range: Array.isArray(metadata.target_turn_range)
            ? metadata.target_turn_range.map((item) => asNumber(item)).filter((item) => Number.isFinite(item))
            : undefined,
        stop_reason: typeof metadata.stop_reason === 'string' ? metadata.stop_reason : undefined,
        llm_provider:
            typeof metadata.llm_provider === 'string'
                ? metadata.llm_provider
                : typeof llmConfig?.provider === 'string'
                    ? llmConfig.provider
                    : undefined,
        llm_model:
            typeof metadata.llm_model === 'string'
                ? metadata.llm_model
                : typeof llmConfig?.model_name === 'string'
                    ? llmConfig.model_name
                    : undefined,
        llm_base_url:
            typeof metadata.llm_base_url === 'string'
                ? metadata.llm_base_url
                : typeof llmConfig?.base_url === 'string'
                    ? llmConfig.base_url
                    : undefined,
    };
};

export function SimulationProvider({ children }: { children: React.ReactNode }) {
    const [isRunning, setIsRunning] = useState(false);
    const [currentSimulationId, setCurrentSimulationId] = useState<string | null>(() => {
        return localStorage.getItem('simulasiMK_current_id');
    });
    const [currentProjectId, setCurrentProjectId] = useState<string | null>(() => {
        return localStorage.getItem('simulasiMK_current_project_id');
    });
    const [currentDraft, setCurrentDraftState] = useState<string>(() => {
        return localStorage.getItem('simulasiMK_current_draft') || '';
    });
    const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
    const [scores, setScores] = useState<Scores | null>(null);
    const [progress, setProgress] = useState<ProgressData | null>(null);
    const [humanTurn, setHumanTurn] = useState<HumanTurnState | null>(null);
    const [simulationMetadata, setSimulationMetadata] = useState<SimulationMetadata | null>(() => {
        try {
            const saved = localStorage.getItem('simulasiMK_current_metadata');
            return saved ? JSON.parse(saved) : null;
        } catch {
            return null;
        }
    });
    const [error, setError] = useState<string | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const isListeningRef = useRef<boolean>(false);

    const API_BASE = '';

    const setCurrentDraft = useCallback((draft: string) => {
        setCurrentDraftState(draft);
        if (draft) {
            localStorage.setItem('simulasiMK_current_draft', draft);
        } else {
            localStorage.removeItem('simulasiMK_current_draft');
        }
    }, []);

    const handleEvent = useCallback((
        type: string,
        data: Record<string, unknown>
    ) => {
        switch (type) {
            case 'transcript':
                setTranscript(prev => {
                    const entry = data as unknown as TranscriptEntry;
                    const exists = prev.some(e => 
                        (e.timestamp === entry.timestamp && e.content === entry.content) ||
                        ((e as unknown as Record<string, unknown>).id && (e as unknown as Record<string, unknown>).id === (data as Record<string, unknown>).id)
                    );
                    if (exists) return prev;
                    return [...prev, entry];
                });
                {
                    const entry = data as unknown as TranscriptEntry;
                    const identity = `${entry.speaker || ''} ${entry.role || ''}`.toLowerCase();
                    if (identity.includes('pemohon')) {
                        setHumanTurn(null);
                    }
                }
                break;
            case 'waiting_for_human':
                {
                    const suggestions = Array.isArray(data.suggestions)
                        ? data.suggestions.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
                        : [];
                    setHumanTurn(prev => ({
                        prompt: typeof data.prompt === 'string' ? data.prompt : prev?.prompt || '',
                        agent_name: typeof data.agent_name === 'string' ? data.agent_name : prev?.agent_name || 'Kuasa Hukum Pemohon',
                        suggestions,
                        is_generating_suggestions: Boolean(data.is_generating_suggestions),
                        requested_at: data.requested_at !== undefined ? asNumber(data.requested_at, Date.now()) : prev?.requested_at || Date.now(),
                        turn_id: typeof data.turn_id === 'string' ? data.turn_id : prev?.turn_id,
                    }));
                    setProgress(prev => ({
                        ...(prev || {}),
                        status: 'waiting_for_human',
                        message: 'Menunggu jawaban Pemohon',
                    } as ProgressData));
                }
                break;
            case 'scores':
                setScores((prev) => ({ ...prev, ...normalizeScores(data) } as Scores));
                break;
            case 'individual_scores':
                setScores((prev) => ({ ...prev, individual: (Array.isArray(data) ? data : []) as Scores['individual'] } as Scores));
                break;
            case 'dissenting_opinions':
                setScores((prev) => ({ ...prev, dissenting_opinions: (Array.isArray(data) ? data : []) as Scores['dissenting_opinions'] } as Scores));
                break;
            case 'feedback':
                setScores((prev) => ({ ...prev, feedback: isRecord(data) ? data : null } as Scores));
                break;
            case 'status':
                setProgress(data as unknown as ProgressData);
                {
                    const statusMetadata = normalizeMetadata(data);
                    if (statusMetadata) {
                        setSimulationMetadata(prev => {
                            const next = { ...(prev || {}), ...statusMetadata };
                            localStorage.setItem('simulasiMK_current_metadata', JSON.stringify(next));
                            return next;
                        });
                    }
                }
                break;
            case 'done':
                setIsRunning(false);
                isListeningRef.current = false;
                setHumanTurn(null);
                setProgress(prev => ({
                    ...(prev || {}),
                    status: 'done',
                    phase: 'done',
                    message: 'Simulasi selesai',
                    step: 'Hasil simulasi sudah tersedia.',
                } as ProgressData));
                setSimulationMetadata(prev => {
                    if (!prev?.started_at || prev.duration_seconds !== undefined) return prev;
                    const next = {
                        ...prev,
                        ended_at: new Date().toISOString(),
                        duration_seconds: Math.max(0, Math.round((Date.now() - new Date(prev.started_at).getTime()) / 1000)),
                    };
                    localStorage.setItem('simulasiMK_current_metadata', JSON.stringify(next));
                    return next;
                });
                break;
        }
    }, []);

    const connectToStream = useCallback(async (simulationId: string, options: SimulationOptions = {}) => {
        if (isListeningRef.current) return;
        isListeningRef.current = true;
        setIsRunning(true);

        abortControllerRef.current = new AbortController();

        try {
            // We use POST to reconnect as well, which triggers the catch-up mechanism in server.py
            const response = await fetch(`${API_BASE}/api/simulate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    simulation_id: simulationId,
                    ...options,
                    reconnect: true // Hint for server
                }),
                signal: abortControllerRef.current.signal,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            await consumeSSEStream(response, ({ type, data }) => {
                handleEvent(type, data as Record<string, unknown>);
            });
        } catch (e: unknown) {
            if (!(e instanceof Error) || e.name !== 'AbortError') {
                console.error('Stream connection failed:', e);
                setError(e instanceof Error ? e.message : 'Koneksi terputus');
            }
        } finally {
            setIsRunning(false);
            isListeningRef.current = false;
        }
    }, [handleEvent]);

    const syncSimulation = useCallback(async (simulationId: string) => {
        if (!simulationId) return;
        
        try {
            const res = await fetch(`${API_BASE}/api/simulations/${simulationId}/transcript`);
            if (res.ok) {
                const data = await res.json();
                
                // Map transcript from {type, data} to just data if needed
                if (data.transcript) {
                    const transcriptPayload: unknown = data.transcript;
                    const rawEvents: StoredSimulationEvent[] = Array.isArray(transcriptPayload)
                        ? transcriptPayload.filter(isRecord).map(item => item as StoredSimulationEvent)
                        : [];
                    const unwrapped = rawEvents.map((item): TranscriptEntry | null => {
                        const entry = item.type === 'transcript' && item.data ? item.data : item;
                        if (!isRecord(entry)) return null;
                        return entry.speaker || entry.content ? entry as unknown as TranscriptEntry : null;
                    }).filter((item): item is TranscriptEntry => item !== null); // Only keep actual messages
                    
                    setTranscript(unwrapped);

                    const lastWaitingIndex = rawEvents.map(event => event.type).lastIndexOf('waiting_for_human');
                    const lastPemohonIndex = rawEvents.findLastIndex((event) => {
                        const entry = event?.type === 'transcript' ? event.data : event;
                        if (!isRecord(entry)) return false;
                        const identity = `${entry.speaker || ''} ${entry.role || ''}`.toLowerCase();
                        return identity.includes('pemohon');
                    });
                    if (lastWaitingIndex >= 0 && lastWaitingIndex > lastPemohonIndex) {
                        const waitingData = isRecord(rawEvents[lastWaitingIndex]?.data)
                            ? rawEvents[lastWaitingIndex].data
                            : {};
                        setHumanTurn({
                            prompt: typeof waitingData.prompt === 'string' ? waitingData.prompt : '',
                            agent_name: typeof waitingData.agent_name === 'string' ? waitingData.agent_name : 'Kuasa Hukum Pemohon',
                            suggestions: Array.isArray(waitingData.suggestions)
                                ? waitingData.suggestions.filter((item: unknown): item is string => typeof item === 'string' && item.trim().length > 0)
                                : [],
                            is_generating_suggestions: Boolean(waitingData.is_generating_suggestions),
                            requested_at: asNumber(waitingData.requested_at, Date.now()),
                            turn_id: typeof waitingData.turn_id === 'string' ? waitingData.turn_id : undefined,
                        });
                    } else {
                        setHumanTurn(null);
                    }
                }
                
                if (data.results && (data.results.amar || data.results.scores)) {
                    setScores(normalizeScores(data.results) as Scores);
                    setSimulationMetadata(normalizeMetadata(data.results));
                } else if (data.transcript) {
                    // Fallback: extract scores from transcript events
                    const scoresEvent = data.transcript.find((e: { type: string }) => e.type === 'scores');
                    const individualEvent = data.transcript.find((e: { type: string }) => e.type === 'individual_scores');
                    const feedbackEvent = data.transcript.find((e: { type: string }) => e.type === 'feedback');
                    const dissentingEvent = data.transcript.find((e: { type: string }) => e.type === 'dissenting_opinions');
                    
                    if (scoresEvent?.data) {
                        setScores({
                            ...normalizeScores(scoresEvent.data),
                            individual: individualEvent?.data || [],
                            feedback: feedbackEvent?.data || null,
                            dissenting_opinions: dissentingEvent?.data || [],
                        } as Scores);
                    }
                }
                const hasResults = Boolean(data.results && (
                    data.results.amar ||
                    data.results.scores ||
                    data.results.total ||
                    data.results.feedback
                ));
                const serverDone = !data.is_running && (
                    hasResults ||
                    data.status?.phase === 'done' ||
                    data.status?.status === 'done' ||
                    data.status?.phase === 'Selesai'
                );

                if (serverDone) {
                    setIsRunning(false);
                    isListeningRef.current = false;
                    setProgress({
                        ...(data.status || {}),
                        status: 'done',
                        phase: 'done',
                        message: data.status?.message || 'Simulasi selesai',
                        step: data.status?.step || 'Hasil simulasi sudah tersedia.',
                    } as ProgressData);
                } else if (data.status) {
                    setProgress(data.status);
                } else if (!data.is_running) {
                    setIsRunning(false);
                    isListeningRef.current = false;
                }

                const syncedMetadata = normalizeMetadata({
                    ...(isRecord(data.results) ? data.results : {}),
                    ...(isRecord(data.config) ? data.config : {}),
                    config: data.config,
                    metadata: isRecord(data.results) && isRecord(data.results.metadata)
                        ? data.results.metadata
                        : data.config,
                });
                if (syncedMetadata) {
                    setSimulationMetadata(syncedMetadata);
                    localStorage.setItem('simulasiMK_current_metadata', JSON.stringify(syncedMetadata));
                }
                
                if (data.is_running) {
                    setIsRunning(true);
                    // Reconnect to stream if it's still running
                    // data.config contains the original settings from the server
                    connectToStream(simulationId, {
                        draft: data.config?.draft || currentDraft,
                        jumlah_hakim: data.config?.jumlah_hakim || 3,
                        mode: data.config?.mode || 'judicial_review',
                        project_id: data.config?.project_id || currentProjectId,
                        llm_config: data.config?.llm_config,
                        judge_personas: data.config?.judge_personas
                    });
                }

                if (currentSimulationId !== simulationId) {
                    setCurrentSimulationId(simulationId);
                    localStorage.setItem('simulasiMK_current_id', simulationId);
                }
                
                // If the server returned a project_id, sync it too
                if (data.config?.project_id && currentProjectId !== data.config.project_id) {
                    setCurrentProjectId(data.config.project_id);
                    localStorage.setItem('simulasiMK_current_project_id', data.config.project_id);
                }
            }
        } catch (err: unknown) {
            console.error('Failed to sync simulation:', err);
        }
    }, [currentSimulationId, currentDraft, currentProjectId, connectToStream]);

    // Auto-sync and reconnect on provider mount
    React.useEffect(() => {
        const discoverAndSync = async () => {
            const savedId = localStorage.getItem('simulasiMK_current_id');
            if (savedId && !isListeningRef.current) {
                syncSimulation(savedId);
                return;
            }

            // If no local ID, check server for active simulations
            if (!isListeningRef.current) {
                try {
                    const res = await fetch(`${API_BASE}/api/simulations/active`);
                    if (res.ok) {
                        const data = await res.json();
                        if (data.active_simulations && data.active_simulations.length > 0) {
                            // Pick the first active one if found
                            const activeId = data.active_simulations[0];
                            console.log('Discovered active simulation on server:', activeId);
                            syncSimulation(activeId);
                        }
                    }
                } catch {
                    // silent fail
                }
            }
        };

        discoverAndSync();
    }, [syncSimulation]);

    const startSimulation = useCallback(async (
        draft: string,
        jumlahHakim: number,
        llmConfig: LlmConfig,
        mode: string,
        simulationId: string,
        projectId?: string,
        judgePersonas?: string[],
        hearingMode?: string,
        targetTurnRange?: number[]
    ) => {
        setError(null);
        setTranscript([]);
        setScores(null);
        setProgress(null);
        setHumanTurn(null);
        const metadata: SimulationMetadata = {
            started_at: new Date().toISOString(),
            ...sanitizeLlmConfig(llmConfig),
        };
        setSimulationMetadata(metadata);
        setCurrentSimulationId(simulationId);
        localStorage.setItem('simulasiMK_current_id', simulationId);
        localStorage.setItem('simulasiMK_current_metadata', JSON.stringify(metadata));
        
        if (projectId) {
            setCurrentProjectId(projectId);
            localStorage.setItem('simulasiMK_current_project_id', projectId);
        }
        
        setCurrentDraftState(draft);
        localStorage.setItem('simulasiMK_current_draft', draft);

        // Initiate connection
        await connectToStream(simulationId, {
            draft,
            jumlah_hakim: jumlahHakim,
            llm_config: llmConfig,
            mode,
            hearing_mode: hearingMode,
            target_turn_range: targetTurnRange,
            project_id: projectId,
            judge_personas: judgePersonas,
        });
    }, [connectToStream]);

    const stopSimulation = useCallback(async (simulationId?: string) => {
        abortControllerRef.current?.abort();
        const idToStop = simulationId || currentSimulationId;
        try {
            await fetch(`${API_BASE}/api/stop${idToStop ? `/${idToStop}` : ''}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(idToStop ? { simulation_id: idToStop } : {}),
            });
        } catch {
            // ignore
        }
        setIsRunning(false);
        isListeningRef.current = false;
        setCurrentSimulationId(null);
        setCurrentProjectId(null);
        setCurrentDraftState('');
        localStorage.removeItem('simulasiMK_current_id');
        localStorage.removeItem('simulasiMK_current_project_id');
        localStorage.removeItem('simulasiMK_current_draft');
        localStorage.removeItem('simulasiMK_current_metadata');
        setSimulationMetadata(null);
        setHumanTurn(null);
    }, [currentSimulationId]);

    const submitHumanInput = useCallback(async (text: string) => {
        const cleanText = text.trim();
        if (!cleanText) {
            throw new Error('Input tidak boleh kosong');
        }

        const response = await fetch(`${API_BASE}/api/human_input`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: cleanText,
                simulation_id: currentSimulationId,
            }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${response.status}`);
        }

        setHumanTurn(null);
        setProgress(prev => ({
            ...(prev || {}),
            status: 'running',
            message: 'Jawaban Pemohon dikirim',
        } as ProgressData));
    }, [currentSimulationId]);

    const clearHumanTurn = useCallback(() => {
        setHumanTurn(null);
    }, []);

    return (
        <SimulationContext.Provider value={{
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
            clearHumanTurn,
            setTranscript,
            setScores,
            setProgress,
            setError,
            setSimulationMetadata
        }}>
            {children}
        </SimulationContext.Provider>
    );
}

export function useSimulationContext() {
    const context = useContext(SimulationContext);
    if (context === undefined) {
        throw new Error('useSimulationContext must be used within a SimulationProvider');
    }
    return context;
}
