# app/core/rbac_catalog.py
"""Single source of truth for the RBAC permission catalog and system roles.

- ``PERMISSIONS``: every permission key the codebase understands. New keys are
  added here (by developers) + a migration seeds them. The admin dashboard
  never invents keys — it only ticks checkboxes from this list.
- ``SYSTEM_ROLES``: slug -> permission keys granted to the 4 legacy roles.
  Mirrors the old ``require_role(...)`` hierarchy so the migration is
  behavior-preserving.
"""

# (key, label, module, description)
PERMISSIONS: list[tuple[str, str, str, str]] = [
    # Dashboard / analytics
    ("dashboard.view", "View dashboard", "dashboard", "Access the admin dashboard overview"),
    ("reports.view", "View reports", "reports", "Access sales/order/customer reports"),
    # Products
    ("products.view", "View products", "products", "List and view products in admin"),
    ("products.create", "Create products", "products", "Create new products and variants"),
    ("products.update", "Update products", "products", "Edit products, variants and bulk status"),
    ("products.delete", "Delete products", "products", "Delete products (single + bulk)"),
    ("products.export", "Export products", "products", "Export product catalog"),
    ("products.manage_prices", "Manage product prices", "products", "Change product and variant prices"),
    ("inventory.adjust", "Adjust inventory", "inventory", "Adjust variant stock levels"),
    ("product_images.manage", "Manage product images", "products", "Add/update/delete/reorder product images"),
    # Categories
    ("categories.view", "View categories", "categories", "List categories in admin"),
    ("categories.manage", "Manage categories", "categories", "Create/update/delete categories"),
    # Orders
    ("orders.view", "View orders", "orders", "List and view order details + stats"),
    ("orders.update", "Update orders", "orders", "Change order status, cancel, collect COD"),
    ("orders.refund", "Refund orders", "orders", "Issue refunds on paid orders"),
    ("shipping.manage", "Manage shipping", "shipping", "Shiprocket dispatch, AWB, pickup, simulator"),
    # COD reconciliation (courier remittance, separate from customer collection)
    ("cod.view", "View COD reconciliation", "cod", "View COD collection and remittance batches"),
    ("cod.reconcile", "Reconcile COD remittances", "cod", "Import batches, confirm bank receipts and resolve discrepancies"),
    # Coupons / promotions
    ("coupons.view", "View coupons", "coupons", "List and view coupons"),
    ("coupons.manage", "Manage coupons", "coupons", "Create/update/delete coupons"),
    ("promotions.send", "Send promotions", "promotions", "Send promotional broadcasts and test emails"),
    # Users
    ("users.view", "View users", "users", "List users, details, addresses, order stats"),
    ("users.manage", "Manage users", "users", "Activate/deactivate and delete users"),
    ("users.manage_roles", "Manage user roles", "users", "Assign roles to users"),
    # Roles & permissions
    ("roles.manage", "Manage roles", "roles", "Create/update/delete roles and their permissions"),
    # Reviews / payments / notifications / settings
    ("reviews.moderate", "Moderate reviews", "reviews", "Reserved for review moderation endpoints"),
    ("content.manage", "Manage content", "content", "Create/edit storefront content blocks and banners"),
    ("payments.view", "View payments", "payments", "Reserved for payment inspection endpoints"),
    ("notifications.manage", "Manage notifications", "notifications", "Admin notification endpoints"),
    ("settings.manage", "Manage settings", "settings", "Access admin settings pages"),
]

PERMISSION_KEYS: list[str] = [key for key, _, _, _ in PERMISSIONS]

# Legacy hierarchy preserved:
#   admin   = everything
#   manager = everything except users.manage*, roles.manage, settings.manage,
#             products.delete/export
#   staff   = products + categories view + orders view + images
#   customer = no admin permissions
_MANAGER_PERMS: list[str] = [
    "dashboard.view",
    "reports.view",
    "products.view",
    "products.create",
    "products.update",
    "products.manage_prices",
    "inventory.adjust",
    "product_images.manage",
    "categories.view",
    "categories.manage",
    "orders.view",
    "orders.update",
    "orders.refund",
    "shipping.manage",
    "cod.view",
    "cod.reconcile",
    "coupons.view",
    "coupons.manage",
    "promotions.send",
    "content.manage",
    "users.view",
    "notifications.manage",
]

_STAFF_PERMS: list[str] = [
    "products.view",
    "products.create",
    "products.update",
    "product_images.manage",
    "categories.view",
    "orders.view",
]

SYSTEM_ROLES: dict[str, dict] = {
    "admin": {
        "name": "Admin",
        "description": "Full access to everything (system role)",
        "permissions": list(PERMISSION_KEYS),
        # None = unlimited single-refund auto-approval.
        "max_refund_amount": None,
    },
    "manager": {
        "name": "Manager",
        "description": "Manages catalog, orders, coupons and reports (system role)",
        "permissions": _MANAGER_PERMS,
        "max_refund_amount": 5000,
    },
    "staff": {
        "name": "Staff",
        "description": "Handles products and views orders (system role)",
        "permissions": _STAFF_PERMS,
        # 0 = may never execute a refund alone (holds no refund permission
        # anyway); any refund they request needs a second admin.
        "max_refund_amount": 0,
    },
    "customer": {
        "name": "Customer",
        "description": "Shopper account, no admin access (system role)",
        "permissions": [],
        "max_refund_amount": 0,
    },
}
