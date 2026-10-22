// src/pages/Users/UserList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Mail, User, Shield, Eye, Filter, ChevronDown } from 'lucide-react';
import { getUsers, deleteUser, updateUserStatus } from '../../api/users';
import { getRoles } from '../../api/roles';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatDate } from '../../utils/format';

const UserList = () => {
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const canManageUsers = hasPermission('users.manage');
  const canViewUsers = canDo(user, 'users.view', 'admin');
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const itemsPerPage = 10;

  // Role filter options come from the dynamic role catalog; the 4 legacy
  // roles are the fallback when the endpoint is unreachable.
  const [roleOptions, setRoleOptions] = useState([
    { value: '', label: 'All Roles' },
    { value: 'admin', label: 'Admin' },
    { value: 'manager', label: 'Manager' },
    { value: 'staff', label: 'Staff' },
    { value: 'customer', label: 'Customer' }
  ]);

  const statusOptions = [
    { value: '', label: 'All Status' },
    { value: 'true', label: 'Active' },
    { value: 'false', label: 'Inactive' }
  ];

  useEffect(() => {
    fetchUsers();
  }, [currentPage, roleFilter, statusFilter]);

  useEffect(() => {
    // Load the dynamic role catalog once for the filter dropdown.
    if (!canViewUsers) return;
    getRoles()
      .then((response) => {
        const roles = response.data || [];
        if (roles.length > 0) {
          setRoleOptions([
            { value: '', label: 'All Roles' },
            ...roles.map((r) => ({ value: r.slug, label: r.name })),
          ]);
        }
      })
      .catch(() => { /* legacy fallback options stay */ });
  }, []);

  const fetchUsers = async () => {
    // Never fire the API for sessions that fail the gate below.
    if (!canViewUsers) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const params = {
        page: currentPage,
        limit: itemsPerPage,
        search: search || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter ? statusFilter === 'true' : undefined
      };
      
      const response = await getUsers(params);
      
      const data = response.data;
      setUsers(data.users || []);
      setTotalUsers(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch {
      toast.error('Failed to load users');
      setUsers([]);
      setTotalUsers(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    setCurrentPage(1);
    fetchUsers();
  };

  const handleDelete = (id, fullName) => {
    if (!canManageUsers) {
      toast.error('You do not have permission to delete users');
      return;
    }
    setConfirmState({
      id,
      title: 'Delete User',
      message: `Are you sure you want to delete user "${fullName}"? This action cannot be undone.`,
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    try {
      setConfirmBusy(true);
      await deleteUser(confirmState.id);
      toast.success('User deleted successfully');
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete user');
    } finally {
      setConfirmBusy(false);
      setConfirmState(null);
    }
  };

  const handleToggleStatus = async (id, currentStatus) => {
    if (!canManageUsers) {
      toast.error('You do not have permission to change user status');
      return;
    }
    
    const newStatus = !currentStatus;
    try {
      await updateUserStatus(id, newStatus);
      toast.success(`User ${newStatus ? 'activated' : 'deactivated'} successfully`);
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update user status');
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

  if (!canViewUsers) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to view users.
      </div>
    );
  }

  if (loading) {
    return <PageSkeleton type="users" />;
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Users</h1>
          <p className="text-sm text-muted-foreground mt-1">{totalUsers} users found</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-4 mb-6">
        <div className="relative w-full sm:flex-1 sm:max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
          <input
            type="text"
            placeholder="Search users by name, email, or username..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>

        <div className="grid grid-cols-2 sm:flex gap-2">
        {/* Role Filter */}
        <div className="relative min-w-0">
          <button
            onClick={() => setShowRoleDropdown(!showRoleDropdown)}
            className="flex items-center justify-center sm:justify-start gap-2 px-3 sm:px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors w-full sm:w-auto text-sm"
          >
            <Shield size={18} className="shrink-0" />
            <span className="truncate">{roleOptions.find(r => r.value === roleFilter)?.label || 'All Roles'}</span>
            <ChevronDown size={16} className="shrink-0" />
          </button>
          {showRoleDropdown && (
            <div className="absolute top-full left-0 right-0 sm:right-auto mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-[150px]">
              {roleOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => {
                    setRoleFilter(option.value);
                    setShowRoleDropdown(false);
                    setCurrentPage(1);
                    fetchUsers();
                  }}
                  className={`w-full text-left px-4 py-2 text-foreground hover:bg-muted transition-colors ${
                    roleFilter === option.value ? 'bg-primary-soft text-primary' : ''
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Status Filter */}
        <div className="relative min-w-0">
          <button
            onClick={() => setShowStatusDropdown(!showStatusDropdown)}
            className="flex items-center justify-center sm:justify-start gap-2 px-3 sm:px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors w-full sm:w-auto text-sm"
          >
            <Filter size={18} className="shrink-0" />
            <span className="truncate">{statusOptions.find(s => s.value === statusFilter)?.label || 'All Status'}</span>
            <ChevronDown size={16} className="shrink-0" />
          </button>
          {showStatusDropdown && (
            <div className="absolute top-full left-0 right-0 sm:right-auto mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-[150px]">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => {
                    setStatusFilter(option.value);
                    setShowStatusDropdown(false);
                    setCurrentPage(1);
                    fetchUsers();
                  }}
                  className={`w-full text-left px-4 py-2 text-foreground hover:bg-muted transition-colors ${
                    statusFilter === option.value ? 'bg-primary-soft text-primary' : ''
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
        </div>
      </div>

      <div className="bg-card rounded-xl shadow-sm overflow-hidden">
        {/* Desktop Table View */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Role</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Joined</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-muted-foreground">
                    No users found
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} className="hover:bg-muted transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground dark:text-black font-semibold">
                          {user.full_name?.[0] || user.username?.[0] || 'U'}
                        </div>
                        <div>
                          <div className="font-medium text-foreground">{user.full_name || user.username}</div>
                          <div className="text-sm text-muted-foreground">@{user.username}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Mail size={14} className="text-muted-foreground" />
                        <span className="text-muted-foreground">{user.email}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex flex-wrap gap-1">
                        {(user.roles?.length ? user.roles : [user.role].filter(Boolean)).map((r) => (
                          <span key={r} className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${getRoleBadge(r)}`}>
                            {r}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggleStatus(user.id, user.is_active)}
                        className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                          user.is_active ? 'bg-success/15 text-success hover:bg-success/20' : 'bg-destructive/15 text-destructive hover:bg-destructive/20'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => navigate(`/users/${user.id}`)}
                          className="p-1 text-primary hover:bg-primary-soft rounded transition-colors"
                          title="View User"
                        >
                          <Eye size={18} />
                        </button>
                        {canManageUsers && (
                          <button
                            onClick={() => handleDelete(user.id, user.full_name || user.username)}
                            className="p-1 text-destructive hover:bg-destructive/10 rounded transition-colors"
                            title="Delete User"
                          >
                            <Trash2 size={18} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Card View */}
        <div className="md:hidden divide-y divide-border">
          {users.length === 0 ? (
            <div className="px-4 py-8 text-center text-muted-foreground">
              No users found
            </div>
          ) : (
            users.map((user) => (
              <div key={user.id} className="p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-semibold shrink-0">
                    {user.full_name?.[0] || user.username?.[0] || 'U'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground truncate">{user.full_name || user.username}</div>
                    <div className="text-sm text-muted-foreground truncate">@{user.username}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex flex-wrap gap-1">
                    {(user.roles?.length ? user.roles : [user.role].filter(Boolean)).map((r) => (
                      <span key={r} className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${getRoleBadge(r)}`}>
                        {r}
                      </span>
                    ))}
                  </span>
                  <button
                    onClick={() => handleToggleStatus(user.id, user.is_active)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      user.is_active ? 'bg-success/15 text-success hover:bg-success/20' : 'bg-destructive/15 text-destructive hover:bg-destructive/20'
                    }`}
                  >
                    {user.is_active ? 'Active' : 'Inactive'}
                  </button>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {formatDate(user.created_at)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="text-sm text-muted-foreground truncate min-w-0">{user.email}</div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => navigate(`/users/${user.id}`)}
                      className="p-1.5 text-primary hover:bg-primary-soft rounded transition-colors"
                      title="View User"
                    >
                      <Eye size={18} />
                    </button>
                    {canManageUsers && (
                      <button
                        onClick={() => handleDelete(user.id, user.full_name || user.username)}
                        className="p-1.5 text-destructive hover:bg-destructive/10 rounded transition-colors"
                        title="Delete User"
                      >
                        <Trash2 size={18} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, totalUsers)} of {totalUsers} users
            </div>
            <div className="flex gap-2">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(p => p - 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(p => p + 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={!!confirmState}
        title={confirmState?.title || 'Delete User'}
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

export default UserList;