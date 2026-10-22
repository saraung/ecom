// src/pages/Categories/CategoryList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  Edit,
  Trash2,
  FolderTree,
  ChevronDown,
  ChevronRight,
  FileText,
  Package,
  Eye,
  EyeOff
} from 'lucide-react';
import { getCategories, deleteCategory, updateCategory } from '../../api/categories';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';

const CategoryList = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  // `canManage` is permission-based so a stacked role set (or a `customer`
  // primary role) can't hide the create/edit/delete controls.
  const canManage = canDo(user, 'categories.manage');
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState('');
  const [expandedIds, setExpandedIds] = useState(new Set());
  const [confirmState, setConfirmState] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    fetchCategories();
  }, []);

  const fetchCategories = async () => {
    try {
      setLoading(true);
      const response = await getCategories();
      
      let categoriesData = [];
      if (Array.isArray(response.data)) {
        categoriesData = response.data;
      } else if (response.data?.items) {
        categoriesData = response.data.items;
      } else if (response.data?.data) {
        categoriesData = response.data.data;
      }
      
      setCategories(categoriesData);
    } catch {
      toast.error('Failed to load categories');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (id) => {
    if (!canManage) {
      toast.error('You do not have permission to delete categories');
      return;
    }
    setConfirmState({ kind: 'delete', target: id });
  };

  const runConfirmed = async () => {
    const s = confirmState;
    if (!s) return;
    try {
      setDeleteBusy(true);
      await deleteCategory(s.target);
      toast.success('Category deleted successfully');
      fetchCategories();
    } catch {
      toast.error('Failed to delete category');
    } finally {
      setDeleteBusy(false);
      setConfirmState(null);
    }
  };

  // Navigate to category products page
  const handleViewProducts = (categoryId) => {
    navigate(`/categories/${categoryId}/products`);
  };

  // Row click: parents expand/collapse, leafs open their products —
  // the fastest path into a section (explicit Package button does the same).
  const handleRowClick = (node) => {
    const hasChildren = node.children && node.children.length > 0;
    if (hasChildren) {
      toggleExpand(node.id);
    } else {
      handleViewProducts(node.id);
    }
  };

  // Build category tree
  const buildCategoryTree = (categories) => {
    const categoryMap = {};
    const roots = [];

    categories.forEach(category => {
      categoryMap[category.id] = {
        ...category,
        children: [],
        level: 0
      };
    });

    categories.forEach(category => {
      if (category.parent_id && categoryMap[category.parent_id]) {
        categoryMap[category.parent_id].children.push(categoryMap[category.id]);
        categoryMap[category.id].level = categoryMap[category.parent_id].level + 1;
      } else {
        roots.push(categoryMap[category.id]);
      }
    });

    const byOrder = (a, b) =>
      (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.name.localeCompare(b.name);
    const sortChildren = (node) => {
      node.children.sort(byOrder);
      node.children.forEach(sortChildren);
    };
    roots.sort(byOrder);
    roots.forEach(sortChildren);

    return roots;
  };

  const filterTree = (nodes, searchTerm) => {
    if (!searchTerm) return nodes;
    
    const result = [];
    for (const node of nodes) {
      const nodeMatches = node.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         node.slug.toLowerCase().includes(searchTerm.toLowerCase());
      
      const filteredChildren = filterTree(node.children, searchTerm);
      
      if (nodeMatches || filteredChildren.length > 0) {
        result.push({
          ...node,
          children: filteredChildren
        });
      }
    }
    return result;
  };

  const getTotalProducts = (node) => {
    // Direct counts come from the API (product_count); subtrees sum up,
    // preserving the previous total-including-descendants behavior.
    let count = node.product_count || 0;
    (node.children || []).forEach(child => {
      count += getTotalProducts(child);
    });
    return count;
  };

  const toggleExpand = (id) => {
    const newExpanded = new Set(expandedIds);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedIds(newExpanded);
  };

  // Quick visibility toggle (manager only).
  const handleToggleActive = async (node) => {
    if (!canManage) {
      toast.error('You do not have permission to update categories');
      return;
    }
    try {
      await updateCategory(node.id, { is_active: !(node.is_active !== false) });
      toast.success(node.is_active !== false ? 'Category hidden from storefront' : 'Category visible on storefront');
      fetchCategories();
    } catch {
      toast.error('Failed to update category');
    }
  };

  const expandAll = () => {
    const allIds = new Set();
    const collectIds = (nodes) => {
      nodes.forEach(node => {
        if (node.children.length > 0) {
          allIds.add(node.id);
          collectIds(node.children);
        }
      });
    };
    collectIds(treeData);
    setExpandedIds(allIds);
  };

  const collapseAll = () => {
    setExpandedIds(new Set());
  };

  const treeData = buildCategoryTree(categories);
  const filteredTree = filterTree(treeData, search);

  const countItems = (nodes) => {
    let count = 0;
    nodes.forEach(node => {
      count++;
      count += countItems(node.children);
    });
    return count;
  };

  if (loading) {
    return <PageSkeleton type="categories" />;
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Categories</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {countItems(filteredTree)} categories found
            {categories.length > 0 && ` (${categories.length} total)`}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:flex-wrap w-full sm:w-auto gap-2">
          {filteredTree.length > 0 && (
            <>
              <button
                onClick={expandAll}
                className="px-3 py-2 text-sm text-muted-foreground hover:bg-muted rounded-lg transition"
              >
                Expand All
              </button>
              <button
                onClick={collapseAll}
                className="px-3 py-2 text-sm text-muted-foreground hover:bg-muted rounded-lg transition"
              >
                Collapse All
              </button>
            </>
          )}
          {canManage && (
            <button
              onClick={() => navigate('/categories/new')}
              className="bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors flex items-center gap-2"
            >
              <Plus size={20} />
              Add Category
            </button>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative w-full max-w-md mb-6">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
        <input
          type="text"
          placeholder="Search categories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
      </div>

      {/* Category Tree */}
      <div className="bg-card rounded-xl shadow-sm overflow-hidden">
        {filteredTree.length === 0 ? (
          <div className="px-4 py-12 text-center text-muted-foreground">
            {search ? 'No categories match your search' : 'No categories found. Create your first category!'}
          </div>
        ) : (
          <div className="divide-y divide-border min-w-0">
            {filteredTree.map((node) => (
              <CategoryTreeNode
                key={node.id}
                node={node}
                level={0}
                isExpanded={expandedIds.has(node.id)}
                onToggle={() => toggleExpand(node.id)}
                onRowClick={handleRowClick}
                onEdit={(id) => navigate(`/categories/${id}/edit`)}
                onDelete={handleDelete}
                onToggleActive={handleToggleActive}
                onViewProducts={handleViewProducts}
                getTotalProducts={getTotalProducts}
                canManage={canManage}
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!confirmState}
        busy={deleteBusy}
        title="Delete category"
        message="Are you sure you want to delete this category?"
        confirmLabel="Delete"
        tone="danger"
        onConfirm={runConfirmed}
        onClose={() => { if (!deleteBusy) setConfirmState(null); }}
      />
    </div>
  );
};

// Category Tree Node Component - Updated with row click handling
const CategoryTreeNode = ({
  node,
  level,
  isExpanded,
  onToggle,
  onRowClick,
  onEdit,
  onDelete,
  onToggleActive,
  onViewProducts,
  getTotalProducts,
  canManage
}) => {
  const hasChildren = node.children && node.children.length > 0;
  const totalProducts = getTotalProducts(node);
  const isParent = hasChildren || node.parent_id === null;
  const isActive = node.is_active !== false;
  // If the thumbnail URL fails (hotlink block, dead link), fall back to
  // the default icon instead of hiding — a blank gap looks broken.
  const [imgFailed, setImgFailed] = useState(false);
  const showThumb = !!(node.image_url && !imgFailed);

  const handleRowClick = (e) => {
    // Prevent click if clicking on action buttons
    if (e.target.closest('button')) {
      return;
    }
    onRowClick(node);
  };

  return (
    <div>
      {/* Category Row - Now clickable */}
      <div
        className={`flex items-center gap-2 px-3 sm:px-4 py-3 hover:bg-muted transition-colors cursor-pointer ${
          level > 0 ? 'border-l-2 border-primary/30 ml-4' : ''
        } ${hasChildren ? 'hover:bg-primary-soft/50' : 'hover:bg-muted'}`}
        style={{ paddingLeft: `${16 + level * 24}px` }}
        onClick={handleRowClick}
        role="button"
        tabIndex={0}
        onKeyPress={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onRowClick(node);
          }
        }}
        title={hasChildren ? (isExpanded ? 'Click to collapse' : 'Click to expand') : 'Click to view products'}
      >
        {/* Expand/Collapse Icon */}
        <div className="w-6 shrink-0">
          {hasChildren && (
            <span className="text-muted-foreground">
              {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            </span>
          )}
        </div>

        {/* Icon */}
        <div className="w-7 shrink-0" title={node.image_url ? `Image: ${node.image_url}` : node.name}>
          {showThumb ? (
            <img
              src={node.image_url}
              alt={node.name}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImgFailed(true)}
              className="w-7 h-7 object-cover rounded-md border border-border bg-muted"
            />
          ) : isParent ? (
            <FolderTree size={18} className={level === 0 ? 'text-primary' : 'text-primary'} />
          ) : (
            <FileText size={18} className="text-muted-foreground" />
          )}
        </div>

        {/* Name */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-medium ${level === 0 ? 'text-foreground text-base' : 'text-muted-foreground text-sm'}`}>
              {node.name}
            </span>
            {!isActive && (
              <span className="badge badge-danger text-[10px]">Inactive</span>
            )}
            {hasChildren && (
              <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                {node.children.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground mt-0.5 flex-wrap min-w-0">
            <span className="truncate">slug: {node.slug}</span>
            {totalProducts > 0 && (
              <span className="inline-flex items-center gap-1 text-primary">
                <Package size={12} />
                {totalProducts} product{totalProducts === 1 ? '' : 's'}
              </span>
            )}
          </div>
        </div>

        {/* Actions - Stop propagation on button clicks */}
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          {/* View Products Button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewProducts(node.id);
            }}
            className="p-1.5 text-muted-foreground hover:bg-muted rounded-lg transition"
            title="View products in this category"
          >
            <Package size={16} />
          </button>

          {/* Edit/Delete/Visibility - Only when the role grants categories.manage.
              Order lives in the form's Sort Order field (arrow buttons removed:
              swapping equal default orders was a visible no-op). */}
          {canManage && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleActive(node);
                }}
                className="p-1.5 text-muted-foreground hover:bg-muted rounded-lg transition"
                title={isActive ? 'Hide from storefront' : 'Show on storefront'}
              >
                {isActive ? <Eye size={16} /> : <EyeOff size={16} />}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(node.id);
                }}
                className="p-1.5 text-primary hover:bg-primary-soft rounded-lg transition"
                title="Edit category"
              >
                <Edit size={16} />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(node.id);
                }}
                className="p-1.5 text-destructive hover:bg-destructive/10 rounded-lg transition"
                title="Delete category"
              >
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div className="bg-muted/50">
          {node.children.map((child) => (
            <CategoryTreeNode
              key={child.id}
              node={child}
              level={level + 1}
              isExpanded={isExpanded}
              onToggle={onToggle}
              onRowClick={onRowClick}
              onEdit={onEdit}
              onDelete={onDelete}
              onToggleActive={onToggleActive}
              onViewProducts={onViewProducts}
              getTotalProducts={getTotalProducts}
              canManage={canManage}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default CategoryList;