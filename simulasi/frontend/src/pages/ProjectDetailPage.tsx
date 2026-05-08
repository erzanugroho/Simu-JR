import React, { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, BarChart3, Search as SearchIcon, Shield, FileText,
    Upload, Trash2, Play, Send, Loader2, CheckCircle, XCircle, AlertTriangle,
    Folder, Calendar, Edit2, Eye
} from 'lucide-react';
import { useProject, useProjectFiles, useProjectSimulations, useProjectResearch, useProjectAudit } from '../hooks/useApi';
import { useProjectContext } from '../context/ProjectContext';
import ProjectModal from '../components/ProjectModal';
import type { AuditIssue } from '../types';
import PermohonanDraftTab from './PermohonanDraftTab';

type TabId = 'simulasi' | 'riset' | 'audit' | 'buat_permohonan' | 'dokumen';

const TABS: { id: TabId; label: string; icon: typeof BarChart3 }[] = [
    { id: 'simulasi', label: 'Simulasi', icon: BarChart3 },
    { id: 'riset', label: 'Riset Hukum', icon: SearchIcon },
    { id: 'audit', label: 'Audit Petitum', icon: Shield },
    { id: 'buat_permohonan', label: 'Buat Dokumen Permohonan', icon: FileText },
    { id: 'dokumen', label: 'Dokumen', icon: FileText },
];

const ProjectDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { project, loading, updateProject } = useProject(id || '');
    const { setCurrentProject } = useProjectContext();
    const [activeTab, setActiveTab] = useState<TabId>('simulasi');

    const [isEditModalOpen, setIsEditModalOpen] = useState(false);

    React.useEffect(() => {
        if (project) {
            setCurrentProject(project);
        }
        return () => setCurrentProject(null);
    }, [project, setCurrentProject]);

    const handleSaveEdit = async (name: string, description: string) => {
        await updateProject({ name, description });
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
        );
    }

    if (!project) {
        return (
            <div className="flex flex-col items-center justify-center py-20 gap-4">
                <p className="text-text-muted">Project tidak ditemukan</p>
                <button onClick={() => navigate('/')} className="bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold">
                    Kembali ke Dashboard
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-slide-up">
            {/* Breadcrumb & Header */}
            <div>
                <button
                    onClick={() => navigate('/')}
                    className="flex items-center gap-2 text-text-muted hover:text-text-primary transition-colors text-sm mb-3"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Dashboard
                </button>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-bg-secondary flex items-center justify-center text-primary">
                            <Folder className="w-6 h-6" />
                        </div>
                        <div>
                            <div className="flex items-center gap-3">
                                <h2 className="text-2xl font-serif font-bold text-text-primary">{project.name}</h2>
                                <button
                                    onClick={() => setIsEditModalOpen(true)}
                                    className="p-1.5 rounded-lg hover:bg-slate-100 text-text-muted hover:text-primary transition-colors"
                                    title="Edit Nama Project"
                                >
                                    <Edit2 className="w-4 h-4" />
                                </button>
                            </div>
                            {project.description && (
                                <p className="text-text-secondary text-sm mt-0.5">{project.description}</p>
                            )}
                            <div className="flex items-center gap-4 mt-1 text-xs text-text-muted">
                                <span className="flex items-center gap-1.5">
                                    <BarChart3 className="w-3.5 h-3.5" />
                                    {project.simulation_count || 0} simulasi
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <FileText className="w-3.5 h-3.5" />
                                    {project.file_count || 0} dokumen
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <Calendar className="w-3.5 h-3.5" />
                                    {new Date(project.updated_at || project.created_at).toLocaleDateString('id-ID')}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-white rounded-xl p-1 border border-border overflow-x-auto">
                {TABS.map(tab => {
                    const Icon = tab.icon;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold transition-all whitespace-nowrap ${activeTab === tab.id
                                ? 'bg-primary text-white shadow-md'
                                : 'text-text-muted hover:text-text-primary hover:bg-bg-primary'
                                }`}
                        >
                            <Icon className="w-4 h-4" />
                            {tab.label}
                        </button>
                    );
                })}
            </div>

            {/* Tab Content */}
            {activeTab === 'simulasi' && <SimulasiTab projectId={id!} onNavigate={navigate} />}
            {activeTab === 'riset' && <RisetTab projectId={id!} />}
            {activeTab === 'audit' && <AuditTab projectId={id!} />}
            {activeTab === 'buat_permohonan' && <PermohonanDraftTab projectId={id!} />}
            {activeTab === 'dokumen' && <DokumenTab projectId={id!} />}

            <ProjectModal
                isOpen={isEditModalOpen}
                onClose={() => setIsEditModalOpen(false)}
                onSave={handleSaveEdit}
                initialName={project?.name || ''}
                initialDescription={project?.description || ''}
                isEdit
            />
        </div>
    );
};

function SimulasiTab({ projectId, onNavigate }: { projectId: string; onNavigate: (path: string) => void }) {
    const { simulations, loading } = useProjectSimulations(projectId);
    if (!projectId) return null;

    return (
        <div className="bg-white rounded-2xl border border-border overflow-hidden shadow-sm">
            <div className="p-6 border-b border-border flex justify-between items-center">
                <h3 className="font-bold text-text-primary">Riwayat Simulasi</h3>
                <button
                    onClick={() => onNavigate(`/simulasi?project=${projectId}`)}
                    className="bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 shadow-md hover:bg-primary-light transition-all"
                >
                    <Play className="w-4 h-4" />
                    Simulasi Baru
                </button>
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                </div>
            ) : simulations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-text-muted">
                    <BarChart3 className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-sm">Belum ada simulasi di project ini</p>
                    <button
                        onClick={() => onNavigate(`/simulasi?project=${projectId}`)}
                        className="mt-4 bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold inline-flex items-center gap-2"
                    >
                        <Play className="w-4 h-4" />
                        Mulai Simulasi
                    </button>
                </div>
            ) : (
                <div className="divide-y divide-border">
                    {simulations.map((sim: any) => (
                        <div key={sim.id} className="p-4 hover:bg-bg-primary transition-colors flex items-center justify-between">
                            <div className="min-w-0 flex-1">
                                <div className="text-sm font-bold text-text-primary truncate">
                                    {sim.draft_excerpt || 'Tanpa judul'}
                                </div>
                                <div className="text-xs text-text-muted mt-1">
                                    {new Date(sim.timestamp).toLocaleString('id-ID')} · {sim.transcript_count} entri
                                </div>
                            </div>
                            <div className="flex items-center gap-3 shrink-0 ml-4">
                                {sim.total_score > 0 && (
                                    <span className={`text-lg font-bold ${sim.total_score >= 70 ? 'text-dikabulkan' : sim.total_score >= 50 ? 'text-tidak-diterima' : 'text-ditolak'
                                        }`}>
                                        {sim.total_score}
                                    </span>
                                )}
                                <span className="text-xs text-text-muted">{sim.amar || '-'}</span>
                                <button
                                    onClick={() => onNavigate(`/simulasi?project=${projectId}&saved=${sim.id}`)}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary hover:text-white transition-all text-xs font-bold"
                                    title="Lihat ulang simulasi"
                                >
                                    <Eye className="w-3.5 h-3.5" />
                                    Lihat
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function RisetTab({ projectId }: { projectId: string }) {
    const { findings, querying, streamingText, runResearch, externalError } = useProjectResearch(projectId);
    const [query, setQuery] = useState('');
    const listRef = useRef<HTMLDivElement>(null);

    const handleRun = async () => {
        if (!query.trim() || querying) return;
        const q = query.trim();
        setQuery('');
        await runResearch(q);
        listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    };

    return (
        <div className="space-y-4">
            {/* Query Input */}
            <div className="bg-white rounded-2xl border border-border p-4 shadow-sm">
                <h3 className="font-bold text-text-primary mb-3">Riset Hukum AI</h3>
                <div className="flex gap-3">
                    <input
                        type="text"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleRun()}
                        placeholder="Contoh: Apa putusan MK terkait outsourcing di UU Cipta Kerja?"
                        className="flex-1 px-4 py-2.5 rounded-xl border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
                        disabled={querying}
                    />
                    <button
                        onClick={handleRun}
                        disabled={!query.trim() || querying}
                        className="bg-primary text-white px-4 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 disabled:opacity-50 shadow-md hover:bg-primary-light transition-all"
                    >
                        {querying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                        {querying ? 'Mencari...' : 'Riset'}
                    </button>
                </div>
            </div>

            {/* External API Error Notification */}
            {externalError && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3 animate-slide-up">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                        <div className="text-sm font-bold text-amber-800">Peringatan: API Pasal.id</div>
                        <div className="text-xs text-amber-700 mt-1">
                            {externalError}. Menggunakan data RAG lokal sebagai fallback.
                        </div>
                    </div>
                </div>
            )}

            {/* Streaming indicator */}
            {querying && streamingText && (
                <div className="bg-white rounded-2xl border border-primary/30 p-5 shadow-sm animate-slide-up">
                    <div className="flex items-center gap-2 mb-2">
                        <Loader2 className="w-4 h-4 animate-spin text-primary" />
                        <span className="text-xs font-bold text-primary uppercase">Menjawab...</span>
                    </div>
                    <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">{streamingText}</div>
                </div>
            )}

            {/* Findings */}
            <div ref={listRef} className="space-y-4">
                {findings.length === 0 && !querying ? (
                    <div className="bg-white rounded-2xl border border-border p-12 shadow-sm text-center">
                        <SearchIcon className="w-12 h-12 text-text-muted opacity-20 mx-auto mb-3" />
                        <p className="text-sm text-text-muted">Ajukan pertanyaan hukum untuk memulai riset</p>
                    </div>
                ) : (
                    findings.map((f) => (
                        <div key={f.id} className="bg-white rounded-2xl border border-border p-5 shadow-sm animate-slide-up">
                            <div className="text-xs text-text-muted font-bold uppercase tracking-wide mb-2">
                                {new Date(f.timestamp).toLocaleString('id-ID')}
                            </div>
                            <div className="text-sm font-bold text-primary mb-3">{f.query}</div>
                            <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
                                {f.answer}
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

function AuditTab({ projectId }: { projectId: string }) {
    const { audits, running, runAudit } = useProjectAudit(projectId);
    const [draft, setDraft] = useState('');

    const handleRun = async () => {
        if (!draft.trim() || running) return;
        await runAudit(draft.trim());
    };

    return (
        <div className="space-y-4">
            {/* Draft Input */}
            <div className="bg-white rounded-2xl border border-border p-4 shadow-sm">
                <h3 className="font-bold text-text-primary mb-3">Audit Petitum vs Posita</h3>
                <textarea
                    value={draft}
                    onChange={e => setDraft(e.target.value)}
                    placeholder="Tempel draft permohonan PUU di sini untuk dianalisis konsistensi Petitum dan Posita..."
                    rows={6}
                    className="w-full px-4 py-2.5 rounded-xl border border-border text-sm text-text-primary placeholder:text-text-muted resize-none mb-3 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
                    disabled={running}
                />
                <div className="flex justify-end">
                    <button
                        onClick={handleRun}
                        disabled={!draft.trim() || running}
                        className="bg-primary text-white px-4 py-2 rounded-xl font-bold text-sm flex items-center gap-2 disabled:opacity-50 shadow-md hover:bg-primary-light transition-all"
                    >
                        {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
                        {running ? 'Menganalisis...' : 'Jalankan Audit'}
                    </button>
                </div>
            </div>

            {/* Audit Results */}
            {audits.length === 0 && !running ? (
                <div className="bg-white rounded-2xl border border-border p-12 shadow-sm text-center">
                    <Shield className="w-12 h-12 text-text-muted opacity-20 mx-auto mb-3" />
                    <p className="text-sm text-text-muted">Tempel draft untuk memeriksa konsistensi Petitum vs Posita</p>
                </div>
            ) : (
                audits.map((audit) => (
                    <div key={audit.id} className="bg-white rounded-2xl border border-border p-5 shadow-sm animate-slide-up">
                        <div className="flex items-center gap-3 mb-3">
                            {audit.consistent ? (
                                <CheckCircle className="w-5 h-5 text-dikabulkan shrink-0" />
                            ) : (
                                <XCircle className="w-5 h-5 text-ditolak shrink-0" />
                            )}
                            <span className={`text-sm font-bold ${audit.consistent ? 'text-dikabulkan' : 'text-ditolak'}`}>
                                {audit.consistent ? 'Konsisten' : 'Ada Ketidakcocokan'}
                            </span>
                            <span className="text-xs text-text-muted ml-auto">
                                {new Date(audit.timestamp).toLocaleString('id-ID')}
                            </span>
                        </div>

                        {audit.summary && (
                            <p className="text-sm text-text-secondary mb-3">{audit.summary}</p>
                        )}

                        {audit.issues && audit.issues.length > 0 && (
                            <div className="space-y-2">
                                {audit.issues.map((issue: AuditIssue, i: number) => (
                                    <div key={i} className="bg-red-50 border border-red-100 rounded-xl p-3">
                                        <div className="flex items-start gap-2">
                                            <AlertTriangle className="w-4 h-4 text-ditolak shrink-0 mt-0.5" />
                                            <div>
                                                <div className="text-xs font-bold text-text-primary">{issue.location}</div>
                                                <div className="text-xs text-text-secondary mt-0.5">{issue.description}</div>
                                                {issue.suggestion && (
                                                    <div className="text-xs text-primary mt-1 font-medium">💡 {issue.suggestion}</div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {(audit.posita_count != null || audit.petitum_count != null) && (
                            <div className="flex gap-4 mt-3 pt-3 border-t border-border text-xs text-text-muted">
                                {audit.posita_count != null && <span>Posita: {audit.posita_count}</span>}
                                {audit.petitum_count != null && <span>Petitum: {audit.petitum_count}</span>}
                                {audit.matched_count != null && <span>Cocok: {audit.matched_count}</span>}
                            </div>
                        )}
                    </div>
                ))
            )}
        </div>
    );
}

function DokumenTab({ projectId }: { projectId: string }) {
    const { files, uploading, uploadFile, deleteFile } = useProjectFiles(projectId);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        await uploadFile(file);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const getFileIcon = (filename: string) => {
        if (filename.endsWith('.pdf')) return '📄';
        if (filename.endsWith('.docx') || filename.endsWith('.doc')) return '📝';
        return '📃';
    };

    return (
        <div className="bg-white rounded-2xl border border-border overflow-hidden shadow-sm">
            <div className="p-6 border-b border-border flex justify-between items-center">
                <h3 className="font-bold text-text-primary">Dokumen & File Bukti</h3>
                <div>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.docx,.doc,.txt"
                        onChange={handleUpload}
                        className="hidden"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 disabled:opacity-50 shadow-md hover:bg-primary-light transition-all"
                    >
                        {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                        {uploading ? 'Mengupload...' : 'Upload File'}
                    </button>
                </div>
            </div>

            {files.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-text-muted">
                    <FileText className="w-12 h-12 mb-4 opacity-20" />
                    <p className="text-sm mb-1">Belum ada dokumen</p>
                    <p className="text-xs">Upload PDF, DOCX, atau TXT</p>
                </div>
            ) : (
                <div className="divide-y divide-border">
                    {files.map((file) => (
                        <div key={file.id} className="p-4 flex items-center gap-3 hover:bg-bg-primary transition-colors">
                            <span className="text-xl">{getFileIcon(file.filename)}</span>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-text-primary truncate">{file.filename}</div>
                                <div className="text-xs text-text-muted">
                                    {formatSize(file.size)} · {new Date(file.uploaded_at).toLocaleDateString('id-ID')}
                                </div>
                            </div>
                            <button
                                onClick={() => {
                                    if (confirm(`Hapus ${file.filename}?`)) deleteFile(file.id);
                                }}
                                className="p-2 rounded-lg hover:bg-red-50 text-text-muted hover:text-ditolak transition-colors"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default ProjectDetailPage;
