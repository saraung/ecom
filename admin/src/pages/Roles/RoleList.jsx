// src/pages/Roles/RoleList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, ShieldCheck, Edit2, Trash2, Users, Lock } from 'lucide-react';
import { getRoles, deleteRole } from '../../api/roles';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const RoleList = () => {
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const canManageRoles = hasPermission('roles.manage');
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState([]);
  const [confirmState, setConfirmState] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  useEffect(() => {
    fetchRoles();
  }, []);

  if (!canDo(user, 'roles.manage', 'admin')) {
    return (
      <div className="text-center py-12">
        <ShieldCheck size={48} className="mx-auto text-destructive mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to manage roles.</p>
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  const fetchRoles = async () => {
    // Never fire the API for sessions that fail the gate above.
    if (!canDo(user, 'roles.manage', 'admin')) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const response = await getRoles();
      setRoles(response.data || []);
    } catch {
      toast.error('Failed to load roles');
      setRoles([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (id, name, isSystem, userCount) => {
    if (isSystem) {
      toast.error('System roles cannot be deleted');
      return;
    }
    if (userCount > 0) {
      toast.error(`Cannot delete: ${userCount} user(s) still have this role`);
      return;
    }
    setConfirmState({
      id,
      title: 'Delete Role',
      message: `Delete role "${name}"? This action cannot be undone.`,
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    try {
      setConfirmBusy(true);
      await deleteRole(confirmState.id);
      toast.success('Role deleted successfully');
      fetchRoles();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete role');
    } finally {
      setConfirmBusy(false);
      setConfirmState(null);
    }
  };

  if (loading) {
    return <PageSkeleton type="roles" />;
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Roles</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {roles.length} roles · permissions are assigned per role
          </p>
        </div>
        {hasPermission('roles.manage') && (
          <button
            onClick={() => navigate('/roles/new')}
            className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors text-sm font-medium w-full sm:w-auto"
          >
            <Plus size={18} />
            New Role
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {roles.map((role) => (
          <div
            key={role.id}
            className="bg-card rounded-xl shadow-sm border border-border p-5 flex flex-col gap-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {role.is_system ? (
                  <Lock size={16} className="text-muted-foreground shrink-0" />
                ) : (
                  <ShieldCheck size={16} className="text-primary shrink-0" />
                )}
                <h2 className="font-semibold text-foreground truncate">{role.name}</h2>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {canManageRoles && (
                  <button
                    onClick={() => navigate(`/roles/${role.id}/edit`)}
                    className="p-1.5 text-primary hover:bg-primary-soft rounded transition-colors"
                    title="Edit role"
                  >
                    <Edit2 size={16} />
                  </button>
                )}
                {!role.is_system && (
                  <button
                    onClick={() => handleDelete(role.id, role.name, role.is_system, role.user_count ?? 0)}
                    className="p-1.5 text-destructive hover:bg-destructive/10 rounded transition-colors"
                    title="Delete role"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-mono">
                {role.slug}
              </span>
              {role.is_system && (
                <span className="px-2 py-0.5 rounded-full bg-primary-soft text-primary font-medium">
                  system
                </span>
              )}
              <span className="inline-flex items-center gap-1 text-muted-foreground">
                <Users size={12} />
                {role.user_count ?? 0} user{(role.user_count ?? 0) === 1 ? '' : 's'}
              </span>
            </div>

            {role.description && (
              <p className="text-sm text-muted-foreground line-clamp-2">{role.description}</p>
            )}

            <div className="flex flex-wrap gap-1.5 mt-auto">
              {(role.permissions || []).slice(0, 6).map((key) => (
                <span
                  key={key}
                  className="px-2 py-0.5 rounded-full bg-success/15 text-success text-xs font-mono"
                >
                  {key}
                </span>
              ))}
              {(role.permissions || []).length > 6 && (
                <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground text-xs">
                  +{(role.permissions || []).length - 6} more
                </span>
              )}
              {(role.permissions || []).length === 0 && (
                <span className="text-xs text-muted-foreground">No permissions</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {roles.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No roles found. The backend seeds admin, manager, staff and customer on migration.
        </div>
      )}
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Delete Role'}
        message={confirmState?.message}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        busy={confirmBusy}
        onClose={() => { if (!confirmBusy) setConfirmState(null); }}
        onConfirm={runConfirmed}
      />
    </div>
  );
};

export default RoleList;
