import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle,
  TrendingUp,
  Folder,
  FileText,
  Calendar,
  Plus,
  Trash2,
  Cpu,
  Loader2,
  Edit2,
  Eye,
  History,
  Clock,
  RefreshCw
} from 'lucide-react';
import { useProjects, useSettings } from '../hooks/useApi';
import ProjectModal from '../components/ProjectModal';

interface DashboardPageProps {
  view?: 'dashboard' | 'projects';
}

interface SavedSimulationSummary {
  id: string;
  timestamp: string;
  draft_excerpt?: string;
  total_score?: number;
  amar?: string;
  transcript_count?: number;
  project_id?: string | null;
  llm_model?: string;
}

interface SavedSimulationStats {
  total: number;
  avg_score: number;
  best_score: number;
  amar_distribution: Record<string, number>;
}

const DashboardPage: React.FC<DashboardPageProps> = ({ view = 'dashboard' }) => {
  const navigate = useNavigate();
  const { projects, total, loading, deleteProject, createProject, updateProject } = useProjects();
  const { settings } = useSettings();
  const isProjectsView = view === 'projects';
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<any>(null);
  const [simulationHistory, setSimulationHistory] = useState<SavedSimulationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [simulationStats, setSimulationStats] = useState<SavedSimulationStats | null>(null);

  const totalSims = projects.reduce((sum, p) => sum + (p.simulation_count || 0), 0);
  const totalDocs = projects.reduce((sum, p) => sum + (p.file_count || 0), 0);
  const avgScore = typeof simulationStats?.avg_score === 'number' ? simulationStats.avg_score : 0;

  const stats = [
    { label: 'Total Project', value: total.toString(), icon: Folder, color: 'text-primary', bg: 'bg-blue-50' },
    { label: 'Jumlah Dokumen', value: totalDocs.toString(), icon: FileText, color: 'text-system', bg: 'bg-purple-50' },
    { label: 'Total Simulasi', value: totalSims.toString(), icon: CheckCircle, color: 'text-pemohon', bg: 'bg-emerald-50' },
    { label: 'Rata-rata Skor', value: avgScore > 0 ? avgScore.toString() : '0', icon: TrendingUp, color: 'text-accent-dim', bg: 'bg-amber-50' },
  ];

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Hapus project ini? Seluruh riwayat simulasi dan file akan ikut terhapus.')) {
      await deleteProject(id);
    }
  };

  const handleOpenCreate = () => {
    setEditingProject(null);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (e: React.MouseEvent, project: any) => {
    e.stopPropagation();
    setEditingProject(project);
    setIsModalOpen(true);
  };

  const handleSave = async (name: string, description: string) => {
    if (editingProject) {
      await updateProject(editingProject.id, { name, description });
    } else {
      await createProject(name, description);
    }
  };

  useEffect(() => {
    if (isProjectsView) return;

    let cancelled = false;
    const fetchSimulationHistory = async () => {
      try {
        setHistoryLoading(true);
        const [historyRes, statsRes] = await Promise.all([
          fetch('/api/saved-simulations?limit=6'),
          fetch('/api/saved-simulations/stats'),
        ]);
        if (!historyRes.ok) throw new Error(`HTTP ${historyRes.status}`);
        const data = await historyRes.json();
        const statsData = statsRes.ok ? await statsRes.json() : null;
        if (!cancelled) {
          setSimulationHistory(Array.isArray(data.simulations) ? data.simulations : []);
          setSimulationStats(statsData);
        }
      } catch (err) {
        if (!cancelled) setSimulationHistory([]);
        console.error('Failed to load simulation history:', err);
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    };

    fetchSimulationHistory();
    return () => {
      cancelled = true;
    };
  }, [isProjectsView]);

  const openSimulationHistory = (sim: SavedSimulationSummary) => {
    const params = new URLSearchParams({ saved: sim.id });
    if (sim.project_id) params.set('project', sim.project_id);
    navigate(`/simulasi?${params.toString()}`);
  };

  return (
    <div className="space-y-8 animate-slide-up">
      {/* Header Area */}
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-serif font-bold text-text-primary">
            {isProjectsView ? 'Folder Project' : 'Command Center'}
          </h2>
          <p className="text-text-secondary mt-1">
            {isProjectsView
              ? 'Kelola seluruh folder perkara, dokumen, dan riwayat simulasi.'
              : 'Selamat datang kembali. Berikut adalah ringkasan performa sistem simulasi Anda.'}
          </p>
        </div>
        <button
          onClick={isProjectsView ? handleOpenCreate : () => navigate('/simulasi')}
          className="bg-primary text-white px-6 py-2.5 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:bg-primary-light transition-all flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          {isProjectsView ? 'Project Baru' : 'Mulai Simulasi Baru'}
        </button>
      </div>

      {/* Stats Grid */}
      {!isProjectsView && (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        {stats.map((stat, idx) => (
          <div key={idx} className="bg-white p-6 rounded-2xl border border-border shadow-sm hover:shadow-md transition-shadow group">
            <div className="flex justify-between items-start mb-4">
              <div className={`p-3 rounded-xl ${stat.bg} ${stat.color} transition-colors`}>
                <stat.icon className="w-6 h-6" />
              </div>
            </div>
            <p className="text-sm font-medium text-text-muted">{stat.label}</p>
            <h3 className="text-2xl font-bold text-text-primary mt-1">{stat.value}</h3>
          </div>
        ))}
        <div className="bg-white p-5 rounded-2xl border border-border shadow-sm">
          <div className="flex justify-between items-start mb-2">
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
              <Cpu className="w-5 h-5" />
            </div>
            <button
              onClick={() => navigate('/settings')}
              className="p-2 rounded-lg bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors"
              title="Buka pengaturan LLM"
              aria-label="Buka pengaturan LLM"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs text-text-muted font-medium">Model AI Dipilih</p>
          <h3 className="text-xl font-black text-text-primary mt-1 truncate" title={settings?.model || settings?.customModelId || 'Local Model'}>
            {settings?.model || settings?.customModelId || 'Local Model'}
          </h3>
        </div>
      </div>
      )}

      {/* Main Content Grid */}
      <div className={`grid grid-cols-1 gap-8 ${isProjectsView ? '' : 'lg:grid-cols-3'}`}>
        {/* Project List */}
        <div className={`${isProjectsView ? '' : 'lg:col-span-2'} bg-white rounded-2xl border border-border overflow-hidden shadow-sm`}>
          <div className="p-6 border-b border-border flex justify-between items-center">
            <h3 className="font-bold text-text-primary">Folder Project Simulasi</h3>
            <div className="flex items-center gap-4">
              <button 
                onClick={handleOpenCreate}
                className="text-[11px] bg-primary/10 text-primary px-3 py-1.5 rounded-lg font-bold hover:bg-primary hover:text-white transition-all flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                PROJECT BARU
              </button>
              <div className="w-[1px] h-4 bg-border"></div>
              {loading && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
              {!isProjectsView && (
                <button
                  onClick={() => navigate('/projects')}
                  className="text-sm font-bold text-primary hover:underline"
                >
                  Lihat Semua
                </button>
              )}
            </div>
          </div>
          <div className="divide-y divide-border min-h-[300px]">
            {projects.length === 0 && !loading ? (
              <div className="flex flex-col items-center justify-center py-20 text-text-muted">
                <Folder className="w-12 h-12 mb-4 opacity-20" />
                <p className="text-sm">Belum ada project. Klik "Project Baru" untuk memulai.</p>
              </div>
            ) : (
              projects.map((project) => (
                <div
                  key={project.id}
                  onClick={() => navigate(`/projects/${project.id}`)}
                  className="p-4 hover:bg-bg-primary transition-colors flex items-center justify-between group cursor-pointer"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-bg-secondary flex items-center justify-center text-primary group-hover:bg-primary group-hover:text-white transition-all">
                      <Folder className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-text-primary">{project.name}</h4>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider">
                          {project.simulation_count || 0} Simulasi
                        </span>
                        <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                        <span className="text-xs text-text-muted flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(project.updated_at || project.created_at).toLocaleDateString('id-ID')}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-tight bg-slate-50 text-slate-700`}>
                      Active
                    </span>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => handleOpenEdit(e, project)}
                        className="p-2 text-slate-300 hover:text-primary transition-colors"
                        title="Edit Project"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => handleDelete(e, project.id)}
                        className="p-2 text-slate-300 hover:text-pemerintah transition-colors"
                        title="Hapus Project"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <ProjectModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          onSave={handleSave}
          initialName={editingProject?.name || ''}
          initialDescription={editingProject?.description || ''}
          isEdit={!!editingProject}
        />

        {/* Recent Simulation History */}
        {!isProjectsView && (
        <div className="bg-white rounded-2xl border border-border p-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-bold text-text-primary">History Simulasi</h3>
            {historyLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-primary" />
            ) : (
              <History className="w-4 h-4 text-text-muted" />
            )}
          </div>
          <div className="space-y-3">
            {simulationHistory.map((sim) => (
              <button
                key={sim.id}
                onClick={() => openSimulationHistory(sim)}
                className="w-full text-left rounded-xl border border-border bg-white p-3 hover:bg-bg-primary hover:border-primary/20 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0 group-hover:bg-primary group-hover:text-white transition-colors">
                    <Eye className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-text-primary truncate">
                      {sim.draft_excerpt || 'Simulasi tanpa judul'}
                    </p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] font-bold uppercase tracking-tight text-text-muted">
                      <Clock className="w-3 h-3" />
                      <span>{new Date(sim.timestamp).toLocaleString('id-ID')}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                      {typeof sim.total_score === 'number' && sim.total_score > 0 && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
                          sim.total_score >= 70 ? 'bg-emerald-50 text-dikabulkan' : sim.total_score >= 50 ? 'bg-amber-50 text-tidak-diterima' : 'bg-red-50 text-ditolak'
                        }`}>
                          Skor {sim.total_score}
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded-full bg-slate-50 text-[10px] font-black text-slate-600 uppercase">
                        {sim.amar || '-'}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
            {!historyLoading && simulationHistory.length === 0 && (
              <div className="flex flex-col items-center justify-center py-10 text-text-muted">
                <History className="w-10 h-10 mb-3 opacity-20" />
                <p className="text-xs text-center">Belum ada history simulasi tersimpan.</p>
              </div>
            )}
          </div>
          <button
            onClick={() => navigate('/projects')}
            className="w-full mt-6 py-3 rounded-xl border border-border text-sm font-bold text-text-muted hover:bg-bg-primary transition-all"
          >
            Lihat Semua Project
          </button>
        </div>
        )}
      </div>
    </div>
  );
};

export default DashboardPage;
