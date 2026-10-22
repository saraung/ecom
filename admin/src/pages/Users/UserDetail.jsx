// src/pages/Users/UserDetail.jsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ArrowLeft, 
  Mail, 
  User, 
  Calendar, 
  Shield, 
  Edit2, 
  Phone,
  ShoppingBag,
  DollarSign,
  Clock,
  Trash2,
  MapPin,
  Home,
  Building,
  TrendingUp,
  Package,
  Award
} from 'lucide-react';
import { getUserById, getUserOrderStats, getUserAddresses, updateUserStatus, deleteUser } from '../../api/users';
import { getRoles, getUserRoles, setUserRoles } from '../../api/roles';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo, highestLegacyRole } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatPrice, formatDate } from '../../utils/format';

const UserDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user: currentUser, hasPermission } = useAuth();
  const canViewUsers = canDo(currentUser, 'users.view', 'admin');
  const canManageRoles = hasPermission('users.manage_roles');
  const canManageUsers = hasPermission('users.manage');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [user, setUser] = useState(null);
  const [addresses, setAddresses] = useState([]);
  const [loadingAddresses, setLoadingAddresses] = useState(false);
  const [orderStats, setOrderStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [editingRole, setEditingRole] = useState(false);
  const [allRoles, setAllRoles] = useState([]);
  const [rolesFailed, setRolesFailed] = useState(false);
  const [selectedRoles, setSelectedRoles] = useState([]);
  const [confirmState, setConfirmState] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  // The backend rejects ANY self role change (400) — the editor explains
  // instead of letting the admin attempt it.
  const isSelf = user?.id != null && user.id === currentUser?.id;

  // Hooks must be called unconditionally (Rules of Hooks). For unauthorized
  // viewers the effect is a no-op — they hit the Access Denied screen below.
  useEffect(() => {
    if (!canViewUsers) return;
    fetchUser();
    fetchUserAddresses();
    fetchUserOrderStats();
    if (canManageRoles) fetchAllRoles();
  }, [id]);

  if (!canViewUsers) {
    return (
      <div className="text-center py-12">
        <Shield size={48} className="mx-auto text-destructive mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to view user details.</p>
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  const fetchUser = async () => {
    try {
      setLoading(true);
      const response = await getUserById(id);
      setUser(response.data);
      const slugs = response.data.roles?.length
        ? response.data.roles
        : [response.data.role].filter(Boolean);
      setSelectedRoles(slugs);
      // Backfill from the dedicated endpoint when the list payload lacks it.
      if (!response.data.roles) {
        try {
          const rolesResp = await getUserRoles(id);
          setSelectedRoles(rolesResp.data || slugs);
        } catch { /* read-only fallback above is enough */ }
      }
    } catch {
      toast.error('Failed to load user');
      navigate('/users');
    } finally {
      setLoading(false);
    }
  };

  const fetchAllRoles = async () => {
    try {
      const response = await getRoles();
      setAllRoles(response.data || []);
      setRolesFailed(false);
    } catch {
      setAllRoles([]);
      setRolesFailed(true);
    }
  };

  const fetchUserAddresses = async () => {
    try {
      setLoadingAddresses(true);
      // Admin-scoped: view THIS user's addresses (the customer-facing
      // GET /addresses only returns the current user's own addresses).
      const response = await getUserAddresses(id);
      setAddresses(response.data || []);
    } catch {
    } finally {
      setLoadingAddresses(false);
    }
  };

  // GET /admin/users/{user_id}/stats — lifetime order statistics.
  // Non-blocking: if it fails, the Statistics card silently falls back
  // to the old user-profile fields instead of breaking the page.
  const fetchUserOrderStats = async () => {
    try {
      setLoadingStats(true);
      const response = await getUserOrderStats(id);
      setOrderStats(response.data);
    } catch {
    } finally {
      setLoadingStats(false);
    }
  };

  const toggleSelectedRole = (slug) => {
    setSelectedRoles((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]
    );
  };

  const handleRoleUpdate = async () => {
    if (!canManageRoles) {
      toast.error('You do not have permission to update user roles');
      return;
    }

    if (selectedRoles.length === 0) {
      toast.error('Assign at least one role');
      return;
    }

    const current = user.roles?.length ? user.roles : [user.role].filter(Boolean);
    if (
      selectedRoles.length === current.length &&
      selectedRoles.every((s) => current.includes(s))
    ) {
      setEditingRole(false);
      return;
    }

    try {
      setSaving(true);
      const response = await setUserRoles(id, selectedRoles);
      const updated = response.data?.length ? response.data : selectedRoles;
      toast.success('User roles updated');
      // Backend stores the highest-privilege slug in `users.role`; mirror it
      // here so the optimistic session matches what /auth/me will return.
      setUser({ ...user, roles: updated, role: highestLegacyRole(updated) ?? updated[0] });
      setEditingRole(false);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update roles');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = () => {
    if (!canManageUsers) {
      toast.error('You do not have permission to change user status');
      return;
    }

    const newStatus = !user.is_active;
    const action = newStatus ? 'activate' : 'deactivate';
    setConfirmState({
      kind: 'status',
      newStatus,
      action,
      title: newStatus ? 'Activate User' : 'Deactivate User',
      message: `Are you sure you want to ${action} this user?`,
      confirmLabel: newStatus ? 'Activate' : 'Deactivate',
      tone: 'primary',
    });
  };

  const handleDelete = () => {
    if (!canManageUsers) {
      toast.error('You do not have permission to delete users');
      return;
    }

    setConfirmState({
      kind: 'delete',
      title: 'Delete User',
      message: `Are you sure you want to delete user "${user.full_name}"? This action cannot be undone.`,
      confirmLabel: 'Delete',
      tone: 'danger',
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    const target = confirmState;
    try {
      setConfirmBusy(true);
      if (target.kind === 'status') {
        await updateUserStatus(id, target.newStatus);
        toast.success(`User ${target.action}d successfully`);
        setUser({ ...user, is_active: target.newStatus });
      } else {
        await deleteUser(id);
        toast.success('User deleted successfully');
        navigate('/users');
      }
    } catch (error) {
      toast.error(
        error.response?.data?.detail ||
          (target.kind === 'status' ? 'Failed to update user status' : 'Failed to delete user')
      );
    } finally {
      setConfirmBusy(false);
      setConfirmState(null);
    }
  };

  const getRoleBadge = (role) => {
    const colors = {
      admin: 'bg-destructive/15 text-destructive',
      manager: 'bg-purple-500/15 text-purple-600 dark:text-purple-300',
      staff: 'bg-primary-soft text-primary-soft-foreground',
      customer: 'bg-success/15 text-success'
    };
    if (colors[role]) return colors[role];
    // Deterministic tint for custom slugs so they don't all look identical.
    const palette = [
      'bg-blue-500/15 text-blue-600 dark:text-blue-300',
      'bg-amber-500/15 text-amber-600 dark:text-amber-300',
      'bg-teal-500/15 text-teal-600 dark:text-teal-300',
      'bg-pink-500/15 text-pink-600 dark:text-pink-300',
      'bg-cyan-500/15 text-cyan-600 dark:text-cyan-300',
      'bg-orange-500/15 text-orange-600 dark:text-orange-300',
    ];
    let hash = 0;
    for (let i = 0; i < String(role).length; i++) {
      hash = (hash * 31 + String(role).charCodeAt(i)) >>> 0;
    }
    return palette[hash % palette.length];
  };

  const displayRoles = user?.roles?.length ? user.roles : [user?.role].filter(Boolean);

  // most_ordered_product can be a string or an object depending on the
  // backend serializer — handle both shapes defensively.
  const topProductRaw = orderStats?.most_ordered_product;
  const topProductName = typeof topProductRaw === 'string'
    ? topProductRaw
    : (topProductRaw?.product_name || topProductRaw?.name || null);

  const formatCurrency = (amount) => formatPrice(amount, { decimals: 0 });

  if (loading) {
    return <PageSkeleton type="user-detail" />;
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <User size={48} className="mx-auto text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">User not found</h2>
        <button
          onClick={() => navigate('/users')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Users
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-6">
        <button
          onClick={() => navigate('/users')}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to users"
        >
          <ArrowLeft size={24} />
        </button>
        <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words min-w-0">User Details</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6 min-w-0">
        {/* User Profile */}
        <div className="lg:col-span-2 space-y-4 sm:space-y-6 min-w-0">
          {/* Profile Card */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6 min-w-0">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-16 h-16 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-2xl font-bold shrink-0">
                  {user.full_name?.[0] || user.username?.[0] || 'U'}
                </div>
                <div className="min-w-0">
                  <h2 className="text-xl font-bold text-foreground truncate">{user.full_name || user.username}</h2>
                  <p className="text-muted-foreground truncate">@{user.username}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <button
                      onClick={handleToggleStatus}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        user.is_active ? 'bg-success/15 text-success hover:bg-success/20' : 'bg-destructive/15 text-destructive hover:bg-destructive/20'
                      }`}
                    >
                      {user.is_active ? 'Active' : 'Inactive'}
                    </button>
                    {editingRole && canManageRoles ? (
                      <div className="flex flex-col items-start gap-2 p-3 border border-input rounded-lg bg-card">
                        {allRoles.length === 0 && !rolesFailed && (
                          <p className="text-xs text-muted-foreground">Loading roles…</p>
                        )}
                        {allRoles.length === 0 && rolesFailed && (
                          <div className="flex items-center gap-2">
                            <p className="text-xs text-muted-foreground">Couldn&apos;t load roles.</p>
                            <button
                              onClick={fetchAllRoles}
                              className="px-2.5 py-1 border border-input rounded-lg text-xs font-medium hover:bg-muted transition-colors"
                            >
                              Retry
                            </button>
                          </div>
                        )}
                        {allRoles.map((role) => (
                          <label key={role.id} className="flex items-center gap-2 text-xs cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedRoles.includes(role.slug)}
                              onChange={() => toggleSelectedRole(role.slug)}
                              className="accent-primary"
                            />
                            <span className="font-medium text-foreground">{role.name}</span>
                            <span className="text-muted-foreground font-mono">({role.slug})</span>
                          </label>
                        ))}
                        <div className="flex items-center gap-1 mt-1">
                          <button
                            onClick={handleRoleUpdate}
                            disabled={saving || selectedRoles.length === 0}
                            className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {saving ? 'Saving...' : 'Save'}
                          </button>
                          <button
                            onClick={() => { setEditingRole(false); setSelectedRoles(displayRoles); }}
                            className="px-3 py-1.5 border border-input text-muted-foreground rounded-lg text-xs font-medium hover:bg-muted transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {displayRoles.map((r) => (
                          <span
                            key={r}
                            className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${getRoleBadge(r)}`}
                          >
                            {r}
                          </span>
                        ))}
                        {canManageRoles && !isSelf && (
                          <button
                            onClick={() => setEditingRole(true)}
                            className="px-2 py-1 bg-primary-soft text-primary-soft-foreground rounded-full text-xs font-medium flex items-center gap-1 hover:bg-primary-soft/80 transition-colors"
                            title="Edit roles"
                          >
                            <Edit2 size={10} />
                          </button>
                        )}
                        {isSelf && (
                          <span
                            className="px-2 py-1 bg-muted text-muted-foreground rounded-full text-xs"
                            title="The backend rejects role changes on your own account"
                          >
                            Own roles locked
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={handleDelete}
                className="p-2 text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                title="Delete User"
              >
                <Trash2 size={18} />
              </button>
            </div>

            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg min-w-0">
                <Mail size={18} className="text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Email</p>
                  <p className="text-sm font-medium text-foreground truncate">{user.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg min-w-0">
                <Calendar size={18} className="text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Joined</p>
                  <p className="text-sm font-medium text-foreground truncate">
                    {formatDate(user.created_at)}
                  </p>
                </div>
              </div>
              {user.phone && (
                <div className="flex items-center gap-2 p-3 bg-muted rounded-lg min-w-0">
                  <Phone size={18} className="text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">Phone</p>
                    <p className="text-sm font-medium text-foreground truncate">{user.phone}</p>
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2 p-3 bg-muted rounded-lg min-w-0">
                <Shield size={18} className="text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Auth Provider</p>
                  <p className="text-sm font-medium text-foreground capitalize truncate">{user.auth_provider || 'email'}</p>
                </div>
              </div>
            </div>
          </div>

          {/* User Addresses — view only. Adding addresses is a customer
              action (account page / checkout); admins shouldn't do it. */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <MapPin size={20} />
                Saved Addresses ({addresses.length})
              </h2>
            </div>
            {loadingAddresses ? (
              <div className="text-center py-4">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary mx-auto"></div>
                <p className="text-sm text-muted-foreground mt-2">Loading addresses...</p>
              </div>
            ) : addresses.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground">
                <Home size={32} className="mx-auto text-muted-foreground mb-2" />
                <p>No saved addresses</p>
              </div>
            ) : (
              <div className="space-y-3">
                {addresses.map((address) => (
                  <div 
                    key={address.id} 
                    className={`p-4 rounded-lg border ${address.is_default ? 'border-primary/50 bg-primary-soft' : 'border-border bg-muted'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2 min-w-0">
                        {address.is_default ? (
                          <Home size={16} className="text-primary mt-0.5 shrink-0" />
                        ) : (
                          <Building size={16} className="text-muted-foreground mt-0.5 shrink-0" />
                        )}
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-foreground">
                              {address.label || 'Address'}
                            </p>
                            {address.is_default && (
                              <span className="px-2 py-0.5 bg-primary-soft text-primary rounded-full text-xs font-medium">
                                Default
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground break-words">{address.line1}</p>
                          {address.line2 && (
                            <p className="text-sm text-muted-foreground break-words">{address.line2}</p>
                          )}
                          <p className="text-sm text-muted-foreground break-words">
                            {address.city}, {address.state} {address.postal_code}
                          </p>
                          <p className="text-sm text-muted-foreground break-words">{address.country}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* User Stats */}
        <div className="space-y-4 sm:space-y-6 min-w-0">
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Statistics</h2>
            {loadingStats ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                    <ShoppingBag size={16} />
                    Total Orders
                  </span>
                  <span className="font-bold text-foreground shrink-0">
                    {orderStats?.total_orders ?? user.orders_count ?? 0}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                    <DollarSign size={16} />
                    Total Spent
                  </span>
                  <span className="font-bold text-foreground shrink-0">
                    {formatCurrency(orderStats?.total_spent ?? user.total_spent)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                    <TrendingUp size={16} />
                    Avg Order Value
                  </span>
                  <span className="font-bold text-foreground shrink-0">
                    {formatCurrency(orderStats?.average_order_value)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                    <Package size={16} />
                    Items Purchased
                  </span>
                  <span className="font-bold text-foreground shrink-0">
                    {orderStats?.total_items_purchased ?? 0}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                  <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                    <Clock size={16} />
                    Last Order
                  </span>
                  <span className="font-medium text-foreground text-right min-w-0 truncate">
                    {(orderStats?.last_order || user.last_order)
                      ? formatDate(orderStats?.last_order || user.last_order)
                      : 'Never'}
                  </span>
                </div>
                {topProductName && (
                  <div className="flex items-center justify-between gap-3 p-3 bg-muted rounded-lg">
                    <span className="text-sm text-muted-foreground flex items-center gap-2 shrink-0">
                      <Award size={16} />
                      Top Product
                    </span>
                    <span
                      className="font-medium text-foreground text-right min-w-0 truncate"
                      title={topProductName}
                    >
                      {topProductName}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Actions</h2>
            <div className="space-y-2">
              <button
                onClick={() => navigate(`/users`)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors"
              >
                <ArrowLeft size={18} />
                Back to Users
              </button>
            </div>
          </div>
        </div>
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Confirm'}
        message={confirmState?.message}
        confirmLabel={confirmState?.confirmLabel || 'Confirm'}
        cancelLabel="Cancel"
        tone={confirmState?.tone || 'danger'}
        busy={confirmBusy}
        onClose={() => { if (!confirmBusy) setConfirmState(null); }}
        onConfirm={runConfirmed}
      />
    </div>
  );
};

export default UserDetail;