# app/schemas/analytics.py (or wherever your schemas are)

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SalesSummary(BaseModel):
    total_sales: float
    order_count: int
    average_order_value: float


class SalesPeriodData(BaseModel):
    period: str
    total_sales: float
    order_count: int
    average_order_value: float


class SalesReportResponse(BaseModel):
    summary: SalesSummary
    period_data: List[SalesPeriodData]


# 👇 UPDATED: Add missing fields
class TopProductItem(BaseModel):
    product_id: str
    product_name: str
    product_slug: str
    total_quantity_sold: int
    total_revenue: float
    average_price: float
    order_count: int = 0  # 👈 ADDED
    variant_count: int = 0  # 👈 ADDED

    class Config:
        from_attributes = True  # For ORM compatibility


class OrderStatusStats(BaseModel):
    status: str
    count: int
    revenue: float


class OrderStatisticsResponse(BaseModel):
    total_orders: int
    by_status: List[OrderStatusStats]


class RevenuePeriodData(BaseModel):
    period: str
    revenue: float
    discounts: float
    tax: float
    shipping: float
    net_revenue: float
    refunds: float = 0


class RevenueReportResponse(BaseModel):
    period_data: List[RevenuePeriodData]


class CustomerSummaryResponse(BaseModel):
    total_customers: int
    active_customers: int
    new_customers: int
    repeat_customers: int
    customer_retention_rate: float


class DashboardStatsResponse(BaseModel):
    today: dict
    this_week: dict
    this_month: dict
    total: dict
