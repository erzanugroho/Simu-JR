import React, { useMemo, useRef, useState } from 'react';
import {
    AlertTriangle,
    CheckCircle,
    Clock,
    Download,
    FileText,
    Loader2,
    RefreshCw,
    Send,
    Shield,
    Upload,
} from 'lucide-react';
import { useFileUpload, usePermohonanCorpus, usePermohonanDrafts, useSettings } from '../hooks/useApi';
import type { LlmConfig, PermohonanDraftMode, UploadedPermohonanDraft } from '../types';

interface PermohonanDraftTabProps {
    projectId: string;
}

type NewDraftForm = {
    jenis_pengujian: string;
    nama_pemohon: string;
    kategori_pemohon: string[];
    uu_diuji: string;
    pasal_diuji: string;
    batu_uji_uud: string;
    kerugian_konstitusional: string;
    kuasa_hukum: string;
    identitas_lengkap: string;
    kronologi: string;
    alasan_permohonan: string;
    target_petitum: string;
    model_draft: string;
    referensi_perkara: string;
    catatan_strategi: string;
};

type ImproveDraftForm = {
    tujuan_perbaikan: string[];
    jenis_pengujian: string;
    pasal_diuji: string;
    batu_uji_uud: string;
    kelemahan_draft: string;
    instruksi_tambahan: string;
    scope_rewrite: string;
};

const DEFAULT_NEW_FORM: NewDraftForm = {
    jenis_pengujian: 'uji materiil',
    nama_pemohon: '',
    kategori_pemohon: ['perorangan WNI'],
    uu_diuji: '',
    pasal_diuji: '',
    batu_uji_uud: '',
    kerugian_konstitusional: '',
    kuasa_hukum: '',
    identitas_lengkap: '',
    kronologi: '',
    alasan_permohonan: '',
    target_petitum: '',
    model_draft: 'standar',
    referensi_perkara: '',
    catatan_strategi: '',
};

const DEFAULT_IMPROVE_FORM: ImproveDraftForm = {
    tujuan_perbaikan: ['review menyeluruh'],
    jenis_pengujian: '',
    pasal_diuji: '',
    batu_uji_uud: '',
    kelemahan_draft: '',
    instruksi_tambahan: '',
    scope_rewrite: 'susun ulang total bila perlu',
};

const IMPROVEMENT_OPTIONS = [
    'rapikan format',
    'perkuat legal standing',
    'perjelas posita',
    'sinkronkan petitum',
    'ubah menjadi format MK yang lebih benar',
    'review menyeluruh',
];

const PEMOHON_CATEGORY_OPTIONS = [
    'perorangan WNI',
    'kelompok orang berkepentingan sama / para Pemohon',
    'serikat pekerja / serikat buruh',
    'badan hukum privat',
    'badan hukum publik',
    'masyarakat hukum adat',
    'lembaga negara',
    'lainnya',
];

const DEFAULT_MODELS: Record<string, string> = {
    local: 'local-model',
    deepseek: 'deepseek-v4-flash',
    mimo: 'mimo-v2-omni',
    openrouter: 'deepseek/deepseek-v4-flash',
    claude: 'claude-haiku-4-5',
};

const DEFAULT_BASE_URLS: Record<string, string> = {
    local: 'http://127.0.0.1:1234/v1',
    deepseek: 'https://api.deepseek.com',
    mimo: 'https://token-plan-sgp.xiaomimimo.com/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    claude: '',
};

const formatNumber = (value: number | undefined) => new Intl.NumberFormat('id-ID').format(value || 0);

const statusLabel = (status?: string) => {
    if (status === 'ready') return 'Siap';
    if (status === 'running') return 'Mengindeks';
    if (status === 'stale') return 'Perlu re-index';
    if (status === 'failed') return 'Gagal';
    return 'Belum diindeks';
};

const isFilled = (value: string | string[]) => Array.isArray(value) ? value.length > 0 : value.trim().length > 0;

function buildLlmConfig(settings: ReturnType<typeof useSettings>['settings']): LlmConfig {
    const provider = settings.provider || 'local';
    const model = settings.customModelId || settings.model || DEFAULT_MODELS[provider] || 'local-model';
    const baseUrl = provider === 'local'
        ? (settings.llmUrl || DEFAULT_BASE_URLS.local)
        : DEFAULT_BASE_URLS[provider] || settings.llmUrl || DEFAULT_BASE_URLS.local;
    return {
        provider,
        api_key: settings.apiKey || '',
        base_url: baseUrl,
        model_name: model,
    };
}

const PermohonanDraftTab: React.FC<PermohonanDraftTabProps> = ({ projectId }) => {
    const { settings } = useSettings();
    const { status, loading: corpusLoading, reindexing, error: corpusError, reindex } = usePermohonanCorpus();
    const {
        drafts,
        loading: draftsLoading,
        generating,
        draftText,
        streamStatus,
        warnings,
        sourceStatus,
        savedDraft,
        error,
        setDraftText,
        generateDraft,
    } = usePermohonanDrafts(projectId);
    const { uploading, uploadError, uploadFile } = useFileUpload();

    const [mode, setMode] = useState<PermohonanDraftMode>('new_draft');
    const [newForm, setNewForm] = useState<NewDraftForm>(DEFAULT_NEW_FORM);
    const [improveForm, setImproveForm] = useState<ImproveDraftForm>(DEFAULT_IMPROVE_FORM);
    const [uploadedDraft, setUploadedDraft] = useState<UploadedPermohonanDraft | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const llmConfig = useMemo(() => buildLlmConfig(settings), [settings]);

    const newDraftValid = (
        isFilled(newForm.jenis_pengujian) &&
        isFilled(newForm.nama_pemohon) &&
        isFilled(newForm.kategori_pemohon) &&
        isFilled(newForm.uu_diuji) &&
        isFilled(newForm.pasal_diuji) &&
        isFilled(newForm.batu_uji_uud) &&
        isFilled(newForm.kerugian_konstitusional)
    );
    const improveDraftValid = Boolean(uploadedDraft?.raw_text.trim()) && improveForm.tujuan_perbaikan.length > 0;
    const canSubmit = mode === 'new_draft' ? newDraftValid : improveDraftValid;

    const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;
        const text = await uploadFile(file);
        if (text) {
            setUploadedDraft({ filename: file.name, raw_text: text, extracted_sections: {} });
        }
        if (fileRef.current) fileRef.current.value = '';
    };

    const updateNewForm = (field: keyof NewDraftForm, value: string | string[]) => {
        setNewForm(prev => ({ ...prev, [field]: value }));
    };

    const updateImproveForm = (field: keyof ImproveDraftForm, value: string | string[]) => {
        setImproveForm(prev => ({ ...prev, [field]: value }));
    };

    const toggleImprovement = (option: string) => {
        setImproveForm(prev => {
            const exists = prev.tujuan_perbaikan.includes(option);
            return {
                ...prev,
                tujuan_perbaikan: exists
                    ? prev.tujuan_perbaikan.filter(item => item !== option)
                    : [...prev.tujuan_perbaikan, option],
            };
        });
    };

    const handleGenerate = async () => {
        if (!canSubmit || generating) return;
        if (mode === 'new_draft') {
            await generateDraft({
                mode,
                user_input: newForm,
                llm_config: llmConfig,
            });
        } else {
            await generateDraft({
                mode,
                user_input: improveForm,
                uploaded_draft: uploadedDraft || undefined,
                llm_config: llmConfig,
            });
        }
    };

    const classification = status?.classification_counts || {};
    const sourceItems: Array<[string, boolean | undefined]> = [
        ['RAG', sourceStatus.rag_used],
        ['Survive Bank', sourceStatus.survive_bank_used],
        ['Concern Bank', sourceStatus.concern_bank_used],
        ['Attack Bank', sourceStatus.attack_bank_used],
        ['Ratio Bank', sourceStatus.ratio_bank_used],
        ['Pasal.id', sourceStatus.pasal_id_used],
        ['PMK 2/2021', sourceStatus.pmk_2_2021_compliance_used],
    ];

    return (
        <div className="space-y-5 animate-slide-up">
            <div className="bg-white border border-border rounded-2xl shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-border flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <FileText className="w-5 h-5 text-primary" />
                            <h3 className="font-bold text-text-primary">Buat Dokumen Permohonan</h3>
                        </div>
                        <p className="text-xs text-text-muted mt-1">
                            Drafter memakai korpus lokal, PMK 2/2021, RAG, bank internal, dan Pasal.id bila tersedia.
                        </p>
                    </div>
                    <button
                        onClick={reindex}
                        disabled={reindexing || status?.status === 'running'}
                        className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50 hover:bg-primary-light transition-all"
                    >
                        {reindexing || status?.status === 'running'
                            ? <Loader2 className="w-4 h-4 animate-spin" />
                            : <RefreshCw className="w-4 h-4" />}
                        Re-index Korpus
                    </button>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-11 divide-x divide-y lg:divide-y-0 divide-border">
                    <StatusMetric label="Status" value={corpusLoading ? 'Memuat' : statusLabel(status?.status)} strong />
                    <StatusMetric label="PMK" value={status?.artifact_availability?.pmk_compliance ? 'Aktif' : '-'} strong={status?.artifact_availability?.pmk_compliance} />
                    <StatusMetric label="File" value={formatNumber(status?.total_files)} />
                    <StatusMetric label="Terekstrak" value={formatNumber(status?.extracted_files)} />
                    <StatusMetric label="Gagal" value={formatNumber(status?.failed_files)} warn={Boolean(status?.failed_files)} />
                    <StatusMetric label="Needs OCR" value={formatNumber(status?.needs_ocr_files)} warn={Boolean(status?.needs_ocr_files)} />
                    <StatusMetric label="OCR OK" value={formatNumber(status?.ocr_success_files)} />
                    <StatusMetric label="OCR Tried" value={formatNumber(status?.ocr_attempted_files)} />
                    <StatusMetric label="Awal" value={formatNumber(classification.permohonan_awal)} />
                    <StatusMetric label="Perbaikan" value={formatNumber(classification.perbaikan)} />
                    <StatusMetric label="Pairs" value={formatNumber(status?.revision_pairs_count)} />
                </div>

                {(corpusError || status?.last_error) && (
                    <div className="px-5 py-3 bg-red-50 border-t border-red-100 text-xs text-ditolak flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>{corpusError || status?.last_error}</span>
                    </div>
                )}
                {status?.status === 'running' && (
                    <div className="px-5 py-3 bg-blue-50 border-t border-blue-100 text-xs text-primary flex items-start gap-2">
                        <Loader2 className="w-4 h-4 shrink-0 mt-0.5 animate-spin" />
                        <span>
                            OCR/indexing berjalan: {formatNumber(status.processed_files)} / {formatNumber(status.total_files)} file.
                            {status.current_file ? ` File aktif: ${status.current_file}` : ''}
                        </span>
                    </div>
                )}
            </div>

            <div className="flex gap-1 bg-white rounded-xl p-1 border border-border w-fit">
                <ModeButton active={mode === 'new_draft'} onClick={() => setMode('new_draft')} label="Buat Draft Baru" />
                <ModeButton active={mode === 'improve_existing_draft'} onClick={() => setMode('improve_existing_draft')} label="Perbaiki Draft Lama" />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] gap-5">
                <div className="space-y-4">
                    {mode === 'new_draft' ? (
                        <NewDraftFormView form={newForm} onChange={updateNewForm} />
                    ) : (
                        <ImproveDraftFormView
                            form={improveForm}
                            uploadedDraft={uploadedDraft}
                            uploading={uploading}
                            uploadError={uploadError}
                            fileRef={fileRef}
                            onUpload={handleUpload}
                            onChange={updateImproveForm}
                            onToggleImprovement={toggleImprovement}
                        />
                    )}

                    <div className="bg-white border border-border rounded-2xl p-4 shadow-sm">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                            <div>
                                <div className="text-sm font-bold text-text-primary">Generate dokumen</div>
                                <div className="text-xs text-text-muted mt-1">
                                    Provider aktif: {llmConfig.provider} / {llmConfig.model_name}
                                </div>
                            </div>
                            <button
                                onClick={handleGenerate}
                                disabled={!canSubmit || generating}
                                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-bold disabled:opacity-50 hover:bg-primary-light transition-all"
                            >
                                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                {generating ? 'Menyusun...' : 'Buat Dokumen'}
                            </button>
                        </div>
                        {!canSubmit && (
                            <p className="text-xs text-text-muted mt-3">
                                Lengkapi field wajib agar drafter bisa menjaga struktur dan fakta dokumen.
                            </p>
                        )}
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="bg-white border border-border rounded-2xl shadow-sm overflow-hidden">
                        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                            <div>
                                <h3 className="font-bold text-text-primary">Editor Draft</h3>
                                <p className="text-xs text-text-muted mt-1">
                                    {streamStatus || (draftText ? 'Draft siap ditinjau' : 'Output akan muncul di sini')}
                                </p>
                            </div>
                            {savedDraft && (
                                <a
                                    href={`/api/projects/${projectId}/permohonan-drafts/${savedDraft.id}/docx`}
                                    className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-primary/10 text-primary text-xs font-bold hover:bg-primary hover:text-white transition-all"
                                >
                                    <Download className="w-4 h-4" />
                                    DOCX
                                </a>
                            )}
                        </div>

                        {warnings.length > 0 && (
                            <div className="px-5 py-3 bg-amber-50 border-b border-amber-100 space-y-1">
                                {warnings.map((warning, index) => (
                                    <div key={`${warning}-${index}`} className="flex items-start gap-2 text-xs text-amber-800">
                                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                                        <span>{warning}</span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {Object.keys(sourceStatus).length > 0 && (
                            <div className="px-5 py-3 border-b border-border flex flex-wrap gap-2">
                                {sourceItems.map(([label, active]) => (
                                    <span
                                        key={label}
                                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${active ? 'bg-emerald-50 text-dikabulkan' : 'bg-bg-secondary text-text-muted'}`}
                                    >
                                        {active ? <CheckCircle className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />}
                                        {label}
                                    </span>
                                ))}
                            </div>
                        )}

                        <textarea
                            value={draftText}
                            onChange={event => setDraftText(event.target.value)}
                            placeholder="Draft permohonan akan ditulis secara streaming..."
                            rows={24}
                            className="w-full p-5 min-h-[520px] resize-y text-sm leading-relaxed text-text-primary placeholder:text-text-muted bg-white outline-none font-mono"
                        />
                        {error && (
                            <div className="px-5 py-3 bg-red-50 border-t border-red-100 text-xs text-ditolak flex items-start gap-2">
                                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                                <span>{error}</span>
                            </div>
                        )}
                    </div>

                    <div className="bg-white border border-border rounded-2xl shadow-sm overflow-hidden">
                        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
                            <div>
                                <h3 className="font-bold text-text-primary">Riwayat Draft</h3>
                                <p className="text-xs text-text-muted mt-1">Draft tersimpan per project.</p>
                            </div>
                            {draftsLoading && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
                        </div>
                        {drafts.length === 0 ? (
                            <div className="p-8 text-sm text-text-muted text-center">Belum ada draft permohonan tersimpan.</div>
                        ) : (
                            <div className="divide-y divide-border">
                                {drafts.map(item => (
                                    <div key={item.id} className="p-4 flex items-center gap-3">
                                        <Shield className="w-5 h-5 text-primary shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm font-bold text-text-primary truncate">{item.title}</div>
                                            <div className="text-xs text-text-muted mt-0.5">
                                                {new Date(item.timestamp).toLocaleString('id-ID')} - {item.mode === 'new_draft' ? 'Draft baru' : 'Perbaikan'} - {formatNumber(item.draft_chars)} karakter
                                            </div>
                                        </div>
                                        <a
                                            href={`/api/projects/${projectId}/permohonan-drafts/${item.id}/docx`}
                                            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-bg-secondary text-text-secondary hover:bg-primary hover:text-white transition-all text-xs font-bold"
                                        >
                                            <Download className="w-3.5 h-3.5" />
                                            DOCX
                                        </a>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

function StatusMetric({ label, value, strong, warn }: { label: string; value: string; strong?: boolean; warn?: boolean }) {
    return (
        <div className="p-4 min-w-0">
            <div className="text-[10px] uppercase tracking-wide font-bold text-text-muted truncate">{label}</div>
            <div className={`mt-1 text-base font-black truncate ${warn ? 'text-ditolak' : strong ? 'text-primary' : 'text-text-primary'}`}>
                {value}
            </div>
        </div>
    );
}

function ModeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className={`px-4 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap ${active ? 'bg-primary text-white shadow-md' : 'text-text-muted hover:text-text-primary hover:bg-bg-primary'}`}
        >
            {label}
        </button>
    );
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
    return (
        <label className="block text-xs font-bold text-text-primary mb-1.5">
            {label} {required && <span className="text-ditolak">*</span>}
        </label>
    );
}

function TextField({
    label,
    value,
    onChange,
    required,
    placeholder,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
    placeholder?: string;
}) {
    return (
        <div>
            <FieldLabel label={label} required={required} />
            <input
                value={value}
                onChange={event => onChange(event.target.value)}
                placeholder={placeholder}
                className="w-full px-3 py-2.5 rounded-xl border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
        </div>
    );
}

function TextAreaField({
    label,
    value,
    onChange,
    required,
    placeholder,
    rows = 4,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
    placeholder?: string;
    rows?: number;
}) {
    return (
        <div>
            <FieldLabel label={label} required={required} />
            <textarea
                value={value}
                onChange={event => onChange(event.target.value)}
                placeholder={placeholder}
                rows={rows}
                className="w-full px-3 py-2.5 rounded-xl border border-border text-sm text-text-primary placeholder:text-text-muted resize-y focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            />
        </div>
    );
}

function SelectField({
    label,
    value,
    onChange,
    options,
    required,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    options: string[];
    required?: boolean;
}) {
    return (
        <div>
            <FieldLabel label={label} required={required} />
            <select
                value={value}
                onChange={event => onChange(event.target.value)}
                className="w-full px-3 py-2.5 rounded-xl border border-border bg-white text-sm text-text-primary focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
            >
                {options.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
        </div>
    );
}

function MultiChoiceField({
    label,
    values,
    options,
    onChange,
    required,
}: {
    label: string;
    values: string[];
    options: string[];
    onChange: (values: string[]) => void;
    required?: boolean;
}) {
    const toggle = (option: string) => {
        onChange(values.includes(option)
            ? values.filter(item => item !== option)
            : [...values, option]);
    };

    return (
        <div>
            <FieldLabel label={label} required={required} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {options.map(option => (
                    <label
                        key={option}
                        className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-sm transition-colors ${values.includes(option) ? 'border-primary bg-primary/5 text-primary' : 'border-border text-text-secondary hover:border-primary/40'}`}
                    >
                        <input
                            type="checkbox"
                            checked={values.includes(option)}
                            onChange={() => toggle(option)}
                            className="mt-0.5 accent-primary"
                        />
                        <span>{option}</span>
                    </label>
                ))}
            </div>
        </div>
    );
}

function NewDraftFormView({ form, onChange }: { form: NewDraftForm; onChange: (field: keyof NewDraftForm, value: string | string[]) => void }) {
    return (
        <div className="bg-white border border-border rounded-2xl p-5 shadow-sm space-y-4">
            <div>
                <h3 className="font-bold text-text-primary">Buat Draft Baru</h3>
                <p className="text-xs text-text-muted mt-1">Field bertanda bintang menjadi dasar minimum draft.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SelectField label="Jenis pengujian" value={form.jenis_pengujian} onChange={value => onChange('jenis_pengujian', value)} options={['uji materiil', 'uji formil', 'campuran']} required />
                <TextField label="Nama Pemohon" value={form.nama_pemohon} onChange={value => onChange('nama_pemohon', value)} required placeholder="Nama lengkap Pemohon" />
                <TextField label="Kuasa hukum" value={form.kuasa_hukum} onChange={value => onChange('kuasa_hukum', value)} placeholder="Opsional" />
                <TextField label="Undang-undang yang diuji" value={form.uu_diuji} onChange={value => onChange('uu_diuji', value)} required placeholder="Contoh: UU Nomor ... Tahun ..." />
                <TextField label="Pasal/ayat/bagian yang diuji" value={form.pasal_diuji} onChange={value => onChange('pasal_diuji', value)} required placeholder="Contoh: Pasal 1 angka 2, Pasal 5 ayat (1)" />
                <TextField label="Pasal UUD 1945 sebagai batu uji" value={form.batu_uji_uud} onChange={value => onChange('batu_uji_uud', value)} required placeholder="Contoh: Pasal 28D ayat (1) UUD 1945" />
                <SelectField label="Model draft" value={form.model_draft} onChange={value => onChange('model_draft', value)} options={['ringkas', 'standar', 'lengkap']} />
            </div>
            <MultiChoiceField
                label="Kategori Pemohon"
                values={form.kategori_pemohon}
                options={PEMOHON_CATEGORY_OPTIONS}
                onChange={value => onChange('kategori_pemohon', value)}
                required
            />
            <TextAreaField label="Uraian singkat kerugian konstitusional" value={form.kerugian_konstitusional} onChange={value => onChange('kerugian_konstitusional', value)} required placeholder="Jelaskan hak konstitusional yang dirugikan, bentuk kerugian, dan hubungan dengan norma." />
            <TextAreaField label="Identitas PMK 2/2021" value={form.identitas_lengkap} onChange={value => onChange('identitas_lengkap', value)} rows={3} placeholder="Pekerjaan, kewarganegaraan, alamat rumah/kantor, dan email." />
            <TextAreaField label="Kronologi singkat" value={form.kronologi} onChange={value => onChange('kronologi', value)} rows={3} />
            <TextAreaField label="Alasan permohonan per poin" value={form.alasan_permohonan} onChange={value => onChange('alasan_permohonan', value)} rows={5} />
            <TextField label="Target jenis petitum" value={form.target_petitum} onChange={value => onChange('target_petitum', value)} placeholder="Contoh: inkonstitusional bersyarat" />
            <TextAreaField label="Referensi perkara yang ingin dipertimbangkan" value={form.referensi_perkara} onChange={value => onChange('referensi_perkara', value)} rows={3} />
            <TextAreaField label="Catatan strategi khusus" value={form.catatan_strategi} onChange={value => onChange('catatan_strategi', value)} rows={3} />
        </div>
    );
}

function ImproveDraftFormView({
    form,
    uploadedDraft,
    uploading,
    uploadError,
    fileRef,
    onUpload,
    onChange,
    onToggleImprovement,
}: {
    form: ImproveDraftForm;
    uploadedDraft: UploadedPermohonanDraft | null;
    uploading: boolean;
    uploadError: string | null;
    fileRef: React.RefObject<HTMLInputElement | null>;
    onUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
    onChange: (field: keyof ImproveDraftForm, value: string | string[]) => void;
    onToggleImprovement: (option: string) => void;
}) {
    return (
        <div className="bg-white border border-border rounded-2xl p-5 shadow-sm space-y-4">
            <div>
                <h3 className="font-bold text-text-primary">Perbaiki Draft Lama</h3>
                <p className="text-xs text-text-muted mt-1">Unggah PDF, DOCX, DOC, TXT, atau MD untuk diekstrak terlebih dahulu.</p>
            </div>

            <div>
                <FieldLabel label="Upload draft" required />
                <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt,.md" onChange={onUpload} className="hidden" />
                <button
                    type="button"
                    onClick={() => fileRef.current?.click()}
                    disabled={uploading}
                    className="w-full border border-dashed border-border rounded-xl px-4 py-5 flex items-center justify-center gap-2 text-sm font-bold text-text-secondary hover:border-primary hover:text-primary transition-colors disabled:opacity-50"
                >
                    {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                    {uploading ? 'Mengekstrak...' : uploadedDraft ? uploadedDraft.filename : 'Pilih draft lama'}
                </button>
                {uploadedDraft && (
                    <p className="text-xs text-dikabulkan mt-2">
                        {uploadedDraft.filename} berhasil diekstrak ({formatNumber(uploadedDraft.raw_text.length)} karakter).
                    </p>
                )}
                {uploadError && <p className="text-xs text-ditolak mt-2">{uploadError}</p>}
            </div>

            <div>
                <FieldLabel label="Tujuan perbaikan" required />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {IMPROVEMENT_OPTIONS.map(option => (
                        <label key={option} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm text-text-secondary">
                            <input
                                type="checkbox"
                                checked={form.tujuan_perbaikan.includes(option)}
                                onChange={() => onToggleImprovement(option)}
                                className="accent-primary"
                            />
                            {option}
                        </label>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SelectField label="Jenis pengujian" value={form.jenis_pengujian} onChange={value => onChange('jenis_pengujian', value)} options={['', 'uji materiil', 'uji formil', 'campuran']} />
                <SelectField label="Scope perbaikan" value={form.scope_rewrite} onChange={value => onChange('scope_rewrite', value)} options={['susun ulang total bila perlu', 'edit terbatas saja']} />
                <TextField label="Pasal yang diuji" value={form.pasal_diuji} onChange={value => onChange('pasal_diuji', value)} />
                <TextField label="Pasal UUD batu uji" value={form.batu_uji_uud} onChange={value => onChange('batu_uji_uud', value)} />
            </div>
            <TextAreaField label="Catatan kelemahan draft menurut user" value={form.kelemahan_draft} onChange={value => onChange('kelemahan_draft', value)} rows={4} />
            <TextAreaField label="Instruksi tambahan" value={form.instruksi_tambahan} onChange={value => onChange('instruksi_tambahan', value)} rows={4} />
        </div>
    );
}

export default PermohonanDraftTab;
