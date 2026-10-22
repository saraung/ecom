// src/components/skeletons/coupons.jsx
import React from 'react';
import { Plus, Sparkles, ChevronDown, ArrowLeft, Save, Tag, Zap } from 'lucide-react';
import { Card, Btn, TabHeader, Count, StaticSearch, HeadRow, ListFooter, Skeleton } from './_shared';

export const CouponsSkeleton = () => (
  <div>
    <TabHeader
      title="Coupons"
      subtitle={(
        <>
          <Count w="w-8" /> coupons found
        </>
      )}
      actions={(
        <>
          <Btn className="gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg justify-center">
            <Sparkles size={18} />
            Generate Code
          </Btn>
          <Btn className="btn-primary gap-2 w-full sm:w-auto justify-center py-2.5 sm:py-2">
            <Plus size={20} />
            Create Coupon
          </Btn>
        </>
      )}
    />

    <StaticSearch placeholder="Search coupons by code..." className="relative w-full max-w-md mb-6" />

    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px]">
          <HeadRow cols={['Type', 'Code', 'Discount', 'Min Order', 'Valid From', 'Valid Until', 'Uses', 'Status', 'Actions']} />
          <tbody className="divide-y divide-border">
            {Array.from({ length: 6 }).map((_, i) => (
              <tr key={i}>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-20 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-8 w-24 rounded-lg" />
                    <Skeleton className="h-4 w-4 rounded" />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-14" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-4 w-16" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-20" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-20" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-3 w-10" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-6 w-16 rounded-full" />
                </td>
                <td className="px-4 py-3">
                  <Skeleton className="h-5 w-16 ml-auto" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ListFooter />
    </Card>
  </div>
);

export const Req = () => <span className="text-destructive"> *</span>;

export const Label = ({ children }) => (
  <label className="block text-xs font-medium text-muted-foreground mb-1">
    {children}
  </label>
);

export const Field = ({ className = 'h-9 w-full rounded-lg' }) => (
  <Skeleton className={className} />
);

export const StaticSelect = ({ display, className = 'h-9 w-full rounded-lg' }) => (
  <div className={`relative ${className}`}>
    <select
      disabled
      value=""
      tabIndex={-1}
      aria-hidden="true"
      className="w-full h-9 px-3 py-1.5 border border-input rounded-lg text-sm text-foreground bg-transparent appearance-none"
    >
      <option value="">{display}</option>
    </select>
    <ChevronDown
      size={16}
      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
    />
  </div>
);

export const StaticDate = ({ placeholder }) => (
  <input
    type="text"
    readOnly
    tabIndex={-1}
    placeholder={placeholder}
    className="w-full h-9 px-3 py-1.5 border border-input rounded-lg text-sm text-muted-foreground bg-transparent focus:outline-none"
  />
);

export const CouponFormSkeleton = ({ title = 'Create New Coupon', submitLabel = 'Create Coupon', mode = 'edit' }) => (
  <div className="pb-8">
    {/* Static header - back arrow + real title (matches the real page) */}
    <div className="flex flex-wrap items-center gap-3 mb-3">
      <Btn className="text-muted-foreground">
        <ArrowLeft size={18} />
      </Btn>
      <h1 className="text-lg font-bold text-foreground">{title}</h1>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {/* Basic Information - static title + labels, bars = dynamic values */}
      <Card className="p-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Basic Information
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="md:col-span-2">
            <Label>Coupon Type</Label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { title: 'Manual code', text: 'Customer types the code at checkout', icon: Tag, active: true },
                {
                  title: 'Automatic',
                  text: 'No code needed \u2014 applies itself at checkout',
                  icon: Zap,
                  active: false,
                },
              ].map(({ title: t, text, icon: Icon, active }) => (
                <Btn
                  key={t}
                  className={`items-start gap-2 p-3 rounded-xl border text-left ${
                    active ? 'border-primary bg-primary-soft' : 'border-input'
                  }`}
                >
                  <Icon size={16} className="mt-0.5 text-primary" />
                  <span>
                    <span className="block text-sm font-semibold text-foreground">{t}</span>
                    <span className="block text-xs text-muted-foreground">{text}</span>
                  </span>
                </Btn>
              ))}
            </div>
          </div>
          <div className="md:col-span-2">
            <Label>
              Coupon Code<Req />
            </Label>
            <Field className="h-9 w-full max-w-xs rounded-lg" />
          </div>
          <div>
            <Label>
              Discount Type<Req />
            </Label>
            <Field />
          </div>
          <div>
            <Label>
              Discount Value<Req />
            </Label>
            <StaticSelect display="Percentage (%)" />
          </div>
        </div>
      </Card>

      {/* Restrictions - static labels, bars = dynamic values */}
      <Card className="p-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Restrictions
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {['Minimum Order Value', 'Maximum Uses (Total)', 'Max Uses Per User', 'Valid From', 'Valid Until'].map(
            (label) => (
              <div key={label}>
                <Label>{label}</Label>
                {label.startsWith('Valid') ? (
                  <StaticDate placeholder={label === 'Valid From' ? 'dd-mm-yyyy' : 'dd-mm-yyyy'} />
                ) : (
                  <Field />
                )}
              </div>
            )
          )}
        </div>
      </Card>

      {/* Trigger Condition (full width) - automatic coupons only, so it is
          hidden on create (manual by default) and shown on edit */}
      {mode !== 'create' && (
      <Card className="p-3 lg:col-span-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Trigger Condition
        </h2>
        <p className="text-xs text-muted-foreground mb-2">
          The backend applies this coupon by itself whenever the condition below is met, and always
          re-checks eligibility server-side before checkout.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <Label>
              Applies automatically when<Req />
            </Label>
            <StaticSelect display="Cart value reaches a minimum amount" />
          </div>
          <div>
            <Label>
              Minimum cart value (&#8377;)<Req />
            </Label>
            <Field />
          </div>
        </div>
      </Card>
      )}

      {/* Footer bar: active toggle + status + actions - static controls */}
      <Card className="p-3 lg:col-span-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked
              readOnly
              tabIndex={-1}
              className="w-4 h-4 text-primary rounded border-input"
            />
            <span className="text-xs font-medium text-foreground">Active</span>
          </label>
          <span className="text-xs text-muted-foreground">Coupon is available for use</span>
          <div className="ml-auto flex gap-2">
            <Btn className="px-4 py-1.5 border border-input rounded-lg text-sm font-medium">
              Cancel
            </Btn>
            <Btn className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg text-sm font-medium gap-2">
              <Save size={16} />
              {submitLabel}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  </div>
);
