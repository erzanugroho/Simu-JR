# Implementation Plan - Professional Project Management Layer

The goal is to upgrade the current single-page simulation interface into a professional project-based application. This involves creating a new Dashboard (Main Page) with project CRUD operations, a structured storage system for project-related simulations and files, and a revamped navigation flow.

## User Review Required

> [!IMPORTANT]
> The landing page will change from the Simulation Terminal to a Project Dashboard. Users will need to select or create a project before starting a simulation.

> [!TIP]
> **Advanced Analysis Tools**: We are adding:
> 1. **Tab Riset**: AI-powered legal research and summary.
> 2. **Audit Petitum**: A consistency checker that ensures the 'Petitum' (requests) align with the 'Posita' (legal arguments).

> [!WARNING]
> This change introduces a new backend storage structure for Projects. Existing simulations (in `results/simulations/`) will be grouped into a "Default Project" initially to preserve data.

## Proposed Changes

### [Backend] Project Storage & API
Implement a new storage module for Projects and expose REST endpoints.

#### [NEW] [project_store.py](file:///e:/Simu%20JR/simulasi/core/project_store.py)
- Create `results/projects/` directory.
- Implement CRUD for projects (metadata + linked simulations/files).
- Handle file uploads within project directories.

#### [MODIFY] [server.py](file:///e:/Simu%20JR/simulasi/server.py)
- Add endpoints:
    - `GET /api/projects`: List all projects.
    - `POST /api/projects`: Create a new project.
    - `GET /api/projects/{id}`: Get project details.
    - `PUT /api/projects/{id}`: Update project metadata.
    - `DELETE /api/projects/{id}`: Delete project.
    - `POST /api/projects/{id}/files`: Upload file to project.
    - `POST /api/projects/{id}/research`: Query RAG and save research findings.
    - `POST /api/projects/{id}/audit`: Analyze draft for consistency between Posita and Petitum.
- Update `/api/simulate` to optionally accept a `project_id`.

### [Frontend] Dashboard & State Management
Revamp the frontend to include a landing page and project-aware state.

#### [MODIFY] [types.ts](file:///e:/Simu%20JR/simulasi/frontend/src/types.ts)
- Add `Project` and `ProjectFile` interfaces.

#### [NEW] [Dashboard.tsx](file:///e:/Simu%20JR/simulasi/frontend/src/components/Dashboard.tsx)
- Main landing page showing project grid/list.
- "Create Project" modal/form.
- Stats overview.

#### [NEW] [ProjectDetail.tsx](file:///e:/Simu%20JR/simulasi/frontend/src/components/ProjectDetail.tsx)
- View simulations and files for a specific project.
- Tabbed interface: "Simulasi", "Riset (AI Research)", "Audit (Consistency)", and "Dokumen".
- "Riset" tab: AI assistant for precedents and laws.
- "Audit" tab: Automated analysis of the draft to detect logical gaps or inconsistencies between arguments and requests.

#### [MODIFY] [App.tsx](file:///e:/Simu%20JR/simulasi/frontend/src/App.tsx)
- Implement conditional rendering or routing to switch between `Dashboard`, `ProjectDetail`, and the `SimulationView` (current logic).
- Integrate project selection into the simulation flow.

#### [MODIFY] [useApi.ts](file:///e:/Simu%20JR/simulasi/frontend/src/hooks/useApi.ts)
- Add `useProjects` hook for API interaction.

## Verification Plan

### Automated Tests
- Test project creation/retrieval via backend unit tests (if applicable).
- Verify file upload persistence to correct project folders.

### Manual Verification
- Create a new project named "Uji Materi UU Cipta Kerja".
- Upload a PDF to the project and verify it appears in the "Dokumen" tab.
- Use the "Riset" tab to ask "Apa putusan MK terkait outsourcing di UU Cipta Kerja?" and verify findings are saved.
- Run an "Audit" on a draft where the Petitum doesn't match the Posita, and verify the AI detects the discrepancy.
- Start a simulation within the project and verify it is saved under that project's simulation list.
- Delete a project and ensure all associated files/metadata are cleaned up.
