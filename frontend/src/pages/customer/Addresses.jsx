import React, { useState, useEffect } from 'react';
import { addressAPI } from '../../api/addresses';
import { useModalA11y } from '../../hooks/useModalA11y';
import toast from 'react-hot-toast';
import { storeCountry } from '../../utils/format';
import {
  MapPin,
  Plus,
  Pencil,
  Trash2,
  Star,
  X,
} from 'lucide-react';

const inputBase =
  'w-full px-4 py-3 rounded-xl border bg-card text-foreground text-sm placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-2 transition-all';
const inputValid = `${inputBase} border-border focus:ring-primary/40`;
const inputInvalid = `${inputBase} border-destructive focus:ring-destructive/40`;
const btnPrimary =
  'inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground px-8 py-3.5 rounded-full font-bold uppercase tracking-widest text-xs sm:text-sm hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl disabled:opacity-60 disabled:pointer-events-none cursor-pointer';
const btnGhost =
  'inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-full border border-border bg-card text-foreground font-bold uppercase tracking-widest text-xs sm:text-sm hover:border-primary/30 hover:text-primary transition-all duration-300 cursor-pointer';
const labelCls = 'block text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2';

const Addresses = () => {
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAddress, setEditingAddress] = useState(null);
  const [formData, setFormData] = useState({
    label: '',
    line1: '',
    line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: storeCountry(),
    is_default: false
  });
  const [formErrors, setFormErrors] = useState({});

  useEffect(() => {
    fetchAddresses();
  }, []);

  const fetchAddresses = async () => {
    try {
      setLoading(true);
      const response = await addressAPI.getAddresses();
      setAddresses(response.data || []);
    } catch (error) {
      console.error('Error fetching addresses:', error);
      toast.error('Failed to load addresses');
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      label: '',
      line1: '',
      line2: '',
      city: '',
      state: '',
      postal_code: '',
      country: storeCountry(),
      is_default: false
    });
    setFormErrors({});
    setEditingAddress(null);
  };

  const openCreateModal = () => {
    resetForm();
    setIsModalOpen(true);
  };

  const openEditModal = (address) => {
    setEditingAddress(address);
    setFormData({
      label: address.label || '',
      line1: address.line1 || '',
      line2: address.line2 || '',
      city: address.city || '',
      state: address.state || '',
      postal_code: address.postal_code || '',
      country: address.country || storeCountry(),
      is_default: address.is_default || false
    });
    setFormErrors({});
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    resetForm();
  };

  // Escape closes, focus trapped/restored, scroll locked while the address form is open.
  const dialogRef = useModalA11y(closeModal, isModalOpen);

  const validateForm = () => {
    const errors = {};
    if (!formData.label.trim()) errors.label = 'Label is required';
    if (!formData.line1.trim()) errors.line1 = 'Address line 1 is required';
    if (!formData.city.trim()) errors.city = 'City is required';
    if (!formData.state.trim()) errors.state = 'State is required';
    if (!formData.postal_code.trim()) errors.postal_code = 'Postal code is required';
    if (!formData.country.trim()) errors.country = 'Country is required';
    if (formData.postal_code && !/^\d{5,6}$/.test(formData.postal_code.replace(/\s/g, ''))) {
      errors.postal_code = 'Please enter a valid postal code (5-6 digits)';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) {
      toast.error('Please fix the errors in the form');
      return;
    }

    try {
      setSaving(true);
      const data = {
        ...formData,
        is_default: formData.is_default || false,
      };

      if (editingAddress) {
        await addressAPI.updateAddress(editingAddress.id, data);
        toast.success('Address updated successfully!');
      } else {
        await addressAPI.createAddress(data);
        toast.success('Address added successfully!');
      }

      closeModal();
      await fetchAddresses();

    } catch (error) {
      console.error('Error saving address:', error);
      let errorMessage = editingAddress ? 'Failed to update address' : 'Failed to add address';
      if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map(err => err.msg || err.message).join(', ');
        } else {
          errorMessage = error.response.data.detail;
        }
      }
      toast.error(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (addressId) => {
    if (!window.confirm('Are you sure you want to delete this address?')) return;

    try {
      await addressAPI.deleteAddress(addressId);
      toast.success('Address deleted successfully!');
      await fetchAddresses();
    } catch (error) {
      console.error('Error deleting address:', error);
      let errorMessage = 'Failed to delete address';
      if (error.response?.status === 400 && error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      toast.error(errorMessage);
    }
  };

  const handleSetDefault = async (addressId) => {
    try {
      await addressAPI.setDefaultAddress(addressId);
      toast.success('Default address updated!');
      await fetchAddresses();
    } catch (error) {
      console.error('Error setting default address:', error);
      toast.error('Failed to set default address');
    }
  };

  if (loading) {
    return (
      <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
        <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
          <div className="border-b border-border pb-6 mb-8">
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
              My Addresses
            </h1>
          </div>
          <div className="bg-card border border-border rounded-4xl shadow-sm p-10 flex flex-col items-center justify-center gap-3 text-center">
            <div className="w-10 h-10 rounded-full bg-primary-soft animate-pulse" aria-hidden="true" />
            <p className="text-sm font-medium text-muted-foreground">Loading your addresses…</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header */}
        <div className="mb-8 sm:mb-10 border-b border-border pb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
              My Addresses
            </h1>
            <p className="text-sm text-muted-foreground font-medium mt-2">
              Manage your saved shipping addresses.
            </p>
          </div>
          <button type="button" onClick={openCreateModal} className={btnPrimary}>
            <Plus size={15} />
            Add Address
          </button>
        </div>

        {/* Address List */}
        {addresses.length === 0 ? (
          <div className="bg-card border border-border rounded-4xl shadow-sm p-10 sm:p-14 text-center max-w-2xl mx-auto">
            <div className="w-16 h-16 mx-auto rounded-3xl bg-primary-soft text-primary flex items-center justify-center mb-5" aria-hidden="true">
              <MapPin size={28} />
            </div>
            <h3 className="text-xl font-extrabold tracking-tight text-foreground">No addresses saved</h3>
            <p className="text-sm text-muted-foreground font-medium mt-2 mb-7">
              Add your first address to make checkout faster.
            </p>
            <button type="button" onClick={openCreateModal} className={btnPrimary}>
              <Plus size={15} />
              Add Address
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
            {addresses.map((address) => (
              <div
                key={address.id}
                className="bg-card border border-border rounded-4xl shadow-sm p-6 sm:p-7 flex flex-col hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5 transition-all duration-300"
              >
                <div className="flex items-start gap-4">
                  <span
                    className={`w-11 h-11 shrink-0 rounded-2xl flex items-center justify-center ${
                      address.is_default ? 'bg-primary text-primary-foreground' : 'bg-primary-soft text-primary'
                    }`}
                  >
                    <MapPin size={19} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-extrabold tracking-tight text-foreground">
                        {address.label || 'Address'}
                      </h3>
                      {address.is_default && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary-soft text-primary text-[10px] font-bold uppercase tracking-widest">
                          <Star size={11} fill="currentColor" />
                          Default
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-foreground mt-2">
                      {address.line1}
                      {address.line2 && <>, {address.line2}</>}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {address.city}, {address.state} {address.postal_code}
                    </p>
                    <p className="text-sm text-muted-foreground">{address.country}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-6 pt-5 border-t border-border">
                  {!address.is_default && (
                    <button
                      type="button"
                      onClick={() => handleSetDefault(address.id)}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-primary-soft border border-border text-foreground text-[11px] font-bold uppercase tracking-widest hover:bg-primary hover:text-primary-foreground transition-all duration-300 cursor-pointer"
                    >
                      <Star size={13} />
                      Set Default
                    </button>
                  )}
                  <div className="ml-auto flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => openEditModal(address)}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full border border-border text-muted-foreground text-[11px] font-bold uppercase tracking-widest hover:border-primary/40 hover:text-primary transition-all duration-300 cursor-pointer bg-transparent"
                    >
                      <Pencil size={13} />
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(address.id)}
                      className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full border border-destructive/30 text-destructive text-[11px] font-bold uppercase tracking-widest hover:bg-destructive hover:text-destructive-soft-foreground hover:border-destructive transition-all duration-300 cursor-pointer bg-transparent"
                    >
                      <Trash2 size={13} />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Address Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 p-4 flex items-center justify-center overflow-y-auto">
          <div
            className="absolute inset-0 bg-foreground/40 backdrop-blur-sm"
            onClick={closeModal}
            aria-hidden="true"
          />
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={editingAddress ? 'Edit address' : 'Add new address'}
            className="relative bg-card border border-border rounded-4xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 sm:p-8"
          >
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-extrabold tracking-tight text-foreground">
                  {editingAddress ? 'Edit Address' : 'Add New Address'}
                </h2>
                <p className="text-sm text-muted-foreground font-medium mt-1">
                  {editingAddress ? 'Update your saved address details' : 'Save a new address for faster checkout'}
                </p>
              </div>
              <button
                type="button"
                onClick={closeModal}
                className="w-9 h-9 rounded-full border border-border text-muted-foreground hover:text-primary hover:border-primary/40 transition-all duration-200 flex items-center justify-center bg-transparent cursor-pointer shrink-0"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className={labelCls}>Label *</label>
                <input
                  type="text"
                  value={formData.label}
                  onChange={(e) => {
                    setFormData({ ...formData, label: e.target.value });
                    if (formErrors.label) setFormErrors({ ...formErrors, label: '' });
                  }}
                  className={formErrors.label ? inputInvalid : inputValid}
                  placeholder="e.g., Home, Office"
                />
                {formErrors.label && <p className="text-xs text-destructive mt-1.5">{formErrors.label}</p>}
              </div>

              <div>
                <label className={labelCls}>Address Line 1 *</label>
                <input
                  type="text"
                  value={formData.line1}
                  onChange={(e) => {
                    setFormData({ ...formData, line1: e.target.value });
                    if (formErrors.line1) setFormErrors({ ...formErrors, line1: '' });
                  }}
                  className={formErrors.line1 ? inputInvalid : inputValid}
                  placeholder="House no., street, area"
                />
                {formErrors.line1 && <p className="text-xs text-destructive mt-1.5">{formErrors.line1}</p>}
              </div>

              <div>
                <label className={labelCls}>
                  Address Line 2 <span className="font-medium normal-case tracking-normal text-muted-foreground">(optional)</span>
                </label>
                <input
                  type="text"
                  value={formData.line2}
                  onChange={(e) => setFormData({ ...formData, line2: e.target.value })}
                  className={inputValid}
                  placeholder="Apartment, suite, landmark"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className={labelCls}>City *</label>
                  <input
                    type="text"
                    value={formData.city}
                    onChange={(e) => {
                      setFormData({ ...formData, city: e.target.value });
                      if (formErrors.city) setFormErrors({ ...formErrors, city: '' });
                    }}
                    className={formErrors.city ? inputInvalid : inputValid}
                  />
                  {formErrors.city && <p className="text-xs text-destructive mt-1.5">{formErrors.city}</p>}
                </div>
                <div>
                  <label className={labelCls}>State *</label>
                  <input
                    type="text"
                    value={formData.state}
                    onChange={(e) => {
                      setFormData({ ...formData, state: e.target.value });
                      if (formErrors.state) setFormErrors({ ...formErrors, state: '' });
                    }}
                    className={formErrors.state ? inputInvalid : inputValid}
                  />
                  {formErrors.state && <p className="text-xs text-destructive mt-1.5">{formErrors.state}</p>}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className={labelCls}>Postal Code *</label>
                  <input
                    type="text"
                    value={formData.postal_code}
                    onChange={(e) => {
                      setFormData({ ...formData, postal_code: e.target.value });
                      if (formErrors.postal_code) setFormErrors({ ...formErrors, postal_code: '' });
                    }}
                    className={formErrors.postal_code ? inputInvalid : inputValid}
                    placeholder="e.g., 400001"
                  />
                  {formErrors.postal_code && <p className="text-xs text-destructive mt-1.5">{formErrors.postal_code}</p>}
                </div>
                <div>
                  <label className={labelCls}>Country *</label>
                  <input
                    type="text"
                    value={formData.country}
                    onChange={(e) => {
                      setFormData({ ...formData, country: e.target.value });
                      if (formErrors.country) setFormErrors({ ...formErrors, country: '' });
                    }}
                    className={formErrors.country ? inputInvalid : inputValid}
                  />
                  {formErrors.country && <p className="text-xs text-destructive mt-1.5">{formErrors.country}</p>}
                </div>
              </div>

              <label className="flex items-center gap-3 bg-background border border-border rounded-xl px-4 py-3.5 cursor-pointer hover:border-primary/30 transition-colors">
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                  className="w-4 h-4 accent-primary"
                />
                <span className="text-sm font-semibold text-foreground">Set as default address</span>
              </label>

              <div className="flex flex-col-reverse sm:flex-row gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className={`${btnGhost} flex-1`}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className={`${btnPrimary} flex-1`}
                >
                  {saving ? (editingAddress ? 'Updating...' : 'Adding...') : (editingAddress ? 'Update Address' : 'Add Address')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Addresses;