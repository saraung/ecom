from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import analytics as analytics_repo
from app.schemas.analytics import (
    CustomerSummaryResponse,
    DashboardStatsResponse,
    OrderStatisticsResponse,
    RevenueReportResponse,
    SalesReportResponse,
    TopProductItem,
)


router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _validate_range(from_date, to_date):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "from_date cannot be greater than to_date")


@router.get("/dashboard", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("dashboard.view")
    ),
):
    """
    Get dashboard statistics.
    """
    return analytics_repo.get_dashboard_stats(session)


@router.get("/sales", response_model=SalesReportResponse)
def get_sales_report(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("reports.view")
    ),
    from_date: date = Query(default=...),
    to_date: date = Query(default=...),
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
):
    """
    Get sales report for a date range.
    
    Allowed:
        manager
        admin
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be greater than to_date"
        )
    
    return analytics_repo.get_sales_report(session, from_date, to_date, group_by)


@router.get("/top-products", response_model=list[TopProductItem])
def get_top_products(
    session: SessionDep,
    current_user: User = Depends(require_perm("reports.view")),  # 👈 ADD THIS BACK
    limit: int = Query(default=10, ge=1, le=100),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
):
    """
    Get top selling products.
    
    Allowed:
        manager
        admin
    """
    _validate_range(from_date, to_date)
    products = analytics_repo.get_top_products(session, limit, from_date, to_date)
    
    return products


@router.get("/orders", response_model=OrderStatisticsResponse)
def get_order_statistics(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("reports.view")
    ),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
):
    """
    Get order statistics by status.
    
    Allowed:
        manager
        admin
    """
    _validate_range(from_date, to_date)
    return analytics_repo.get_order_statistics(session, from_date, to_date)


@router.get("/revenue", response_model=RevenueReportResponse)
def get_revenue_report(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("reports.view")
    ),
    from_date: date = Query(default=...),
    to_date: date = Query(default=...),
    group_by: str = Query(default="day", pattern="^(day|week|month)$"),
):
    """
    Get revenue report.
    
    Allowed:
        manager
        admin
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be greater than to_date"
        )
    
    return analytics_repo.get_revenue_report(session, from_date, to_date, group_by)


@router.get("/customers", response_model=CustomerSummaryResponse)
def get_customer_summary(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("reports.view")
    ),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
):
    """
    Get customer analytics summary.
    
    Allowed:
        manager
        admin
    """
    _validate_range(from_date, to_date)
    return analytics_repo.get_customer_summary(session, from_date, to_date)
