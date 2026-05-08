export interface LlmConfig {
    provider: string;
    api_key: string;
    base_url: string;
    model_name: string;
    openrouter_provider?: Record<string, unknown> | null;
}

export interface SimulationMetadata {
    started_at?: string;
    ended_at?: string;
    duration_seconds?: number;
    hearing_mode?: string;
    turn_count?: number;
    target_turn_range?: number[];
    stop_reason?: string;
    llm_provider?: string;
    llm_model?: string;
    llm_base_url?: string;
}

export interface TranscriptEntry {
    speaker: string;
    role: string;
    content: string;
    round: string;
    timestamp?: string;
}

export interface HumanTurnState {
    prompt: string;
    agent_name: string;
    suggestions: string[];
    is_generating_suggestions?: boolean;
    requested_at?: number;
    turn_id?: string;
}

export interface ScoreBreakdown {
    legal_standing: number;
    kerugian_konstitusional: number;
    substansi_argumen: number;
    konsistensi_putusan: number;
    kelengkapan_formil: number;
}

export interface IndividualScore {
    legal_standing: number;
    kerugian_konstitusional: number;
    substansi_argumen: number;
    konsistensi_putusan: number;
    kelengkapan_formil: number;
    total: number;
    amar: string;
    catatan: string;
}

export interface DissentingOpinion {
    hakim: string;
    type: string;
    amar_hakim: string;
    amar_mayoritas: string;
    opinion: string;
}

export interface Scores {
    total: number;
    breakdown: ScoreBreakdown;
    amar: string;
    voting_detail: Record<string, number>;
    catatan_hakim: string[];
    individual: Record<string, IndividualScore> | IndividualScore[];
    feedback: Record<string, unknown> | null;
    dissenting_opinions: DissentingOpinion[];
}

export interface SimulationState {
    draft: string;
    hakimCount: number;
    transcript: TranscriptEntry[];
    chatMessages: { role: string; content: string }[];
    scores: Scores | null;
    isFinished: boolean;
    progressData: ProgressData | null;
    metadata?: SimulationMetadata | null;
}

export interface ProgressData {
    phase: string;
    message: string;
    status?: string;
    step?: string;
    stages?: { id: string; label: string; status: 'pending' | 'active' | 'done' }[];
}


export interface HealthStatus {
    status: string;
    rag: string;
    rag_vectors: number;
    intelligence_banks: Record<string, number>;
    rag_data?: {
        status: string;
        manifest_path: string;
        data_version?: string | null;
        built_at?: string | null;
        source_label?: string;
        collection_counts?: Record<string, number>;
        error?: string;
    };
    llm: string;
    llm_url: string;
}

export interface HistoryEntry {
    id: string;
    date: string;
    excerpt: string;
    state: SimulationState;
}

export interface Project {
    id: string;
    name: string;
    description: string;
    created_at: string;
    updated_at: string;
    simulation_count: number;
    file_count: number;
}

export interface ProjectFile {
    id: string;
    filename: string;
    stored_filename: string;
    size: number;
    mime_type: string;
    uploaded_at: string;
}

export interface ResearchFinding {
    id: string;
    query: string;
    answer: string;
    sources: string[];
    timestamp: string;
}

export interface AuditResult {
    id: string;
    consistent: boolean;
    issues: AuditIssue[];
    summary: string;
    posita_count?: number;
    petitum_count?: number;
    matched_count?: number;
    timestamp: string;
}

export interface AuditIssue {
    location: string;
    type: 'missing' | 'mismatch' | 'weak_argument' | 'unsupported_claim';
    description: string;
    suggestion?: string;
}

export type PermohonanCorpusStatusValue = 'not_started' | 'running' | 'ready' | 'failed' | 'stale';

export interface PermohonanCorpusStatus {
    status: PermohonanCorpusStatusValue;
    corpus_dir: string;
    total_files: number;
    processed_files?: number;
    extracted_files: number;
    failed_files: number;
    needs_ocr_files: number;
    ocr_enabled?: boolean;
    ocr_attempted_files?: number;
    ocr_success_files?: number;
    current_file?: string;
    last_ocr_status?: string;
    classification_counts: Record<string, number>;
    revision_pairs_count: number;
    last_indexed_at?: string | null;
    started_at?: string | null;
    last_error?: string;
    artifact_availability: Record<string, boolean>;
}

export type PermohonanDraftMode = 'new_draft' | 'improve_existing_draft';

export interface UploadedPermohonanDraft {
    filename: string;
    raw_text: string;
    extracted_sections?: Record<string, unknown>;
}

export interface PermohonanDraftPayload {
    mode: PermohonanDraftMode;
    user_input: Record<string, unknown>;
    uploaded_draft?: UploadedPermohonanDraft;
    llm_config?: LlmConfig;
}

export interface PermohonanDraftRecord {
    id: string;
    title: string;
    mode: PermohonanDraftMode;
    timestamp: string;
    user_input: Record<string, unknown>;
    uploaded_draft?: {
        filename?: string;
        text_chars?: number;
    };
    sources?: Record<string, unknown>;
    txt_filename: string;
    docx_filename: string;
    draft_excerpt: string;
    draft_chars: number;
}

export const JUDGE_PERSONA_OPTIONS = ['formalis', 'progresif', 'positivis'] as const;
export type JudgePersona = typeof JUDGE_PERSONA_OPTIONS[number];
