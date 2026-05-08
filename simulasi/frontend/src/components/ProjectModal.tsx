import { useState, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';

interface ProjectModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: (name: string, description: string) => Promise<void>;
    initialName?: string;
    initialDescription?: string;
    isEdit?: boolean;
}

export default function ProjectModal({ isOpen, onClose, onSave, initialName = '', initialDescription = '', isEdit = false }: ProjectModalProps) {
    const [name, setName] = useState(initialName);
    const [description, setDescription] = useState(initialDescription);
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setName(initialName);
            setDescription(initialDescription);
        }
    }, [isOpen, initialName, initialDescription]);

    if (!isOpen) return null;

    const handleSubmit = async () => {
        if (!name.trim()) return;
        setIsSaving(true);
        try {
            await onSave(name.trim(), description.trim());
            onClose();
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
            <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden animate-scale-up">
                <div className="p-6 border-b border-border flex justify-between items-center bg-bg-secondary">
                    <h3 className="font-serif font-bold text-text-primary">
                        {isEdit ? 'Edit Project' : 'Project Baru'}
                    </h3>
                    <button onClick={onClose} className="p-1.5 hover:bg-slate-200 rounded-lg transition-colors">
                        <X className="w-4 h-4 text-text-muted" />
                    </button>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-[10px] font-bold text-text-muted uppercase mb-1.5 ml-1">Nama Project</label>
                        <input
                            autoFocus
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Contoh: Pengujian UU Cipta Kerja"
                            className="w-full px-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all"
                        />
                    </div>
                    <div>
                        <label className="block text-[10px] font-bold text-text-muted uppercase mb-1.5 ml-1">Deskripsi (Opsional)</label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Berikan catatan singkat tentang project ini..."
                            rows={3}
                            className="w-full px-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all resize-none"
                        />
                    </div>
                    <div className="pt-2 flex gap-3">
                        <button
                            onClick={onClose}
                            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-text-muted hover:bg-bg-secondary transition-all"
                        >
                            Batal
                        </button>
                        <button
                            onClick={handleSubmit}
                            disabled={!name.trim() || isSaving}
                            className="flex-1 bg-primary text-white px-4 py-2.5 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:bg-primary-light transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                        >
                            {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                            {isEdit ? 'Simpan Perubahan' : 'Buat Project'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
