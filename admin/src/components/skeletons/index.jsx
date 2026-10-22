// src/components/skeletons/index.jsx
// Central registry for page-shaped loading skeletons.
//
// Each feature keeps its skeleton implementations in its own file; this file
// only maps the public `type` strings used by pages to those components.
import React from 'react';
import { DashboardSkeleton } from './dashboard';
import { ProductsSkeleton, ProductDetailSkeleton, ProductFormSkeleton } from './products';
import { OrdersSkeleton, OrderDetailSkeleton } from './orders';
import { ReturnListSkeleton, ReturnDetailSkeleton } from './returns';
import { UsersSkeleton, UserDetailSkeleton } from './users';
import { CouponsSkeleton, CouponFormSkeleton } from './coupons';
import { CategoriesSkeleton, CategoryProductsSkeleton, CategoryFormSkeleton } from './categories';
import { ReportsSkeleton } from './reports';
import { SettingsSkeleton } from './settings';
import { PromotionsSkeleton } from './promotions';
import { RolesSkeleton, RoleFormSkeleton } from './roles';
import { ShippingSimulatorSkeleton } from './shipping';
import { AuditLogSkeleton } from './audit';
import { InvitesSkeleton } from './invites';
import { RefundsSkeleton } from './refunds';
import { ReviewsSkeleton } from './reviews';
import { StoreSettingsSkeleton } from './store-settings';
import { BannersSkeleton, ContentFormSkeleton } from './content';
import { McpAgentSkeleton } from './mcp-agent';
import {
  CodReconciliationSkeleton,
  CodDetailSkeleton,
  CodImportSkeleton,
  CodManualBatchSkeleton,
} from './cod';

// One entry per sidebar tab / sub-page, each rendering the skeleton that
// mirrors that page's real UI. Generic aliases are kept for compatibility.
const SKELETONS = {
  dashboard: DashboardSkeleton,
  products: ProductsSkeleton,
  orders: OrdersSkeleton,
  returns: ReturnListSkeleton,
  'return-detail': ReturnDetailSkeleton,
  users: UsersSkeleton,
  coupons: CouponsSkeleton,
  categories: CategoriesSkeleton,
  'category-products': CategoryProductsSkeleton,
  reports: ReportsSkeleton,
  settings: SettingsSkeleton,
  promotions: PromotionsSkeleton,
  'product-detail': ProductDetailSkeleton,
  'order-detail': OrderDetailSkeleton,
  'user-detail': UserDetailSkeleton,
  'product-form': ProductFormSkeleton,
  'coupon-form': CouponFormSkeleton,
  'category-form': CategoryFormSkeleton,
  roles: RolesSkeleton,
  'role-form': RoleFormSkeleton,
  'shipping-simulator': ShippingSimulatorSkeleton,
  refunds: RefundsSkeleton,
  cod: CodReconciliationSkeleton,
  'cod-detail': CodDetailSkeleton,
  'cod-import': CodImportSkeleton,
  'cod-manual': CodManualBatchSkeleton,
  'audit-log': AuditLogSkeleton,
  invites: InvitesSkeleton,
  reviews: ReviewsSkeleton,
  'store-settings': StoreSettingsSkeleton,
  banners: BannersSkeleton,
  'content-form': ContentFormSkeleton,
  'mcp-agent': McpAgentSkeleton,

  // Generic aliases
  chart: DashboardSkeleton,
  table: ProductsSkeleton,
  list: CategoriesSkeleton,
  form: ProductFormSkeleton,
  detail: ProductDetailSkeleton,
};

const PageSkeleton = ({ type = 'table', ...props }) => {
  const Component = SKELETONS[type] || ProductsSkeleton;
  return <Component {...props} />;
};

export default PageSkeleton;
