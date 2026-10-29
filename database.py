"""
database.py
===========
SIERRA STORE — Wholesale Clothing Management System
---------------------------------------------------
Database layer (SQLite).
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# The path can be overridden with the SIERRA_DB_PATH environment variable
# (useful for tests or for keeping the database on a shared drive).
DB_PATH = os.environ.get("SIERRA_DB_PATH", os.path.join(BASE_DIR, "sierra_store.db"))

# Roles recognised by the application
ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)

# Default application settings (invoice header / footer, shop identity, ...)
DEFAULT_SETTINGS: Dict[str, str] = {
    "shop_name": "SIERRA STORE",
    "invoice_header": "SIERRA STORE\nWholesale Clothing",
    "invoice_footer": "Thank you for your business!\nGoods cannot be returned after 3 days.",
    "receipt_width_mm": "80",
    "currency_symbol": "$",
}


# ---------------------------------------------------------------------------
# Low level helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """
    Yield a configured SQLite connection.

    The connection is committed on success, rolled back on error and always
    closed afterwards.  Foreign keys are enforced on every connection.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    """Current local timestamp in SQLite-friendly format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    """Current local date (YYYY-MM-DD)."""
    return date.today().isoformat()


def _money(value: Any) -> float:
    """Coerce a value to a 2-decimal float."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convert an sqlite3.Row to a plain dictionary."""
    return dict(row) if row is not None else None


def _rows_to_dicts(rows: Sequence[sqlite3.Row]) -> List[Dict[str, Any]]:
    """Convert a sequence of sqlite3.Row objects to plain dictionaries."""
    return [dict(row) for row in rows]


def _build_date_filter(column: str,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None) -> tuple:
    """
    Build a WHERE fragment (list of clauses) and its parameters for
    inclusive date-range filtering on `column` (a date/datetime column).
    """
    clauses: List[str] = []
    params: List[Any] = []
    if date_from:
        clauses.append(f"date({column}) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append(f"date({column}) <= date(?)")
        params.append(date_to)
    return clauses, params


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    Hash a password using PBKDF2-HMAC-SHA256.

    Returns a string of the form "<salt>$<hexdigest>".
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a plain password against a stored hash produced by hash_password()."""
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, _ = stored_hash.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), stored_hash)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- -----------------------------------------------------------------------
-- Users
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    password    TEXT    NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'user'
                        CHECK (role IN ('admin', 'user')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- -----------------------------------------------------------------------
-- Products
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    category         TEXT    NOT NULL DEFAULT '',
    cost_price       REAL    NOT NULL DEFAULT 0,
    wholesale_price  REAL    NOT NULL DEFAULT 0,
    stock_qty        INTEGER NOT NULL DEFAULT 0,
    min_limit        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_products_name     ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);

-- -----------------------------------------------------------------------
-- Suppliers
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL DEFAULT '',
    address     TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- -----------------------------------------------------------------------
-- Invoices (header)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name   TEXT    NOT NULL DEFAULT '',
    customer_phone  TEXT    NOT NULL DEFAULT '',
    total_items     INTEGER NOT NULL DEFAULT 0,
    subtotal        REAL    NOT NULL DEFAULT 0,
    discount        REAL    NOT NULL DEFAULT 0,
    net_total       REAL    NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    cashier_name    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices (created_at);

-- -----------------------------------------------------------------------
-- Invoice items (lines)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoice_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id    INTEGER NOT NULL,
    product_code  TEXT    NOT NULL,
    product_name  TEXT    NOT NULL,
    quantity      INTEGER NOT NULL,
    price         REAL    NOT NULL,
    total_price   REAL    NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_code    ON invoice_items (product_code);

-- -----------------------------------------------------------------------
-- Expenses
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS expenses (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    category  TEXT    NOT NULL,
    amount    REAL    NOT NULL DEFAULT 0,
    notes     TEXT    NOT NULL DEFAULT '',
    date      TEXT    NOT NULL DEFAULT (date('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date);

-- -----------------------------------------------------------------------
-- Application settings (key/value)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT ''
);
"""


def initialize_database() -> None:
    """
    Create the database file (if needed), all tables, indexes, the default
    administrator account and the default settings.

    Safe to call multiple times — it never destroys existing data.
    """
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(SCHEMA_SQL)

    _seed_defaults()


def _seed_defaults() -> None:
    """Insert the default admin user and default settings when missing."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", hash_password("admin123"), ROLE_ADMIN),
            )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


# ===========================================================================
# USERS
# ===========================================================================

def create_user(username: str, password: str, role: str = ROLE_USER) -> int:
    """
    Create a new user and return its id.

    Raises ValueError on invalid input or duplicated username.
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required.")
    if not password or len(password) < 4:
        raise ValueError("Password must be at least 4 characters long.")
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {VALID_ROLES}.")

    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists.")
        return int(cur.lastrowid)


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Validate credentials.

    Returns {'id', 'username', 'role'} on success, otherwise None.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", ((username or "").strip(),)
        ).fetchone()

    if row is None or not verify_password(password, row["password"]):
        return None

    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Return a single user (without password) or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Return a single user (without password) or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
    return _row_to_dict(row)


def get_all_users() -> List[Dict[str, Any]]:
    """Return every user (without passwords), ordered by username."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return _rows_to_dicts(rows)


def update_user_password(user_id: int, new_password: str) -> bool:
    """Change a user's password. Returns True when a row was updated."""
    if not new_password or len(new_password) < 4:
        raise ValueError("Password must be at least 4 characters long.")

    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        return cur.rowcount > 0


def update_user_role(user_id: int, role: str) -> bool:
    """Change a user's role. Returns True when a row was updated."""
    if role not in VALID_ROLES:
        raise ValueError(f"Role must be one of {VALID_ROLES}.")

    with get_connection() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return False

        # Never allow the system to lose its last administrator.
        if user["role"] == ROLE_ADMIN and role != ROLE_ADMIN:
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = ?", (ROLE_ADMIN,)
            ).fetchone()["c"]
            if admins <= 1:
                raise ValueError("Cannot demote the last remaining administrator.")

        cur = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        return cur.rowcount > 0


def delete_user(user_id: int) -> bool:
    """
    Delete a user. Returns True when a row was deleted.

    Raises ValueError if the user is the last remaining administrator.
    """
    with get_connection() as conn:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            return False

        if user["role"] == ROLE_ADMIN:
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = ?", (ROLE_ADMIN,)
            ).fetchone()["c"]
            if admins <= 1:
                raise ValueError("Cannot delete the last remaining administrator.")

        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def count_users() -> int:
    """Total number of users."""
    with get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"])


# ===========================================================================
# PRODUCTS
# ===========================================================================

def add_product(code: str,
                name: str,
                category: str = "",
                cost_price: float = 0.0,
                wholesale_price: float = 0.0,
                stock_qty: int = 0,
                min_limit: int = 0) -> int:
    """
    Insert a new product and return its id.

    Raises ValueError on invalid input or duplicated product code.
    """
    code = (code or "").strip()
    name = (name or "").strip()

    if not code:
        raise ValueError("Product code is required.")
    if not name:
        raise ValueError("Product name is required.")

    cost_price = _money(cost_price)
    wholesale_price = _money(wholesale_price)
    stock_qty = int(stock_qty or 0)
    min_limit = int(min_limit or 0)

    if cost_price < 0 or wholesale_price < 0:
        raise ValueError("Prices cannot be negative.")
    if stock_qty < 0 or min_limit < 0:
        raise ValueError("Stock quantities cannot be negative.")

    with get_connection() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO products
                       (code, name, category, cost_price, wholesale_price, stock_qty, min_limit)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (code, name, (category or "").strip(), cost_price,
                 wholesale_price, stock_qty, min_limit),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Product code '{code}' already exists.")
        return int(cur.lastrowid)


def update_product(product_id: int,
                   code: str,
                   name: str,
                   category: str = "",
                   cost_price: float = 0.0,
                   wholesale_price: float = 0.0,
                   stock_qty: int = 0,
                   min_limit: int = 0) -> bool:
    """Update every field of an existing product. Returns True on success."""
    code = (code or "").strip()
    name = (name or "").strip()

    if not code:
        raise ValueError("Product code is required.")
    if not name:
        raise ValueError("Product name is required.")

    cost_price = _money(cost_price)
    wholesale_price = _money(wholesale_price)
    stock_qty = int(stock_qty or 0)
    min_limit = int(min_limit or 0)

    if cost_price < 0 or wholesale_price < 0:
        raise ValueError("Prices cannot be negative.")
    if stock_qty < 0 or min_limit < 0:
        raise ValueError("Stock quantities cannot be negative.")

    with get_connection() as conn:
        try:
            cur = conn.execute(
                """UPDATE products
                      SET code = ?, name = ?, category = ?, cost_price = ?,
                          wholesale_price = ?, stock_qty = ?, min_limit = ?
                    WHERE id = ?""",
                (code, name, (category or "").strip(), cost_price,
                 wholesale_price, stock_qty, min_limit, product_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Product code '{code}' already exists.")
        return cur.rowcount > 0


def delete_product(product_id: int) -> bool:
    """
    Delete a product. Returns True when a row was deleted.

    Historical invoice lines keep a snapshot of the code/name/price,
    therefore past invoices are never affected by product deletion.
    """
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return cur.rowcount > 0


def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    """Return a product by its primary key."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _row_to_dict(row)


def get_product_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Return a product by its unique code."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE code = ?", ((code or "").strip(),)
        ).fetchone()
    return _row_to_dict(row)


def get_all_products(search: str = "", category: str = "") -> List[Dict[str, Any]]:
    """
    Return products, optionally filtered by a free-text search
    (code / name / category) and/or an exact category.
    """
    query = "SELECT * FROM products"
    clauses: List[str] = []
    params: List[Any] = []

    if search:
        term = f"%{search.strip()}%"
        clauses.append("(code LIKE ? OR name LIKE ? OR category LIKE ?)")
        params.extend([term, term, term])

    if category:
        clauses.append("category = ?")
        params.append(category)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY name COLLATE NOCASE"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)


def search_products(term: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Quick search used by the POS screen.

    Matches product code or name; products with available stock are listed first.
    """
    term = (term or "").strip()
    if not term:
        return []

    pattern = f"%{term}%"
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT *
                 FROM products
                WHERE code LIKE ? OR name LIKE ? OR category LIKE ?
                ORDER BY (stock_qty > 0) DESC, name COLLATE NOCASE
                LIMIT ?""",
            (pattern, pattern, pattern, int(limit)),
        ).fetchall()
    return _rows_to_dicts(rows)


def get_low_stock_products() -> List[Dict[str, Any]]:
    """Return products whose stock reached or fell below their minimum limit."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT *
                 FROM products
                WHERE stock_qty <= min_limit
                ORDER BY stock_qty ASC, name COLLATE NOCASE"""
        ).fetchall()
    return _rows_to_dicts(rows)


def count_low_stock_products() -> int:
    """Number of products at or below their minimum stock limit."""
    with get_connection() as conn:
        return int(conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE stock_qty <= min_limit"
        ).fetchone()["c"])


def get_product_categories() -> List[str]:
    """Distinct, non-empty product categories."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT category
                 FROM products
                WHERE category IS NOT NULL AND TRIM(category) <> ''
                ORDER BY category COLLATE NOCASE"""
        ).fetchall()
    return [row["category"] for row in rows]


def set_product_stock(product_id: int, stock_qty: int) -> bool:
    """Overwrite a product's stock quantity (used for manual stock takes)."""
    stock_qty = int(stock_qty)
    if stock_qty < 0:
        raise ValueError("Stock quantity cannot be negative.")

    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE products SET stock_qty = ? WHERE id = ?", (stock_qty, product_id)
        )
        return cur.rowcount > 0


def adjust_product_stock(product_id: int, delta: int) -> bool:
    """
    Add or subtract a quantity from a product's stock.

    Raises ValueError if the resulting stock would become negative.
    """
    delta = int(delta)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT stock_qty FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if row is None:
            return False

        new_qty = int(row["stock_qty"]) + delta
        if new_qty < 0:
            raise ValueError("Stock quantity cannot become negative.")

        conn.execute(
            "UPDATE products SET stock_qty = ? WHERE id = ?", (new_qty, product_id)
        )
        return True


def count_products() -> int:
    """Total number of products."""
    with get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"])


# ===========================================================================
# SUPPLIERS
# ===========================================================================

def add_supplier(name: str,
                 phone: str = "",
                 address: str = "",
                 notes: str = "") -> int:
    """Insert a new supplier and return its id."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Supplier name is required.")

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO suppliers (name, phone, address, notes) VALUES (?, ?, ?, ?)",
            (name, (phone or "").strip(), (address or "").strip(), (notes or "").strip()),
        )
        return int(cur.lastrowid)


def update_supplier(supplier_id: int,
                    name: str,
                    phone: str = "",
                    address: str = "",
                    notes: str = "") -> bool:
    """Update a supplier record. Returns True on success."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Supplier name is required.")

    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE suppliers
                  SET name = ?, phone = ?, address = ?, notes = ?
                WHERE id = ?""",
            (name, (phone or "").strip(), (address or "").strip(),
             (notes or "").strip(), supplier_id),
        )
        return cur.rowcount > 0


def delete_supplier(supplier_id: int) -> bool:
    """Delete a supplier. Returns True on success."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        return cur.rowcount > 0


def get_supplier_by_id(supplier_id: int) -> Optional[Dict[str, Any]]:
    """Return a supplier by id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()
    return _row_to_dict(row)


def get_all_suppliers(search: str = "") -> List[Dict[str, Any]]:
    """Return all suppliers, optionally filtered by name / phone / address."""
    query = "SELECT * FROM suppliers"
    params: List[Any] = []

    if search:
        term = f"%{search.strip()}%"
        query += " WHERE name LIKE ? OR phone LIKE ? OR address LIKE ?"
        params.extend([term, term, term])

    query += " ORDER BY name COLLATE NOCASE"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)


def count_suppliers() -> int:
    """Total number of suppliers."""
    with get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM suppliers").fetchone()["c"])


# ===========================================================================
# INVOICES
# ===========================================================================

def get_next_invoice_number() -> int:
    """
    Preview the next invoice number (the invoices table uses AUTOINCREMENT).

    Used by the POS screen to display the upcoming invoice id before saving.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'invoices'"
        ).fetchone()
        if row is None:
            return 1
        return int(row["seq"]) + 1


def create_invoice(customer_name: str = "",
                   customer_phone: str = "",
                   items: Optional[Sequence[Dict[str, Any]]] = None,
                   discount: float = 0.0,
                   cashier_name: str = "",
                   created_at: Optional[str] = None) -> Dict[str, Any]:
    """
    Create an invoice, insert its lines and deduct the stock — atomically.

    Parameters
    ----------
    items : sequence of dicts, each containing
            {'product_code' (or 'code'), 'quantity' (or 'qty'), 'price' (optional)}
            When 'price' is omitted the product's wholesale_price is used.

    Returns
    -------
    The complete invoice dictionary (see `get_invoice`).

    Raises
    ------
    ValueError
        On an empty invoice, unknown product, invalid quantity/price,
        insufficient stock, or a discount larger than the subtotal.
    """
    items = list(items or [])
    if not items:
        raise ValueError("Cannot create an invoice without items.")

    discount = _money(discount)
    if discount < 0:
        raise ValueError("Discount cannot be negative.")

    created_at = created_at or _now()

    with get_connection() as conn:
        lines: List[Dict[str, Any]] = []
        demand: Dict[str, int] = {}
        products_cache: Dict[str, sqlite3.Row] = {}

        # --- Validate and normalise every line -----------------------------
        for raw in items:
            code = str(raw.get("product_code") or raw.get("code") or "").strip()
            if not code:
                raise ValueError("Every invoice line requires a product code.")

            try:
                qty = int(raw.get("quantity", raw.get("qty", 0)))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity for product '{code}'.")
            if qty <= 0:
                raise ValueError(f"Quantity for product '{code}' must be greater than zero.")

            product = products_cache.get(code)
            if product is None:
                product = conn.execute(
                    "SELECT * FROM products WHERE code = ?", (code,)
                ).fetchone()
                if product is None:
                    raise ValueError(f"Product with code '{code}' was not found.")
                products_cache[code] = product

            raw_price = raw.get("price")
            price = _money(product["wholesale_price"] if raw_price is None else raw_price)
            if price < 0:
                raise ValueError(f"Invalid price for product '{code}'.")

            demand[code] = demand.get(code, 0) + qty
            lines.append({
                "product_code": code,
                "product_name": product["name"],
                "quantity": qty,
                "price": price,
                "total_price": _money(price * qty),
            })

        # --- Stock check (aggregated per product) --------------------------
        for code, qty in demand.items():
            product = products_cache[code]
            if int(product["stock_qty"]) < qty:
                raise ValueError(
                    f"Not enough stock for '{product['name']}' "
                    f"(available: {product['stock_qty']}, requested: {qty})."
                )

        # --- Totals ---------------------------------------------------------
        subtotal = _money(sum(line["total_price"] for line in lines))
        total_items = int(sum(line["quantity"] for line in lines))

        if discount > subtotal:
            raise ValueError("Discount cannot be greater than the subtotal.")

        net_total = _money(subtotal - discount)

        # --- Persist ---------------------------------------------------------
        cur = conn.execute(
            """INSERT INTO invoices
                   (customer_name, customer_phone, total_items,
                    subtotal, discount, net_total, created_at, cashier_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ((customer_name or "").strip(), (customer_phone or "").strip(),
             total_items, subtotal, discount, net_total, created_at,
             (cashier_name or "").strip()),
        )
        invoice_id = int(cur.lastrowid)

        for line in lines:
            conn.execute(
                """INSERT INTO invoice_items
                       (invoice_id, product_code, product_name,
                        quantity, price, total_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (invoice_id, line["product_code"], line["product_name"],
                 line["quantity"], line["price"], line["total_price"]),
            )
            conn.execute(
                "UPDATE products SET stock_qty = stock_qty - ? WHERE code = ?",
                (line["quantity"], line["product_code"]),
            )

    return get_invoice(invoice_id)


def get_invoice(invoice_id: int) -> Optional[Dict[str, Any]]:
    """
    Return a complete invoice (header + 'items' list) or None.
    """
    with get_connection() as conn:
        header = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if header is None:
            return None

        items = conn.execute(
            """SELECT id, invoice_id, product_code, product_name,
                      quantity, price, total_price
                 FROM invoice_items
                WHERE invoice_id = ?
                ORDER BY id""",
            (invoice_id,),
        ).fetchall()

    invoice = dict(header)
    invoice["items"] = _rows_to_dicts(items)
    return invoice


def get_invoices(search: str = "",
                 date_from: Optional[str] = None,
                 date_to: Optional[str] = None,
                 limit: int = 200,
                 offset: int = 0) -> List[Dict[str, Any]]:
    """
    Return invoice headers (newest first), optionally filtered by
    customer name / phone / invoice number and by an inclusive date range.
    """
    query = "SELECT * FROM invoices"
    clauses: List[str] = []
    params: List[Any] = []

    if search:
        term = f"%{search.strip()}%"
        clauses.append(
            "(customer_name LIKE ? OR customer_phone LIKE ? OR CAST(id AS TEXT) LIKE ?)"
        )
        params.extend([term, term, term])

    date_clauses, date_params = _build_date_filter("created_at", date_from, date_to)
    clauses.extend(date_clauses)
    params.extend(date_params)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)


def delete_invoice(invoice_id: int, restore_stock: bool = True) -> bool:
    """
    Delete an invoice and (optionally) return its quantities to stock.

    Returns True when the invoice existed and was removed.
    """
    with get_connection() as conn:
        header = conn.execute(
            "SELECT id FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if header is None:
            return False

        if restore_stock:
            rows = conn.execute(
                "SELECT product_code, quantity FROM invoice_items WHERE invoice_id = ?",
                (invoice_id,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE products SET stock_qty = stock_qty + ? WHERE code = ?",
                    (int(row["quantity"]), row["product_code"]),
                )

        conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        return True


def count_invoices(date_from: Optional[str] = None,
                   date_to: Optional[str] = None) -> int:
    """Number of invoices within an optional date range."""
    clauses, params = _build_date_filter("created_at", date_from, date_to)
    query = "SELECT COUNT(*) AS c FROM invoices"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    with get_connection() as conn:
        return int(conn.execute(query, params).fetchone()["c"])


# ===========================================================================
# EXPENSES
# ===========================================================================

def add_expense(category: str,
                amount: float,
                notes: str = "",
                expense_date: Optional[str] = None) -> int:
    """Register a new operational expense and return its id."""
    category = (category or "").strip()
    if not category:
        raise ValueError("Expense category is required.")

    amount = _money(amount)
    if amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (category, amount, notes, date) VALUES (?, ?, ?, ?)",
            (category, amount, (notes or "").strip(), expense_date or _today()),
        )
        return int(cur.lastrowid)


def update_expense(expense_id: int,
                   category: str,
                   amount: float,
                   notes: str = "",
                   expense_date: Optional[str] = None) -> bool:
    """Update an existing expense. Returns True on success."""
    category = (category or "").strip()
    if not category:
        raise ValueError("Expense category is required.")

    amount = _money(amount)
    if amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")

    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE expenses
                  SET category = ?, amount = ?, notes = ?, date = ?
                WHERE id = ?""",
            (category, amount, (notes or "").strip(),
             expense_date or _today(), expense_id),
        )
        return cur.rowcount > 0


def delete_expense(expense_id: int) -> bool:
    """Delete an expense. Returns True on success."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        return cur.rowcount > 0


def get_expense_by_id(expense_id: int) -> Optional[Dict[str, Any]]:
    """Return a single expense record."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return _row_to_dict(row)


def get_expenses(category: str = "",
                 date_from: Optional[str] = None,
                 date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return expenses (newest first) filtered by category and/or date range."""
    query = "SELECT * FROM expenses"
    clauses: List[str] = []
    params: List[Any] = []

    if category:
        clauses.append("category = ?")
        params.append(category)

    date_clauses, date_params = _build_date_filter("date", date_from, date_to)
    clauses.extend(date_clauses)
    params.extend(date_params)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY date DESC, id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return _rows_to_dicts(rows)


def get_expense_categories() -> List[str]:
    """Distinct expense categories already used."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT category
                 FROM expenses
                WHERE TRIM(category) <> ''
                ORDER BY category COLLATE NOCASE"""
        ).fetchall()
    return [row["category"] for row in rows]


def get_total_expenses(date_from: Optional[str] = None,
                       date_to: Optional[str] = None) -> float:
    """Sum of expenses within an optional date range."""
    clauses, params = _build_date_filter("date", date_from, date_to)
    query = "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    with get_connection() as conn:
        return _money(conn.execute(query, params).fetchone()["total"])


# ===========================================================================
# REPORTS
# ===========================================================================

def get_sales_summary(date_from: Optional[str] = None,
                      date_to: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregated sales figures for a date range.

    Returns
    -------
    {'invoice_count', 'total_items', 'subtotal', 'discount', 'net_total'}
    """
    clauses, params = _build_date_filter("created_at", date_from, date_to)
    query = """SELECT COUNT(*)                       AS invoice_count,
                      COALESCE(SUM(total_items), 0) AS total_items,
                      COALESCE(SUM(subtotal), 0)    AS subtotal,
                      COALESCE(SUM(discount), 0)    AS discount,
                      COALESCE(SUM(net_total), 0)   AS net_total
                 FROM invoices"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()

    return {
        "invoice_count": int(row["invoice_count"]),
        "total_items": int(row["total_items"]),
        "subtotal": _money(row["subtotal"]),
        "discount": _money(row["discount"]),
        "net_total": _money(row["net_total"]),
    }


def get_cost_of_goods_sold(date_from: Optional[str] = None,
                           date_to: Optional[str] = None) -> float:
    """
    Cost of goods sold for a date range.

    The cost is resolved from the product's *current* cost_price through the
    product code stored on each invoice line.
    """
    clauses, params = _build_date_filter("i.created_at", date_from, date_to)
    query = """SELECT COALESCE(SUM(ii.quantity * COALESCE(p.cost_price, 0)), 0) AS cogs
                 FROM invoice_items ii
                 JOIN invoices i       ON i.id = ii.invoice_id
                 LEFT JOIN products p  ON p.code = ii.product_code"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    with get_connection() as conn:
        return _money(conn.execute(query, params).fetchone()["cogs"])


def get_profit_report(date_from: Optional[str] = None,
                      date_to: Optional[str] = None) -> Dict[str, Any]:
    """
    Full profit breakdown for a date range.

    Returns
    -------
    {'revenue', 'cogs', 'gross_profit', 'expenses', 'net_profit',
     'invoice_count', 'total_items'}
    """
    sales = get_sales_summary(date_from, date_to)
    cogs = get_cost_of_goods_sold(date_from, date_to)
    expenses = get_total_expenses(date_from, date_to)

    revenue = _money(sales["net_total"])
    gross_profit = _money(revenue - cogs)
    net_profit = _money(gross_profit - expenses)

    return {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "expenses": expenses,
        "net_profit": net_profit,
        "invoice_count": sales["invoice_count"],
        "total_items": sales["total_items"],
    }


def get_top_products(limit: int = 10,
                     date_from: Optional[str] = None,
                     date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Best selling products in a date range, ordered by revenue.

    Returns a list of {'product_code', 'product_name', 'quantity', 'revenue'}.
    """
    clauses, params = _build_date_filter("i.created_at", date_from, date_to)
    query = """SELECT ii.product_code              AS product_code,
                      ii.product_name              AS product_name,
                      COALESCE(SUM(ii.quantity), 0)    AS quantity,
                      COALESCE(SUM(ii.total_price), 0) AS revenue
                 FROM invoice_items ii
                 JOIN invoices i ON i.id = ii.invoice_id"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += """ GROUP BY ii.product_code, ii.product_name
                 ORDER BY revenue DESC
                 LIMIT ?"""
    params.append(int(limit))

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [{
        "product_code": row["product_code"],
        "product_name": row["product_name"],
        "quantity": int(row["quantity"]),
        "revenue": _money(row["revenue"]),
    } for row in rows]


def get_sales_by_day(date_from: Optional[str] = None,
                     date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Daily sales totals, ordered by date.

    Returns a list of {'day', 'invoice_count', 'net_total'}.
    """
    clauses, params = _build_date_filter("created_at", date_from, date_to)
    query = """SELECT date(created_at)               AS day,
                      COUNT(*)                       AS invoice_count,
                      COALESCE(SUM(net_total), 0)    AS net_total
                 FROM invoices"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " GROUP BY day ORDER BY day"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [{
        "day": row["day"],
        "invoice_count": int(row["invoice_count"]),
        "net_total": _money(row["net_total"]),
    } for row in rows]


def get_sales_by_category(date_from: Optional[str] = None,
                          date_to: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Sales totals grouped by product category.

    Products that no longer exist fall into the "Uncategorised" bucket.
    """
    clauses, params = _build_date_filter("i.created_at", date_from, date_to)
    query = """SELECT COALESCE(NULLIF(TRIM(p.category), ''), 'Uncategorised') AS category,
                      COALESCE(SUM(ii.quantity), 0)    AS quantity,
                      COALESCE(SUM(ii.total_price), 0) AS revenue
                 FROM invoice_items ii
                 JOIN invoices i      ON i.id = ii.invoice_id
                 LEFT JOIN products p ON p.code = ii.product_code"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " GROUP BY category ORDER BY revenue DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [{
        "category": row["category"],
        "quantity": int(row["quantity"]),
        "revenue": _money(row["revenue"]),
    } for row in rows]


def get_dashboard_stats() -> Dict[str, Any]:
    """
    Snapshot values for a dashboard / home screen.
    """
    with get_connection() as conn:
        def scalar(query: str, params: Sequence[Any] = ()) -> Any:
            row = conn.execute(query, params).fetchone()
            return row[0] if row is not None else 0

        stats = {
            "total_products": int(scalar("SELECT COUNT(*) FROM products")),
            "low_stock_count": int(scalar(
                "SELECT COUNT(*) FROM products WHERE stock_qty <= min_limit"
            )),
            "total_suppliers": int(scalar("SELECT COUNT(*) FROM suppliers")),
            "total_users": int(scalar("SELECT COUNT(*) FROM users")),

            "today_sales": _money(scalar(
                "SELECT COALESCE(SUM(net_total), 0) FROM invoices "
                "WHERE date(created_at) = date('now', 'localtime')"
            )),
            "today_invoices": int(scalar(
                "SELECT COUNT(*) FROM invoices "
                "WHERE date(created_at) = date('now', 'localtime')"
            )),

            "month_sales": _money(scalar(
                "SELECT COALESCE(SUM(net_total), 0) FROM invoices "
                "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')"
            )),
            "month_expenses": _money(scalar(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', 'localtime')"
            )),
        }

    return stats


# ===========================================================================
# SETTINGS
# ===========================================================================

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return a single setting value (or `default` when missing)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    """Create or overwrite a setting."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, "" if value is None else str(value)),
        )


def set_settings(values: Dict[str, str]) -> None:
    """Create or overwrite several settings at once."""
    with get_connection() as conn:
        for key, value in values.items():
            conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, "" if value is None else str(value)),
            )


def get_all_settings() -> Dict[str, str]:
    """Return every setting merged on top of the application defaults."""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()

    settings = dict(DEFAULT_SETTINGS)
    settings.update({row["key"]: row["value"] for row in rows})
    return settings


def get_invoice_header() -> str:
    """Header text printed on thermal receipts."""
    return get_setting("invoice_header", DEFAULT_SETTINGS["invoice_header"]) or ""


def get_invoice_footer() -> str:
    """Footer text printed on thermal receipts."""
    return get_setting("invoice_footer", DEFAULT_SETTINGS["invoice_footer"]) or ""


def get_currency_symbol() -> str:
    """Currency symbol used across the UI."""
    return get_setting("currency_symbol", DEFAULT_SETTINGS["currency_symbol"]) or ""


# ===========================================================================
# MAINTENANCE
# ===========================================================================

def backup_database(destination_path: str) -> str:
    """
    Create a consistent backup of the database at `destination_path`.

    Returns the destination path.
    """
    destination_path = os.path.abspath(destination_path)
    os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)

    with get_connection() as source:
        with sqlite3.connect(destination_path) as target:
            source.backup(target)

    return destination_path


def database_exists() -> bool:
    """True when the database file exists on disk."""
    return os.path.exists(DB_PATH)


# ---------------------------------------------------------------------------
# Bootstrap (only when running this module directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    initialize_database()
    print("SIERRA STORE database initialised.")
    print(f"  Path     : {DB_PATH}")
    print(f"  Users    : {count_users()}")
    print(f"  Products : {count_products()}")
    print(f"  Suppliers: {count_suppliers()}")
    print("  Default login -> username: admin | password: admin123")