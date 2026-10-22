import test from 'node:test';
import assert from 'node:assert/strict';
import { skeletonForPath } from '../components/skeletons/skeletonRoutes.js';

test('skeletonForPath maps COD routes from most specific to least specific', () => {
  assert.equal(skeletonForPath('/cod/import').type, 'cod-import');
  assert.equal(skeletonForPath('/cod/new').type, 'cod-manual');
  assert.equal(skeletonForPath('/cod/42').type, 'cod-detail');
  assert.equal(skeletonForPath('/cod/42/').type, 'cod-detail');
  assert.equal(skeletonForPath('/cod').type, 'cod');
});

test('skeletonForPath maps create and edit forms with their titles', () => {
  const productCreate = skeletonForPath('/products/new');
  assert.equal(productCreate.type, 'product-form');
  assert.equal(productCreate.props.title, 'Create New Product');
  assert.equal(productCreate.props.mode, 'create');

  const productEdit = skeletonForPath('/products/abc/edit');
  assert.equal(productEdit.type, 'product-form');
  assert.equal(productEdit.props.title, 'Edit Product');
  assert.equal(productEdit.props.mode, 'edit');

  const couponEdit = skeletonForPath('/coupons/abc/edit');
  assert.equal(couponEdit.type, 'coupon-form');
  assert.equal(couponEdit.props.submitLabel, 'Update Coupon');
});

test('skeletonForPath distinguishes category products from category edit', () => {
  assert.equal(skeletonForPath('/categories/12/products').type, 'category-products');
  assert.equal(skeletonForPath('/categories/12/edit').type, 'category-form');
  assert.equal(skeletonForPath('/categories').type, 'categories');
});

test('skeletonForPath resolves detail routes before list routes', () => {
  assert.equal(skeletonForPath('/products/abc').type, 'product-detail');
  assert.equal(skeletonForPath('/orders/abc').type, 'order-detail');
  assert.equal(skeletonForPath('/returns/abc').type, 'return-detail');
  assert.equal(skeletonForPath('/users/abc').type, 'user-detail');
  assert.equal(skeletonForPath('/products').type, 'products');
  assert.equal(skeletonForPath('/orders').type, 'orders');
  assert.equal(skeletonForPath('/returns').type, 'returns');
  assert.equal(skeletonForPath('/users').type, 'users');
});

test('skeletonForPath covers remaining admin pages and falls back safely', () => {
  const expected = {
    '/': 'dashboard',
    '/reports': 'reports',
    '/settings': 'settings',
    '/promotions': 'promotions',
    '/refunds': 'refunds',
    '/audit-log': 'audit-log',
    '/invites': 'invites',
    '/reviews': 'reviews',
    '/store-settings': 'store-settings',
    '/content': 'banners',
    '/content/new': 'content-form',
    '/content/1/edit': 'content-form',
    '/shipping-simulator': 'shipping-simulator',
    '/mcp-agent': 'mcp-agent',
  };

  for (const [pathname, type] of Object.entries(expected)) {
    assert.equal(skeletonForPath(pathname).type, type, pathname);
  }

  assert.deepEqual(skeletonForPath('/does-not-exist'), {
    type: 'products',
    props: {},
  });
  assert.deepEqual(skeletonForPath(undefined), {
    type: 'products',
    props: {},
  });
});
