import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { Project } from '../types';

interface ProjectContextValue {
    currentProject: Project | null;
    setCurrentProject: (project: Project | null) => void;
}

const ProjectContext = createContext<ProjectContextValue>({
    currentProject: null,
    setCurrentProject: () => { },
});

export function ProjectProvider({ children }: { children: ReactNode }) {
    const [currentProject, setCurrentProject] = useState<Project | null>(null);

    const handleSetProject = useCallback((project: Project | null) => {
        setCurrentProject(project);
    }, []);

    return (
        <ProjectContext.Provider value={{ currentProject, setCurrentProject: handleSetProject }}>
            {children}
        </ProjectContext.Provider>
    );
}

export function useProjectContext() {
    return useContext(ProjectContext);
}