import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getProjects, createProject, updateProject, deleteProject } from '../api/projects';
import type { Project, CreateProjectPayload } from '../types/project';
import { ProjectFormModal } from '../components/ProjectFormModal';

export const Dashboard: React.FC = () => {
  const { user, logout } = useAuth();

  // Project state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true);
  const [projectError, setProjectError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchUserProjects = async () => {
    setIsLoadingProjects(true);
    setProjectError(null);
    try {
      const data = await getProjects();
      setProjects(data);
      if (data.length > 0) {
        setSelectedProject((prev) => {
          if (prev && data.some((p) => p.id === prev.id)) {
            return data.find((p) => p.id === prev.id) || data[0];
          }
          return data[0];
        });
      } else {
        setSelectedProject(null);
      }
    } catch (err: any) {
      setProjectError(err?.data?.detail || 'Failed to load projects.');
    } finally {
      setIsLoadingProjects(false);
    }
  };

  useEffect(() => {
    fetchUserProjects();
  }, []);

  const handleOpenCreateModal = () => {
    setEditingProject(null);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (project: Project) => {
    setEditingProject(project);
    setIsModalOpen(true);
  };

  const handleSaveProject = async (payload: CreateProjectPayload) => {
    if (editingProject) {
      const updated = await updateProject(editingProject.id, payload);
      setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (selectedProject?.id === updated.id) {
        setSelectedProject(updated);
      }
    } else {
      const created = await createProject(payload);
      setProjects((prev) => [created, ...prev]);
      setSelectedProject(created);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingProject) return;
    setIsDeleting(true);
    try {
      await deleteProject(deletingProject.id);
      const remaining = projects.filter((p) => p.id !== deletingProject.id);
      setProjects(remaining);
      if (selectedProject?.id === deletingProject.id) {
        setSelectedProject(remaining.length > 0 ? remaining[0] : null);
      }
      setDeletingProject(null);
    } catch (err: any) {
      alert(err?.data?.detail || 'Failed to delete project.');
    } finally {
      setIsDeleting(false);
    }
  };


  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f9fafb', fontFamily: 'system-ui, sans-serif', width: '100%', boxSizing: 'border-box' }}>
      {/* Navigation Header */}
      <header style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={logoIconStyle}>D</div>
            <div>
              <h1 style={{ fontSize: '18px', margin: 0, fontWeight: 700, color: '#111827' }}>DoxaRank</h1>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>● Ethiopia-First SEO</span>
            </div>
          </div>

          {selectedProject && (
            <div style={activeProjectBadgeStyle}>
              <span style={{ color: '#6b7280', fontSize: '12px', marginRight: '4px' }}>Active Project:</span>
              <span style={{ fontWeight: 700, color: '#1d4ed8' }}>{selectedProject.name}</span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
              {user?.full_name || 'DoxaRank User'}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280' }}>
              {user?.email}
            </div>
          </div>
          <button
            id="logout-button"
            onClick={logout}
            style={logoutButtonStyle}
          >
            Log out
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ maxWidth: '1080px', margin: '32px auto', padding: '0 20px', textAlign: 'left' }}>
        
        {/* Selected Project Overview Card */}
        {selectedProject ? (
          <div style={selectedProjectCardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <span style={{ fontSize: '12px', textTransform: 'uppercase', fontWeight: 700, color: '#2563eb', letterSpacing: '0.05em' }}>
                  Current Project Context
                </span>
                <h2 style={{ margin: '4px 0', fontSize: '26px', fontWeight: 700, color: '#111827' }}>
                  {selectedProject.name}
                </h2>
                <a
                  href={selectedProject.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#4b5563', fontSize: '14px', textDecoration: 'none' }}
                >
                  🔗 {selectedProject.website_url}
                </a>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => handleOpenEditModal(selectedProject)}
                  style={secondaryActionBtnStyle}
                >
                  Edit Project
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div style={welcomePromptStyle}>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '22px', color: '#111827' }}>
              Welcome to DoxaRank, {user?.first_name || user?.email}! 👋
            </h2>
            <p style={{ margin: 0, color: '#4b5563', fontSize: '14px' }}>
              Get started by creating your first project to track keyword rankings and SEO health.
            </p>
          </div>
        )}

        {/* Projects Section Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '32px 0 16px 0' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
              Your Projects {projects.length > 0 && `(${projects.length})`}
            </h3>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
              Manage the websites you are tracking on DoxaRank.
            </p>
          </div>
          <button
            id="add-project-button"
            onClick={handleOpenCreateModal}
            style={primaryAddBtnStyle}
          >
            + Add Project
          </button>
        </div>

        {/* Error Alert */}
        {projectError && (
          <div style={errorAlertStyle}>
            {projectError}
          </div>
        )}

        {/* Loading State */}
        {isLoadingProjects ? (
          <div style={loadingStateStyle}>
            <p style={{ color: '#6b7280', fontSize: '15px' }}>Loading projects from Neon PostgreSQL...</p>
          </div>
        ) : projects.length === 0 ? (
          /* Empty State */
          <div style={emptyStateCardStyle}>
            <div style={{ fontSize: '40px', marginBottom: '12px' }}>📁</div>
            <h4 style={{ margin: '0 0 6px 0', fontSize: '18px', fontWeight: 600, color: '#111827' }}>
              No projects yet
            </h4>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#6b7280', maxWidth: '400px' }}>
              Create your first project to begin tracking Ethiopian search keywords, search intent, and rankings.
            </p>
            <button
              id="empty-add-project-button"
              onClick={handleOpenCreateModal}
              style={primaryAddBtnStyle}
            >
              Create your first project
            </button>
          </div>
        ) : (
          /* Projects Grid */
          <div style={projectsGridStyle}>
            {projects.map((project) => {
              const isSelected = selectedProject?.id === project.id;
              return (
                <div
                  key={project.id}
                  style={{
                    ...projectCardStyle,
                    borderColor: isSelected ? '#3b82f6' : '#e5e7eb',
                    backgroundColor: isSelected ? '#f8faff' : '#ffffff',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                    <div>
                      <h4 style={{ margin: '0 0 4px 0', fontSize: '17px', fontWeight: 700, color: '#111827' }}>
                        {project.name}
                      </h4>
                      <a
                        href={project.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: '#2563eb', fontSize: '13px', textDecoration: 'none', wordBreak: 'break-all' }}
                      >
                        {project.website_url}
                      </a>
                    </div>
                    {isSelected && (
                      <span style={activeTagStyle}>Active</span>
                    )}
                  </div>

                  <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '16px' }}>
                    Created on {new Date(project.created_at).toLocaleDateString()}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #f3f4f6', paddingTop: '12px' }}>
                    {!isSelected ? (
                      <button
                        onClick={() => setSelectedProject(project)}
                        style={selectBtnStyle}
                      >
                        Select
                      </button>
                    ) : (
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#2563eb' }}>● Selected</span>
                    )}

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => handleOpenEditModal(project)}
                        style={cardActionBtnStyle}
                      >
                        Edit
                      </button>
                      <button
                        id={`delete-btn-${project.id}`}
                        onClick={() => setDeletingProject(project)}
                        style={{ ...cardActionBtnStyle, color: '#ef4444' }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* Create / Edit Project Modal */}
      <ProjectFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={handleSaveProject}
        projectToEdit={editingProject}
      />

      {/* Custom Delete Confirmation Modal */}
      {deletingProject && (
        <div style={modalOverlayStyle}>
          <div style={deleteModalBoxStyle}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
              Delete Project
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#4b5563', lineHeight: 1.5 }}>
              Are you sure you want to delete <strong>{deletingProject.name}</strong> ({deletingProject.website_url})? This action cannot be undone.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button
                type="button"
                onClick={() => setDeletingProject(null)}
                style={cancelDeleteBtnStyle}
              >
                Cancel
              </button>
              <button
                id="confirm-delete-button"
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                style={{
                  ...confirmDeleteBtnStyle,
                  opacity: isDeleting ? 0.7 : 1,
                  cursor: isDeleting ? 'not-allowed' : 'pointer',
                }}
              >
                {isDeleting ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const modalOverlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: '16px',
};

const deleteModalBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  width: '100%',
  maxWidth: '420px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
};

const cancelDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const confirmDeleteBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  backgroundColor: '#dc2626',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
};


// Styles
const headerStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderBottom: '1px solid #e5e7eb',
  padding: '14px 24px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const logoIconStyle: React.CSSProperties = {
  width: '34px',
  height: '34px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  borderRadius: '8px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 700,
  fontSize: '18px',
};

const activeProjectBadgeStyle: React.CSSProperties = {
  backgroundColor: '#eff6ff',
  border: '1px solid #bfdbfe',
  borderRadius: '20px',
  padding: '4px 12px',
  fontSize: '13px',
};

const logoutButtonStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const selectedProjectCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
};

const welcomePromptStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  border: '1px solid #e5e7eb',
};

const primaryAddBtnStyle: React.CSSProperties = {
  padding: '10px 18px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const secondaryActionBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  backgroundColor: '#ffffff',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '12px',
  borderRadius: '8px',
  fontSize: '14px',
  marginBottom: '16px',
  border: '1px solid #fca5a5',
};

const loadingStateStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '48px 0',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
};

const emptyStateCardStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '48px 24px',
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px dashed #d1d5db',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const projectsGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
  gap: '20px',
};

const projectCardStyle: React.CSSProperties = {
  borderRadius: '12px',
  padding: '20px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'space-between',
};

const activeTagStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  backgroundColor: '#dbeafe',
  color: '#1d4ed8',
  padding: '2px 8px',
  borderRadius: '12px',
  textTransform: 'uppercase',
};

const selectBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  backgroundColor: '#ffffff',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const cardActionBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#4b5563',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  padding: '4px 8px',
};
