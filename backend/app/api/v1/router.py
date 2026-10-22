from fastapi import APIRouter
from app.api.v1 import auth,product,product_images,categories,cart,checkout,address,orders,payments,webhooks,reviews,wishlist,coupons,email,analytics,chat,notifications,invites,content,mcp
from app.api.v1.admin import dashboard, orders as admin_orders, users as admin_users, products as admin_products, notifications as admin_notifications
from app.api.v1.admin import content as admin_content
from app.api.v1.admin import cod as admin_cod
from app.api.v1.admin import roles as admin_roles
from app.api.v1.admin import refunds as admin_refunds
from app.api.v1.admin import audit as admin_audit
from app.api.v1.admin import reviews as admin_reviews
from app.api.v1.admin import settings as admin_settings
from app.api.v1 import returns
from app.api.v1.admin import returns as admin_returns

api_router=APIRouter()


api_router.include_router(auth.router)
api_router.include_router(product.router)
api_router.include_router(categories.router)
api_router.include_router(product_images.router)
api_router.include_router(cart.router)
api_router.include_router(checkout.router)
api_router.include_router(address.router)
api_router.include_router(orders.router)
api_router.include_router(returns.router)
api_router.include_router(payments.router)
api_router.include_router(webhooks.router)
api_router.include_router(reviews.router)
api_router.include_router(wishlist.router)
api_router.include_router(coupons.router)
api_router.include_router(email.router)  # Add this
api_router.include_router(analytics.router)
api_router.include_router(chat.router)
api_router.include_router(notifications.router)
api_router.include_router(content.router)  # /content/blocks (public)

# Admin APIs
api_router.include_router(dashboard.router)        # /admin/dashboard
api_router.include_router(admin_orders.router)     # /admin/orders
api_router.include_router(admin_users.router)      # /admin/users
api_router.include_router(admin_products.router)   # /admin/products
api_router.include_router(admin_notifications.router)  # /admin/notifications
api_router.include_router(admin_cod.router)        # /admin/cod
api_router.include_router(admin_roles.router)      # /admin/roles, /admin/permissions
api_router.include_router(admin_refunds.router)    # /admin/refunds, /admin/orders/{id}/cancel
api_router.include_router(admin_audit.router)      # /admin/audit-log
api_router.include_router(admin_reviews.router)    # /admin/reviews
api_router.include_router(admin_settings.router)  # /admin/settings/store
api_router.include_router(admin_content.router)   # /admin/content
api_router.include_router(admin_returns.router)
api_router.include_router(invites.router)          # /admin/invites, /invites/accept
api_router.include_router(mcp.router)              # /mcp/chat (MCP agent)
