from datetime import datetime
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import user as user_repo  # 👈 Use existing user repo
from app.repositories import order as order_repo
from app.repositories import analytics as analytics_repo
from app.repositories import product as product_repo

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


@router.get("", response_model=dict)
def get_admin_dashboard(
    session: SessionDep,
    current_user: User = Depends(require_perm("dashboard.view")),
):
    """
    Get admin dashboard summary (requires dashboard.view permission).
    """
    # User stats
    user_stats = user_repo.get_user_stats(session)
    
    # Order stats
    order_stats = order_repo.get_order_statistics(session)
    
    # Revenue stats
    revenue_stats = analytics_repo.get_dashboard_stats(session)
    
    # Top products by revenue (last 30 days) — consumed by the dashboard widget
    # via `revenue.top_products`. Kept inside `revenue` because the Dashboard
    # page renders <RevenueChart data={dashboardData.revenue} />. Top 4 keeps the
    # ranked list readable (a wider set turns into an unreadable bar chart).
    revenue_stats["top_products"] = analytics_repo.get_dashboard_top_products(
        session, limit=4, days=30
    )
    
    # Recent orders
    recent_orders = order_repo.get_recent_orders(session, limit=10)
    
    # Total products
    total_products = product_repo.get_total_products(session)
    
    # Daily sales trend (last 7 days, zero-filled) for the dashboard chart
    sales_trend = analytics_repo.get_sales_trend(session, days=7)
    
    return {
        "users": user_stats,
        "orders": order_stats,
        "revenue": revenue_stats,
        "total_products": total_products,
        "recent_orders": recent_orders,
        "sales_trend": sales_trend,
        "timestamp": datetime.now().isoformat(),
    }