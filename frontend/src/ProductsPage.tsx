import { useEffect, useState, FormEvent } from 'react';
import { api, Product, ProductInput } from './api';
import SidebarLayout from './SidebarLayout';

const EMPTY_FORM: ProductInput = {
  name: '',
  description: '',
  price: 0,
  currency: 'CZK',
  category: '',
  tags: '',
  stock: 0,
  is_active: true,
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ProductInput>(EMPTY_FORM);
  const [formError, setFormError] = useState('');

  const loadProducts = async (p = page) => {
    setLoading(true);
    try {
      const data = await api.getProducts(p);
      setProducts(data.items);
      setTotal(data.total);
      setPage(data.page);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load products');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadProducts(); }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setShowForm(true);
  };

  const openEdit = (product: Product) => {
    setEditingId(product.id);
    setForm({
      name: product.name,
      description: product.description,
      price: product.price,
      currency: product.currency,
      category: product.category,
      tags: product.tags,
      stock: product.stock,
      is_active: product.is_active,
    });
    setFormError('');
    setShowForm(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError('');

    try {
      if (editingId) {
        await api.updateProduct(editingId, form);
      } else {
        await api.createProduct(form);
      }
      setShowForm(false);
      loadProducts();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Save failed');
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      await api.deleteProduct(id);
      loadProducts();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleToggle = async (product: Product) => {
    try {
      await api.updateProduct(product.id, { is_active: !product.is_active });
      loadProducts();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Toggle failed');
    }
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <SidebarLayout title="Product Catalog">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <span className="count-badge" style={{ fontSize: '0.9rem', padding: '0.3rem 0.8rem' }}>Total: {total}</span>
        </div>
        <button onClick={openCreate} className="btn-primary-sm">
          + New Product
        </button>
      </div>

      {error && <div className="alert-error" style={{ marginBottom: '1rem', color: 'var(--danger)' }}>{error}</div>}

        {/* Product Table */}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="table-empty">Loading...</td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={6} className="table-empty">
                    No products yet.{' '}
                    <button onClick={openCreate} className="link-btn">Create one</button>
                  </td>
                </tr>
              ) : (
                products.map(p => (
                  <tr key={p.id} className={!p.is_active ? 'row-inactive' : ''}>
                    <td>
                      <div className="product-name">{p.name}</div>
                      {p.description && (
                        <div className="product-desc">{p.description}</div>
                      )}
                    </td>
                    <td>
                      {p.category && (
                        <span className="category-tag">{p.category}</span>
                      )}
                    </td>
                    <td className="price-cell">
                      {p.price.toFixed(0)} {p.currency}
                    </td>
                    <td>
                      <span className={`stock-badge ${p.stock === 0 ? 'out' : p.stock < 5 ? 'low' : 'ok'}`}>
                        {p.stock}
                      </span>
                    </td>
                    <td>
                      <button
                        className={`toggle-btn ${p.is_active ? 'active' : 'inactive'}`}
                        onClick={() => handleToggle(p)}
                        title={p.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {p.is_active ? '✅' : '⬜'}
                      </button>
                    </td>
                    <td>
                      <div className="action-btns">
                        <button onClick={() => openEdit(p)} className="btn-icon" title="Edit">✏️</button>
                        <button onClick={() => handleDelete(p.id, p.name)} className="btn-icon btn-danger" title="Delete">🗑️</button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button disabled={page <= 1} onClick={() => loadProducts(page - 1)}>←</button>
            <span>{page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => loadProducts(page + 1)}>→</button>
          </div>
        )}      {/* Create/Edit Modal */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>{editingId ? 'Edit Product' : 'New Product'}</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-row">
                <div className="form-group">
                  <label>Name *</label>
                  <input
                    value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    required
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label>Category</label>
                  <input
                    value={form.category}
                    onChange={e => setForm({ ...form, category: e.target.value })}
                    placeholder="e.g. Flowers"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  rows={2}
                  placeholder="Optional product description"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Price *</label>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={form.price}
                    onChange={e => setForm({ ...form, price: parseFloat(e.target.value) || 0 })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Currency</label>
                  <input
                    value={form.currency}
                    onChange={e => setForm({ ...form, currency: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Stock</label>
                  <input
                    type="number"
                    min={0}
                    value={form.stock}
                    onChange={e => setForm({ ...form, stock: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Tags</label>
                <input
                  value={form.tags}
                  onChange={e => setForm({ ...form, tags: e.target.value })}
                  placeholder="comma, separated, tags"
                />
              </div>

              <div className="form-check">
                <label>
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={e => setForm({ ...form, is_active: e.target.checked })}
                  />
                  Active (visible to AI & customers)
                </label>
              </div>

              {formError && <div className="form-error">{formError}</div>}

              <div className="form-actions">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  {editingId ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </SidebarLayout>
  );
}
