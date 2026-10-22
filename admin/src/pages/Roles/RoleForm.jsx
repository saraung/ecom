// src/pages/Roles/RoleForm.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, RefreshCw, ShieldCheck } from 'lucide-react';
import { getPermissions, getRoleById, createRole, updateRole } from '../../api/roles';
import { useAuth } from '../../context/AuthContext';
import { canDo, groupPermissionsByModule } from '../../utils/permissions';
import { currencySymbol } from '../../utils/format';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const RoleForm = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const { user } = useAuth();
  const isEdit = !!id;

  const allowed = canDo(user, 'roles.manage', 'admin');

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState([]);
  const [catalogError, setCatalogError] = useState(false);
  const [isSystem, setIsSystem] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    slug: '',
    description: '',
    permission_keys: [],
    max_refund_amount: '',
  });
  // Snapshot for the unsaved-changes guard on Cancel/back.
  const [initialData, setInitialData] = useState({
    name: '',
    slug: '',
    description: '',
    permission_keys: [],
    max_refund_amount: '',
  });
  const [confirmState, setConfirmState] = useState(null);

  useEffect(() => {
    // Never fire API calls for sessions that fail the gate below.
    if (!allowed) return;
    fetchCatalog();
    if (isEdit) fetchRole();
  }, [id, allowed]);

  if (!allowed) {
    return (
      <div className="text-center py-12">
        <ShieldCheck size={48} className="mx-auto text-destructive mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to manage roles.</p>
        <button
          onClick={() => navigate('/roles')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Roles
        </button>
      </div>
    );
  }

  const fetchCatalog = async () => {
    try {
      const response = await getPermissions();
      setCatalog(response.data || []);
      setCatalogError(false);
    } catch {
      setCatalogError(true);
      toast.error('Failed to load permission catalog');
    }
  };

  const fetchRole = async () => {
    try {
      setLoading(true);
      const response = await getRoleById(id);
      const role = response.data;
      setIsSystem(!!role.is_system);
      const loaded = {
        name: role.name || '',
        slug: role.slug || '',
        description: role.description || '',
        permission_keys: role.permissions || [],
        max_refund_amount: role.max_refund_amount != null ? String(role.max_refund_amount) : '',
      };
      setFormData(loaded);
      setInitialData(loaded);
    } catch {
      toast.error('Failed to load role');
      navigate('/roles');
    } finally {
      setLoading(false);
    }
  };

  const isDirty =
    JSON.stringify(formData) !== JSON.stringify(initialData);

  const handleCancel = () => {
    if (isDirty) {
      setConfirmState({
        title: 'Discard Changes',
        message: 'Discard unsaved changes to this role?',
      });
      return;
    }
    navigate('/roles');
  };

  const runConfirmed = async () => {
    setConfirmState(null);
    navigate('/roles');
  };

  // Blank = unlimited (null). Returns undefined + toast on invalid input.
  const parseRefundLimit = () => {
    if (formData.max_refund_amount === '') return null;
    const num = parseFloat(formData.max_refund_amount);
    if (!Number.isFinite(num) || num < 0) {
      toast.error('Max auto-refund must be a number ≥ 0 (or blank for unlimited)');
      return undefined;
    }
    return num;
  };

  const togglePermission = (key) => {
    setFormData((prev) => ({
      ...prev,
      permission_keys: prev.permission_keys.includes(key)
        ? prev.permission_keys.filter((k) => k !== key)
        : [...prev.permission_keys, key],
    }));
  };

  const toggleModule = (items) => {
    const keys = items.map((p) => p.key);
    const allSelected = keys.every((k) => formData.permission_keys.includes(k));
    setFormData((prev) => ({
      ...prev,
      permission_keys: allSelected
        ? prev.permission_keys.filter((k) => !keys.includes(k))
        : [...new Set([...prev.permission_keys, ...keys])],
    }));
  };

  const handleNameChange = (e) => {
    const name = e.target.value;
    setFormData((prev) => ({
      ...prev,
      name,
      // Keep slug editable after first touch: only auto-derive on create.
      slug: !isEdit
        ? name.toLowerCase().trim().replace(/\s+/g, '-').replace(/[^a-z0-9-_]/g, '')
        : prev.slug,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      toast.error('Role name is required');
      return;
    }
    const refundLimit = parseRefundLimit();
    if (refundLimit === undefined) return;
    try {
      setSaving(true);
      if (isEdit) {
        await updateRole(id, {
          name: formData.name.trim(),
          description: formData.description || null,
          permission_keys: formData.permission_keys,
          max_refund_amount: refundLimit,
        });
        toast.success('Role updated successfully');
      } else {
        await createRole({
          name: formData.name.trim(),
          slug: formData.slug || undefined,
          description: formData.description || undefined,
          permission_keys: formData.permission_keys,
          max_refund_amount: refundLimit,
        });
        toast.success('Role created successfully');
      }
      navigate('/roles');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save role');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <PageSkeleton type="role-form" title={isEdit ? 'Edit Role' : 'Create New Role'} />;
  }

  const groups = groupPermissionsByModule(catalog);

  return (
    <div className="pb-8">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3">
        <button
          onClick={handleCancel}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to roles"
        >
          <ArrowLeft size={18} />
        </button>
        <h1 className="text-lg font-bold text-foreground break-words min-w-0 flex-1 basis-40">
          {isEdit ? `Edit Role — ${formData.name}` : 'Create New Role'}
        </h1>
        {isSystem && (
          <span className="px-2 py-0.5 rounded-full bg-primary-soft text-primary text-xs font-medium shrink-0">
            system role — permissions editable, deletion disabled
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={handleNameChange}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="Warehouse Packer"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Slug {isEdit && <span className="text-xs">(locked after creation)</span>}
              </label>
              <input
                type="text"
                value={formData.slug}
                disabled={isEdit}
                onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent font-mono disabled:opacity-60"
                placeholder="warehouse-packer"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="What is this role for?"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Max auto-refund ({currencySymbol()}) — blank = unlimited
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={formData.max_refund_amount}
                onChange={(e) => setFormData({ ...formData, max_refund_amount: e.target.value })}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="e.g. 5000"
              />
              <p className="text-xs text-muted-foreground mt-1">Above-limit or self-order refunds stage for a second admin.</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-foreground">
              Permissions{' '}
              <span className="text-sm font-normal text-muted-foreground">
                ({formData.permission_keys.length} selected)
              </span>
            </h2>
            <button
              type="button"
              onClick={() => setFormData({ ...formData, permission_keys: [] })}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear all
            </button>
          </div>
          <div className="space-y-5">
            {groups.map((group) => {
              const keys = group.items.map((p) => p.key);
              const selected = keys.filter((k) => formData.permission_keys.includes(k)).length;
              return (
                <div key={group.module} className="border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-foreground">
                      {group.label}{' '}
                      <span className="font-normal text-muted-foreground">
                        ({selected}/{keys.length})
                      </span>
                    </h3>
                    <button
                      type="button"
                      onClick={() => toggleModule(group.items)}
                      className="text-xs text-primary hover:text-primary-hover font-medium"
                    >
                      {selected === keys.length ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {group.items.map((perm) => (
                      <label
                        key={perm.key}
                        className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                          formData.permission_keys.includes(perm.key)
                            ? 'border-primary/50 bg-primary-soft'
                            : 'border-border hover:bg-muted'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={formData.permission_keys.includes(perm.key)}
                          onChange={() => togglePermission(perm.key)}
                          className="mt-0.5 accent-primary"
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-foreground">{perm.label}</span>
                          <span className="block text-xs text-muted-foreground font-mono truncate">
                            {perm.key}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
            {groups.length === 0 && catalogError && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                <p className="text-sm text-muted-foreground flex-1">
                  Permission catalog failed to load. Check the backend /admin/permissions endpoint.
                </p>
                <button
                  type="button"
                  onClick={fetchCatalog}
                  className="px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium shrink-0"
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="bg-card rounded-xl shadow-sm border border-border p-3 flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
          <button
            type="button"
            onClick={handleCancel}
            className="px-4 py-1.5 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
          >
            {saving ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save size={16} />
                {isEdit ? 'Update Role' : 'Create Role'}
              </>
            )}
          </button>
        </div>
      </form>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Discard Changes'}
        message={confirmState?.message}
        confirmLabel="Discard changes"
        cancelLabel="Cancel"
        tone="neutral"
        onClose={() => setConfirmState(null)}
        onConfirm={runConfirmed}
      />
    </div>
  );
};

export default RoleForm;
