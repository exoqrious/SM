import sys
from typing import Optional, List
import sqlite3
from datetime import datetime, date, timedelta
from PySide6.QtGui import QShortcut, QKeySequence, QColor, QPalette
from PySide6.QtCore import QTimer
# --- PATCH START: Sound Feedback + PDF / Printer Receipts Imports ---
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtGui import QTextDocument, QPageSize
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog
from pathlib import Path
from PySide6.QtWidgets import QLabel, QVBoxLayout
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# --- PATCH END ---


from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QTabWidget,
    QFormLayout,
    QDateEdit,
    QTextEdit,
    QHeaderView,
    QGroupBox,
    QCheckBox,
    QDialog,
    QGridLayout,
)
# --- PATCH START: Auto-Restock Imports ---
from PySide6.QtWidgets import QDialogButtonBox, QSpinBox, QFormLayout, QGridLayout, QDialog
# --- PATCH END ---
# --- PATCH START: Visual Stock Dashboard (Matplotlib) ---
import matplotlib
matplotlib.use("Agg")  # headless-safe backend
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
# --- PATCH END ---
# --- PATCH START: Export, Email, Google Sheets, AI Analytics Imports ---
import os, ssl, smtplib, json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from sklearn.linear_model import LinearRegression
import numpy as np
# --- PATCH END ---


# --------- Database Layer --------- #

class Database:
    """Simple SQLite wrapper for supermarket POS."""

    def __init__(self, path: str = "supermarket.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()
    def seed_initial_data(self) -> None:
        """Optional: populate sample products if DB empty."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products;")
        if cur.fetchone()[0] == 0:
            products = [
                ("P001", "Rice 1kg", "Grocery", 80.0, 0.0, 20, 5.0, 1),
                ("P002", "Milk 1L", "Dairy", 55.0, 0.0, 30, 10.0, 1),
                ("P003", "Soap Bar", "Personal Care", 25.0, 5.0, 50, 10.0, 1),
            ]
            cur.executemany(
                """
                INSERT INTO products (code, name, category, price, tax_rate, stock, restock_level, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                products,
            )
            self.conn.commit()
            ### >>> PATCH START: Create missing tables ###
            # Ensure all dependent tables exist if running fresh
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    phone TEXT,
                    email TEXT,
                    loyalty_points INTEGER DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime TEXT NOT NULL,
                    customer_id INTEGER,
                    subtotal REAL,
                    discount REAL,
                    tax_total REAL,
                    grand_total REAL,
                    payment_method TEXT,
                    paid_amount REAL,
                    change_due REAL,
                    notes TEXT,
                    FOREIGN KEY (customer_id) REFERENCES customers(id)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS invoice_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER,
                    product_id INTEGER,
                    product_code TEXT,
                    product_name TEXT,
                    quantity REAL,
                    unit_price REAL,
                    tax_rate REAL,
                    line_total REAL,
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                    FOREIGN KEY (product_id) REFERENCES products(id)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)
            self.conn.commit()
            ### <<< PATCH END ###




        # --- PATCH START: Per-Product Auto-Restock Thresholds ---

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                price REAL NOT NULL,
                tax_rate REAL NOT NULL DEFAULT 0,
                stock REAL NOT NULL DEFAULT 0,
                restock_level REAL NOT NULL DEFAULT 5,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)

        # Backward compatibility upgrade
        cur.execute("PRAGMA table_info(products);")
        cols = [c[1] for c in cur.fetchall()]
        if "restock_level" not in cols:
            cur.execute("ALTER TABLE products ADD COLUMN restock_level REAL NOT NULL DEFAULT 5;")
        self.conn.commit()
        # --- PATCH START: Create missing tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                phone TEXT,
                email TEXT,
                loyalty_points INTEGER DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                customer_id INTEGER,
                subtotal REAL,
                discount REAL,
                tax_total REAL,
                grand_total REAL,
                payment_method TEXT,
                paid_amount REAL,
                change_due REAL,
                notes TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER,
                product_id INTEGER,
                product_code TEXT,
                product_name TEXT,
                quantity REAL,
                unit_price REAL,
                tax_rate REAL,
                line_total REAL,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.commit()
        # --- PATCH END ---

    def add_product(self, code, name, category, price, tax_rate, stock, active, restock_level=5.0) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO products (code, name, category, price, tax_rate, stock, restock_level, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (code, name, category, price, tax_rate, stock, restock_level, 1 if active else 0),
        )
        self.conn.commit()

    def update_product(
        self, product_id, code, name, category, price, tax_rate, stock, active, restock_level
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE products
               SET code=?, name=?, category=?, price=?, tax_rate=?, stock=?, restock_level=?, active=?
             WHERE id=?;
            """,
            (code, name, category, price, tax_rate, stock, restock_level, 1 if active else 0, product_id),
        )
        self.conn.commit()

        # --- PATCH END ---
        # ----- Product operations ----- #

    def get_products(self, active_only: bool = True, search_text: Optional[str] = None):
        cur = self.conn.cursor()
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        if active_only:
            query += " AND active = 1"
        if search_text:
            query += " AND (code LIKE ? OR name LIKE ? OR category LIKE ?)"
            like = f"%{search_text}%"
            params.extend([like, like, like])
        query += " ORDER BY name ASC;"
        cur.execute(query, params)
        return cur.fetchall()

    def get_product_by_code(self, code: str):
        """Fetch a single product by its unique code."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM products WHERE code = ? AND active = 1;", (code,))
        return cur.fetchone()


    def deactivate_product(self, product_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("UPDATE products SET active = 0 WHERE id = ?;", (product_id,))
        self.conn.commit()

    # ----- Customer operations ----- #

    def get_customers(self, active_only: bool = True, search_text: Optional[str] = None):

        cur = self.conn.cursor()
        query = "SELECT * FROM customers WHERE 1=1"
        params: list = []
        if active_only:
            query += " AND active = 1"
        if search_text:
            query += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            like = f"%{search_text}%"
            params.extend([like, like, like])
        query += " ORDER BY name ASC"
        cur.execute(query, params)
        return cur.fetchall()

    def add_customer(
        self,
        name: str,
        phone: str,
        email: str,
        loyalty_points: int,
        active: bool,
    ) -> None:
        # Prevent duplicate customer names
        cur = self.conn.cursor()
        # Prevent duplicate customer names
        cur.execute("SELECT COUNT(*) FROM customers WHERE name = ?;", (name,))
        if cur.fetchone()[0] > 0:
            raise ValueError(f"Customer '{name}' already exists.")


        cur.execute(
            """
            INSERT INTO customers (name, phone, email, loyalty_points, active)
            VALUES (?, ?, ?, ?, ?);
            """,
            (name, phone, email, loyalty_points, 1 if active else 0),
        )
        self.conn.commit()

    def update_customer(
        self,
        customer_id: int,
        name: str,
        phone: str,
        email: str,
        loyalty_points: int,
        active: bool,
    ) -> None:
        # Prevent duplicate customer names
        cur = self.conn.cursor()
        # Prevent duplicate customer names (ignore the same customer record)
        cur.execute(
            "SELECT COUNT(*) FROM customers WHERE name = ? AND id != ?;",
            (name, customer_id),
        )
        if cur.fetchone()[0] > 0:
            raise ValueError(f"Customer '{name}' already exists.")

        cur.execute(
            """
            UPDATE customers
               SET name = ?, phone = ?, email = ?, loyalty_points = ?, active = ?
             WHERE id = ?;
            """,
            (name, phone, email, loyalty_points, 1 if active else 0, customer_id),
        )
        self.conn.commit()


    def deactivate_customer(self, customer_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("UPDATE customers SET active = 0 WHERE id = ?;", (customer_id,))
        self.conn.commit()

    # ----- Invoice operations ----- #

    def create_invoice(
        self,
        customer_id: Optional[int],
        cart_items: List[dict],
        global_discount_percent: float,
        payment_method: str,
        paid_amount: float,
        notes: str,
    ):
        """Create invoice, adjust stock, return (invoice_id, totals_dict)."""
        if not cart_items:
            raise ValueError("Cart is empty")

        cur = self.conn.cursor()

        with self.conn:
            cur = self.conn.cursor()

            # Check stock
            for item in cart_items:
                pid = item["product_id"]
                qty = float(item["quantity"])
                cur.execute("SELECT stock FROM products WHERE id = ?;", (pid,))
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"Product not found (id={pid})")
                if row["stock"] < qty:
                    raise ValueError(
                        f"Insufficient stock for {item['name']} "
                        f"(available {row['stock']}, requested {qty})"
                    )

            discount_factor = 1.0 - (global_discount_percent / 100.0)
            subtotal = discount_total = tax_total = grand_total = 0.0

            for item in cart_items:
                price = float(item["price"])
                qty = float(item["quantity"])
                tax_rate = float(item["tax_rate"])
                base = price * qty
                discounted_base = base * discount_factor
                line_discount = base - discounted_base
                tax = discounted_base * (tax_rate / 100.0)
                line_total = discounted_base + tax

                subtotal += base
                discount_total += line_discount
                tax_total += tax
                grand_total += line_total

            if paid_amount < grand_total:
                raise ValueError(
                    f"Paid amount ({paid_amount:.2f}) is less than total ({grand_total:.2f})"
                )

            change_due = paid_amount - grand_total
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            customer_id_db = customer_id if customer_id is not None else None

            cur.execute(
                """
                INSERT INTO invoices (
                    datetime, customer_id, subtotal, discount, tax_total,
                    grand_total, payment_method, paid_amount, change_due, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    now_str,
                    customer_id_db,
                    subtotal,
                    discount_total,
                    tax_total,
                    grand_total,
                    payment_method,
                    paid_amount,
                    change_due,
                    notes,
                ),
            )

            invoice_id = cur.lastrowid

            for item in cart_items:
                pid = item["product_id"]
                qty = float(item["quantity"])
                price = float(item["price"])
                tax_rate = float(item["tax_rate"])
                name = item["name"]
                code = item["code"]

                base = price * qty
                discounted_base = base * discount_factor
                tax = discounted_base * (tax_rate / 100.0)
                line_total = discounted_base + tax

                cur.execute(
                    """
                    INSERT INTO invoice_items (
                        invoice_id, product_id, product_code, product_name,
                        quantity, unit_price, tax_rate, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (invoice_id, pid, code, name, qty, price, tax_rate, line_total),
                )

                # stock update
                cur.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?;",
                    (qty, pid),
                )

        # no explicit commit needed – handled by context manager
        totals = {
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_total": tax_total,
            "grand_total": grand_total,
            "paid_amount": paid_amount,
            "change_due": change_due,
            "datetime": now_str,
        }
        return invoice_id, totals


    def get_invoices_between_dates(self, start: date, end: date):
        cur = self.conn.cursor()
        start_str = f"{start.isoformat()} 00:00:00"
        end_str = f"{end.isoformat()} 23:59:59"
        cur.execute(
            """
            SELECT invoices.*, customers.name AS customer_name
              FROM invoices
         LEFT JOIN customers ON invoices.customer_id = customers.id
             WHERE datetime BETWEEN ? AND ?
          ORDER BY datetime ASC;
            """,
            (start_str, end_str),
        )
        return cur.fetchall()

    def get_invoice_items(self, invoice_id: int):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT * FROM invoice_items
             WHERE invoice_id = ?
          ORDER BY id ASC;
            """,
            (invoice_id,),
        )
        return cur.fetchall()
        # --- PATCH: Dashboard Data Methods ---

    def get_stock_levels(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT name, category, stock, restock_level
              FROM products
             WHERE active = 1
             ORDER BY category, name;
        """)
        return cur.fetchall()

    def get_sales_trend(self, days: int = 30):
        """Return list of (date, total_sales) for last N days."""
        cur = self.conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
        cur.execute(
            """
            SELECT DATE(datetime) AS day, SUM(grand_total) AS total
              FROM invoices
             WHERE datetime >= ?
             GROUP BY DATE(datetime)
             ORDER BY DATE(datetime);
            """,
            (start_date,),
        )
        return cur.fetchall()

    def get_stock_trend(self, days: int = 30):
        """Approximate stock trend from historical average per product."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT DATE('now', '-' || ? || ' day') AS start_date, AVG(stock) AS avg_stock
              FROM products
             WHERE active = 1;
            """,
            (days,),
        )
        avg_stock = cur.fetchone()
        if avg_stock and avg_stock["avg_stock"] is not None:
            return [(datetime.now().strftime("%Y-%m-%d"), avg_stock["avg_stock"])]
        return []

        # ----- Settings operations ----- #
    def get_setting(self, key: str) -> Optional[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        cur = self.conn.cursor()
        cur.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    # --- PATCH START: Export + Analytics DB Methods ---

    def get_all_products_data(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT code, name, category, price, tax_rate, stock, restock_level, active
              FROM products
             ORDER BY category, name;
        """)
        return cur.fetchall()

    def get_all_invoices_data(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT invoices.id, datetime, customers.name AS customer, subtotal, discount, tax_total, grand_total, payment_method
              FROM invoices
         LEFT JOIN customers ON invoices.customer_id = customers.id
          ORDER BY datetime DESC;
        """)
        return cur.fetchall()

    def get_sales_details(self, last_days: int = 30):
        """Detailed sales lines for AI analytics."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT products.name AS product,
                   invoice_items.quantity AS qty,
                   DATE(invoices.datetime) AS day
              FROM invoice_items
              JOIN products ON invoice_items.product_id = products.id
              JOIN invoices ON invoice_items.invoice_id = invoices.id
             WHERE invoices.datetime >= DATE('now', ?)
          ORDER BY invoices.datetime ASC;
            """,
            (f"-{last_days} day",),
        )
        return cur.fetchall()

    # --- PATCH END ---
    # --- PATCH START: Safe DB close ---
    def __del__(self):
        """Safely close SQLite connection on destruction."""
        try:
            self.conn.close()
        except Exception:
            pass
    # --- PATCH END ---

    # --------- UI Helper Functions (GLOBAL) --------- #
    from PySide6.QtWidgets import QApplication, QMessageBox

    def apply_premium_style(app: QApplication) -> None:
        """Apply a modern, high-contrast, premium theme with readable text."""
        style = """
            * {
                font-family: "Segoe UI", "Helvetica Neue", Arial;
                font-size: 11pt;
            }
            QMainWindow { background-color: #e9ebf4; }
            QTabWidget::pane {
                border: 1px solid #c0c4d7;
                border-radius: 12px;
                background: #ffffff;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin: 2px;
                border-radius: 10px;
                background: #d8dcf2;
                color: #222222;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #4a6fff;
                color: #ffffff;
            }
        """
        app.setStyleSheet(style)

    def show_error(parent, message: str) -> None:
        QMessageBox.critical(parent, "Error", message)

    def show_info(parent, message: str) -> None:
        QMessageBox.information(parent, "Info", message)



# --- PATCH START: Sound Feedback Class ---
# --- PATCH START: Real-Time Stock Alerts + Enhanced SoundManager ---

LOW_STOCK_THRESHOLD = 5  # units


class SoundManager:
    """Manages success, error, and warning sounds."""

    def __init__(self):
        self.success = QSoundEffect()
        self.error = QSoundEffect()
        self.warning = QSoundEffect()

        base = Path(".")
        self._load_sound(self.success, base / "success.wav")
        self._load_sound(self.error, base / "error.wav")
        self._load_sound(self.warning, base / "warning.wav")

        for s in (self.success, self.error, self.warning):
            s.setVolume(0.6)

    def _load_sound(self, sound_obj: QSoundEffect, path: Path):
        # --- PATCH START: Safe file check ---
        if not path.exists():
            return
        sound_obj.setSource(QUrl.fromLocalFile(str(path)))
        # --- PATCH END ---


    def play_success(self):
        if self.success.source().isValid():
            self.success.play()

    def play_error(self):
        if self.error.source().isValid():
            self.error.play()

    def play_warning(self):
        if self.warning.source().isValid():
            self.warning.play()
# --- PATCH END ---

# --- PATCH END ---


# --- PATCH START: Auto-Restock Dialog ---

class RestockDialog(QDialog):
    """Popup dialog to restock multiple low-stock items."""

    def __init__(self, db: Database, low_items: list[sqlite3.Row], parent=None):
        super().__init__(parent)
        self.db = db
        self.low_items = low_items
        self.restock_inputs = {}

        self.setWindowTitle("Restock Low Inventory")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("The following items are low on stock:"))
        layout.addSpacing(10)

        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Product</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Current</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Add</b>"), 0, 2)

        for i, item in enumerate(low_items, start=1):
            name_lbl = QLabel(item["name"])
            stock_lbl = QLabel(f"{item['stock']:.2f}")
            spin = QSpinBox()
            spin.setRange(0, 10_000)
            spin.setValue(0)
            grid.addWidget(name_lbl, i, 0)
            grid.addWidget(stock_lbl, i, 1)
            grid.addWidget(spin, i, 2)
            self.restock_inputs[item["id"]] = spin

        layout.addLayout(grid)
        layout.addSpacing(15)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self.resize(450, 300)

    def get_restock_data(self):
        """Return dict {product_id: quantity_to_add}."""
        return {pid: spin.value() for pid, spin in self.restock_inputs.items() if spin.value() > 0}

# --- PATCH END ---

# --------- Billing Tab --------- #

class BillingTab(QWidget):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.cart_items: list[dict] = []
        self.suppress_cart_signals = False
        self.sound = SoundManager()  # ✅ New: sound feedback

        self.init_ui()
        self.load_products()
        self.load_customers()
        self.recalculate_totals()
        self.status_banner = QLabel("")
        self.status_banner.setAlignment(Qt.AlignCenter)
        self.status_banner.setStyleSheet(
            "QLabel { background-color: #f2f2f2; color: #333; padding: 8px; border-radius: 8px; }"
        )
        self.layout().insertWidget(0, self.status_banner)


        # --- NEW: barcode scan buffer ---
        self._scan_buffer = ""
        self._scan_timer = QTimer()
        self._scan_timer.setSingleShot(True)
        self._scan_timer.timeout.connect(self._reset_scan_buffer)

        # Register keyboard shortcuts
        self._init_shortcuts()


    def init_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # Left panel: product search + list
        left_panel = QVBoxLayout()
        product_group = QGroupBox("Products")
        product_layout = QVBoxLayout(product_group)

        search_layout = QHBoxLayout()
        self.product_search_edit = QLineEdit()
        self.product_search_edit.setPlaceholderText("Search products by code, name, category...")
        self.product_search_edit.textChanged.connect(self.load_products)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.product_search_edit)

        self.product_table = QTableWidget(0, 6)
        self.product_table.setHorizontalHeaderLabels(
            ["Code", "Name", "Category", "Price", "Tax%", "Stock"]
        )
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.product_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.product_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.product_table.doubleClicked.connect(self.add_selected_product_to_cart)

        add_layout = QHBoxLayout()
        self.code_input_edit = QLineEdit()
        self.code_input_edit.setPlaceholderText("Scan / Enter product code")
        self.code_add_button = QPushButton("Add by Code")
        self.code_add_button.clicked.connect(self.add_product_by_code)
        add_layout.addWidget(self.code_input_edit)
        add_layout.addWidget(self.code_add_button)

        product_layout.addLayout(search_layout)
        product_layout.addWidget(self.product_table)
        product_layout.addLayout(add_layout)

        left_panel.addWidget(product_group)

        # Right panel: cart + totals + payment
        right_panel = QVBoxLayout()

        cart_group = QGroupBox("Cart")
        cart_layout = QVBoxLayout(cart_group)

        self.cart_table = QTableWidget(0, 6)
        self.cart_table.setHorizontalHeaderLabels(
            ["Code", "Name", "Qty", "Unit Price", "Tax%", "Line Total"]
        )
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cart_table.itemChanged.connect(self.on_cart_item_changed)

        cart_buttons = QHBoxLayout()
        self.remove_item_button = QPushButton("Remove Selected Item")
        self.remove_item_button.clicked.connect(self.remove_selected_cart_item)
        self.new_bill_button = QPushButton("New Bill")
        self.new_bill_button.clicked.connect(self.new_bill)
        cart_buttons.addWidget(self.remove_item_button)
        cart_buttons.addStretch()
        cart_buttons.addWidget(self.new_bill_button)

        cart_layout.addWidget(self.cart_table)
        cart_layout.addLayout(cart_buttons)

        right_panel.addWidget(cart_group)

        # Totals and payment group
        totals_group = QGroupBox("Totals & Payment")
        totals_layout = QGridLayout(totals_group)

        self.global_discount_spin = QDoubleSpinBox()
        self.global_discount_spin.setRange(0, 100)
        self.global_discount_spin.setDecimals(2)
        self.global_discount_spin.setSuffix(" %")
        self.global_discount_spin.valueChanged.connect(self.recalculate_totals)

        self.subtotal_label = QLabel("0.00")
        self.discount_label = QLabel("0.00")
        self.tax_label = QLabel("0.00")
        self.total_label = QLabel("0.00")
        self.change_label = QLabel("0.00")

        self.customer_combo = QComboBox()
        self.payment_method_combo = QComboBox()
        self.payment_method_combo.addItems(["Cash", "Card", "UPI", "Other"])

        self.paid_amount_spin = QDoubleSpinBox()
        self.paid_amount_spin.setRange(0, 10_000_000)
        self.paid_amount_spin.setDecimals(2)
        self.paid_amount_spin.valueChanged.connect(self.recalculate_totals)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes (invoice remark)")

        # Layout positions
        row = 0
        totals_layout.addWidget(QLabel("Customer:"), row, 0)
        totals_layout.addWidget(self.customer_combo, row, 1, 1, 3)

        row += 1
        totals_layout.addWidget(QLabel("Subtotal:"), row, 0)
        totals_layout.addWidget(self.subtotal_label, row, 1)
        totals_layout.addWidget(QLabel("Global Discount:"), row, 2)
        totals_layout.addWidget(self.global_discount_spin, row, 3)

        row += 1
        totals_layout.addWidget(QLabel("Discount Amount:"), row, 0)
        totals_layout.addWidget(self.discount_label, row, 1)
        totals_layout.addWidget(QLabel("Tax Total:"), row, 2)
        totals_layout.addWidget(self.tax_label, row, 3)

        row += 1
        totals_layout.addWidget(QLabel("Grand Total:"), row, 0)
        totals_layout.addWidget(self.total_label, row, 1)
        totals_layout.addWidget(QLabel("Paid Amount:"), row, 2)
        totals_layout.addWidget(self.paid_amount_spin, row, 3)

        row += 1
        totals_layout.addWidget(QLabel("Change:"), row, 0)
        totals_layout.addWidget(self.change_label, row, 1)
        totals_layout.addWidget(QLabel("Payment Method:"), row, 2)
        totals_layout.addWidget(self.payment_method_combo, row, 3)

        row += 1
        totals_layout.addWidget(QLabel("Notes:"), row, 0)
        totals_layout.addWidget(self.notes_edit, row, 1, 1, 3)

        row += 1
        self.save_print_button = QPushButton("Save & Print Invoice")
        self.save_print_button.clicked.connect(self.save_and_print_invoice)
        totals_layout.addWidget(self.save_print_button, row, 0, 1, 4)

        right_panel.addWidget(totals_group)

        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 1)

    # ----- Loading data ----- #

    def load_products(self) -> None:
        search_text = self.product_search_edit.text().strip()
        rows = self.db.get_products(active_only=True, search_text=search_text)
        self.product_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.product_table.setItem(r, 0, QTableWidgetItem(row["code"]))
            self.product_table.setItem(r, 1, QTableWidgetItem(row["name"]))
            self.product_table.setItem(r, 2, QTableWidgetItem(row["category"] or ""))
            self.product_table.setItem(r, 3, QTableWidgetItem(f"{row['price']:.2f}"))
            self.product_table.setItem(r, 4, QTableWidgetItem(f"{row['tax_rate']:.2f}"))
            self.product_table.setItem(r, 5, QTableWidgetItem(f"{row['stock']:.2f}"))

    def load_customers(self) -> None:
        rows = self.db.get_customers(active_only=True)
        self.customer_combo.clear()
        self.customer_combo.addItem("Walk-in Customer", None)
        for row in rows:
            self.customer_combo.addItem(row["name"], row["id"])

    # ----- Cart management ----- #

    def add_selected_product_to_cart(self) -> None:
        row = self.product_table.currentRow()
        if row < 0:
            return
        code = self.product_table.item(row, 0).text()
        product = self.db.get_product_by_code(code)
        if not product:
            show_error(self, "Product no longer available.")
            return
        self.add_product_to_cart(product)

    def add_product_by_code(self) -> None:
        code = self.code_input_edit.text().strip()
        if not code:
            return
        product = self.db.get_product_by_code(code)
        if not product:
            show_error(self, f"No active product with code {code}")
            return
        self.add_product_to_cart(product)
        self.code_input_edit.clear()



    def refresh_cart_table(self) -> None:
        self.suppress_cart_signals = True
        self.cart_table.setRowCount(len(self.cart_items))
        for r, item in enumerate(self.cart_items):
            self.cart_table.setItem(r, 0, QTableWidgetItem(item["code"]))
            self.cart_table.setItem(r, 1, QTableWidgetItem(item["name"]))

            qty_item = QTableWidgetItem(str(item["quantity"]))
            qty_item.setFlags(qty_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.cart_table.setItem(r, 2, qty_item)

            self.cart_table.setItem(r, 3, QTableWidgetItem(f"{item['price']:.2f}"))
            self.cart_table.setItem(r, 4, QTableWidgetItem(f"{item['tax_rate']:.2f}"))

            # Line total computed in recalculate_totals; show placeholder first
            self.cart_table.setItem(r, 5, QTableWidgetItem("0.00"))
        self.suppress_cart_signals = False

    def on_cart_item_changed(self, item: QTableWidgetItem) -> None:
        if self.suppress_cart_signals:
            return
        row = item.row()
        col = item.column()
        if col == 2:  # Qty edited
            text = item.text().strip()
            try:
                qty = float(text)
                if qty <= 0:
                    raise ValueError
            except ValueError:
                show_error(self, "Quantity must be a positive number.")
                # 🩵 FIX 5️⃣ use blockSignals to safely restore value without triggering recursion
                self.cart_table.blockSignals(True)
                item.setText(str(self.cart_items[row]["quantity"]))
                self.cart_table.blockSignals(False)
                return

            self.cart_items[row]["quantity"] = qty
            self.recalculate_totals()

    def remove_selected_cart_item(self) -> None:
        row = self.cart_table.currentRow()
        if row < 0:
            return
        del self.cart_items[row]
        self.refresh_cart_table()
        self.recalculate_totals()

    def new_bill(self) -> None:
        self.cart_items.clear()
        self.refresh_cart_table()
        self.global_discount_spin.setValue(0.0)
        self.paid_amount_spin.setValue(0.0)
        self.notes_edit.clear()
        self.recalculate_totals()

    def recalculate_totals(self) -> None:
        discount_percent = self.global_discount_spin.value()
        discount_factor = 1.0 - (discount_percent / 100.0)
        subtotal = 0.0
        discount_total = 0.0
        tax_total = 0.0
        grand_total = 0.0

        for idx, item in enumerate(self.cart_items):
            price = float(item["price"])
            qty = float(item["quantity"])
            tax_rate = float(item["tax_rate"])
            base = price * qty
            discounted_base = base * discount_factor
            line_discount = base - discounted_base
            tax = discounted_base * (tax_rate / 100.0)
            line_total = discounted_base + tax

            subtotal += base
            discount_total += line_discount
            tax_total += tax
            grand_total += line_total

            # Update line total in table
            if idx < self.cart_table.rowCount():
                self.suppress_cart_signals = True
                self.cart_table.setItem(
                    idx, 5, QTableWidgetItem(f"{line_total:.2f}")
                )
                self.suppress_cart_signals = False

        paid_amount = self.paid_amount_spin.value()
        change = max(0.0, paid_amount - grand_total)

        self.subtotal_label.setText(f"{subtotal:.2f}")
        self.discount_label.setText(f"{discount_total:.2f}")
        self.tax_label.setText(f"{tax_total:.2f}")
        self.total_label.setText(f"{grand_total:.2f}")
        self.change_label.setText(f"{change:.2f}")
    def save_and_print_invoice(self) -> None:
        if not self.cart_items:
            self.sound.play_error()
            show_error(self, "Cart is empty, cannot create invoice.")
            return

        customer_id = self.customer_combo.currentData()
        payment_method = self.payment_method_combo.currentText()
        paid_amount = float(self.paid_amount_spin.value())
        # 🪄 Auto-fill paid amount if it's still zero (full payment)
        if paid_amount == 0:
            paid_amount = float(self.total_label.text())
            self.paid_amount_spin.setValue(paid_amount)

        notes = self.notes_edit.text().strip()
        discount_percent = float(self.global_discount_spin.value())

        try:
            invoice_id, totals = self.db.create_invoice(
                customer_id=customer_id,
                cart_items=self.cart_items,
                global_discount_percent=discount_percent,
                payment_method=payment_method,
                paid_amount=paid_amount,
                notes=notes,
            )
        except ValueError as e:
            self.sound.play_error()
            show_error(self, str(e))
            return

        self.sound.play_success()

        receipt_text = self.build_receipt_text(invoice_id, totals, customer_id, payment_method, notes)

        # Use QTextDocument for print/PDF rendering
        doc = QTextDocument()
        doc.setPlainText(receipt_text)

        try:
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Invoice #{invoice_id} - Preview / Print")
            layout = QVBoxLayout(dlg)

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(receipt_text)
            layout.addWidget(text_edit)

            button_layout = QHBoxLayout()
            btn_print = QPushButton("Print")
            btn_print.clicked.connect(lambda: self._print_invoice(text_edit))

            btn_pdf = QPushButton("Save as PDF")
            btn_pdf.clicked.connect(lambda: self._save_pdf(receipt_text, invoice_id))

            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)

            button_layout.addWidget(btn_print)
            button_layout.addWidget(btn_pdf)
            button_layout.addStretch()
            button_layout.addWidget(btn_close)

            layout.addLayout(button_layout)

            dlg.resize(600, 700)
            dlg.exec()


        except Exception as e:
            show_error(self, f"Failed to open invoice dialog: {e}")





        # --- Auto-Restock Prompt ---
        low_items = []
        for item in self.cart_items:
            product = self.db.get_product_by_code(item["code"])
            if product["stock"] <= product["restock_level"]:

                low_items.append(product)

        if low_items:
            self.sound.play_warning()
            self._show_status_banner("⚠️ Low stock detected! Prompting restock...", "orange")

            dlg = RestockDialog(self.db, low_items, self)
            if dlg.exec() == QDialog.Accepted:
                restock_data = dlg.get_restock_data()
                if restock_data:
                    self._apply_restock(restock_data)
                    self.sound.play_success()
                    self._show_status_banner("✅ Inventory restocked successfully.", "green")
                    show_info(self, "Stock levels updated.")
                else:
                    self._show_status_banner("ℹ️ No changes made.", "gray")

        # --- Low stock check after billing ---
        low_items = []
        for item in self.cart_items:
            product = self.db.get_product_by_code(item["code"])
            if not product:
                continue
            stock_left = product["stock"]
            if stock_left <= LOW_STOCK_THRESHOLD:
                low_items.append((product["name"], stock_left))

        if low_items:
            msg_lines = [
                f"⚠️ LOW STOCK ALERT ({len(low_items)} items):",
                *(f"• {n} ({s} left)" for n, s in low_items),
            ]
            self.sound.play_warning()
            show_info(self, "\n".join(msg_lines))
            self._show_status_banner("⚠️ Low stock detected after billing", "orange")
            # --- PATCH START: move reset after alerts ---
            self.new_bill()
            self.load_products()
            # --- PATCH END ---

    def _print_invoice(self, doc: QTextDocument):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.Accepted:
            doc.print(printer)
            show_info(self, "Invoice sent to printer.")

    def _save_pdf(self, doc: QTextDocument, invoice_id: int):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Invoice as PDF",
            f"Invoice_{invoice_id}.pdf",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(file_path)
        doc.print(printer)
        show_info(self, f"Invoice saved to: {file_path}")


    def build_receipt_text(
        self,
        invoice_id: int,
        totals: dict,
        customer_id: Optional[int],
        payment_method: str,
        notes: str,
    ) -> str:

        customer_name = "Walk-in Customer"
        if customer_id:
            customers = self.db.get_customers(active_only=False)
            for c in customers:
                if c["id"] == customer_id:
                    customer_name = c["name"]
                    break

        lines = []
        lines.append("LUXE MARKET SUPERMARKET")
        lines.append("Premium Billing Receipt")
        lines.append("-" * 40)
        lines.append(f"Invoice #: {invoice_id}")
        lines.append(f"Date: {totals['datetime']}")
        lines.append(f"Customer: {customer_name}")
        lines.append("-" * 40)
        lines.append("{:<4} {:<14} {:>5} {:>7} {:>8}".format("#", "Item", "Qty", "Price", "Total"))

        discount_percent = float(self.global_discount_spin.value())
        discount_factor = 1.0 - (discount_percent / 100.0)

        for idx, item in enumerate(self.cart_items, start=1):
            try:
                name = str(item.get("name", ""))[:14]
                qty = float(item.get("quantity", 0))
                price = float(item.get("price", 0))
                tax_rate = float(item.get("tax_rate", 0))

                base = price * qty
                discounted_base = base * discount_factor
                tax = discounted_base * (tax_rate / 100.0)
                line_total = discounted_base + tax

                lines.append(
                    "{:<4} {:<14} {:>5} {:>7.2f} {:>8.2f}".format(
                        idx, name, qty, price, line_total
                    )
                )
            except Exception as e:
                lines.append(f"Error in item #{idx}: {e}")


        lines.append("-" * 40)
        lines.append(f"Subtotal:      {totals['subtotal']:>10.2f}")
        lines.append(f"Discount:      {totals['discount_total']:>10.2f}")
        lines.append(f"Tax:           {totals['tax_total']:>10.2f}")
        lines.append(f"Grand Total:   {totals['grand_total']:>10.2f}")
        lines.append(f"Paid:          {totals['paid_amount']:>10.2f}")
        lines.append(f"Change:        {totals['change_due']:>10.2f}")
        lines.append(f"Payment: {payment_method}")
        if notes:
            lines.append(f"Notes: {notes}")
        lines.append("-" * 40)
        lines.append("Thank you for shopping with us!")
        return "\n".join(lines)

    def _init_shortcuts(self):
        """Keyboard shortcuts for power users."""
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_bill)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_and_print_invoice)
        QShortcut(QKeySequence("Delete"), self, activated=self.remove_selected_cart_item)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=lambda: self.global_discount_spin.setFocus())
        QShortcut(QKeySequence("Ctrl+P"), self, activated=lambda: self.paid_amount_spin.setFocus())
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.product_search_edit.setFocus())

    def keyPressEvent(self, event):
        """Intercept global key input for barcode scanning."""
        key = event.key()
        text = event.text()
        if text.isalnum():
            self._scan_buffer += text
            self._scan_timer.start(300)  # reset if no input within 300ms
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self._scan_buffer:
                code = self._scan_buffer.strip()
                self._reset_scan_buffer()
                product = self.db.get_product_by_code(code)
                if product:
                    self.add_product_to_cart(product)
                    self._flash_cart_item(product["code"])
                    self.sound.play_success()
                else:
                    self.sound.play_error()
                    show_error(self, f"Product not found: {code}")

            return  # prevent Enter propagation
        else:
            super().keyPressEvent(event)

    def _reset_scan_buffer(self):
        """Clear temporary barcode buffer."""
        self._scan_buffer = ""

    def _flash_cart_item(self, code: str):
        """Flash added product row briefly to confirm scan success."""
        for r in range(self.cart_table.rowCount()):
            if self.cart_table.item(r, 0).text() == code:
                original_color = self.cart_table.palette().color(QPalette.Base)
                highlight = QColor("#c8ffc8")  # light green flash
                for c in range(self.cart_table.columnCount()):
                    item = self.cart_table.item(r, c)
                    if item:
                        item.setBackground(highlight)
                QTimer.singleShot(
                    500,
                    lambda r=r: [
                        self.cart_table.item(r, c).setBackground(original_color)
                        for c in range(self.cart_table.columnCount())
                        if self.cart_table.item(r, c)
                    ],
                )
                break


    def _show_status_banner(self, text: str, color: str):
        color_map = {
            "red": "#ffcccc",
            "orange": "#fff4cc",
            "green": "#ccffcc",
            "gray": "#f2f2f2",
        }
        self.status_banner.setText(text)
        bg = color_map.get(color, "#f2f2f2")
        self.status_banner.setStyleSheet(
            f"QLabel {{ background-color: {bg}; color: #222; padding: 8px; border-radius: 8px; font-weight: 600; }}"
        )
        QTimer.singleShot(3000, self._clear_status_banner)


    def _clear_status_banner(self):
        self.status_banner.setText("")
        self.status_banner.setStyleSheet(
            "QLabel { background-color: #f2f2f2; color: #333; padding: 8px; border-radius: 8px; }"
        )

    def _apply_restock(self, restock_data: dict[int, int]) -> None:
        cur = self.db.conn.cursor()
        for pid, qty in restock_data.items():
            cur.execute("UPDATE products SET stock = stock + ? WHERE id = ?;", (qty, pid))
        self.db.conn.commit()
        self.load_products()

# --------- Products Tab --------- #

    def add_product_to_cart(self, product_row: sqlite3.Row) -> None:
        pid = product_row["id"]
        restock_level = float(product_row["restock_level"]) if "restock_level" in product_row.keys() else 5.0
        stock_left = float(product_row["stock"])
        restock_level = float(product_row["restock_level"]) if "restock_level" in product_row.keys() else 5.0
        name = product_row["name"]

        if stock_left <= 0:
            self.sound.play_error()
            self._show_status_banner(f"❌ '{name}' is OUT OF STOCK!", "red")
            show_error(self, f"Cannot add '{name}' — out of stock.")
            return
        elif stock_left <= restock_level:
            self.sound.play_warning()
            self._show_status_banner(f"⚠️ Low stock for '{name}' ({stock_left} left)", "orange")

        for item in self.cart_items:
            if item["product_id"] == pid:
                item["quantity"] += 1
                break
        else:
            self.cart_items.append(
                {
                    "product_id": pid,
                    "code": product_row["code"],
                    "name": product_row["name"],
                    "price": float(product_row["price"]),
                    "tax_rate": float(product_row["tax_rate"]),
                    "quantity": 1.0,
                }
            )
        self.refresh_cart_table()
        self.recalculate_totals()

        # --------- Products Tab --------- #

class ProductsTab(QWidget):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.current_product_id: Optional[int] = None
        self.init_ui()
        self.load_products()

    def init_ui(self) -> None:
        main_layout = QHBoxLayout(self)

        # Left: Product table and search
        left_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search products...")
        self.search_edit.textChanged.connect(self.load_products)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_products)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(refresh_btn)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Code", "Name", "Category", "Price", "Tax%", "Stock", "Restock @"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.on_row_double_clicked)

        left_layout.addLayout(search_layout)
        left_layout.addWidget(self.table)

        # Right: Product details form
        right_group = QGroupBox("Product Details")
        form_layout = QFormLayout(right_group)

        self.code_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.category_edit = QLineEdit()
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 1_000_000)
        self.price_spin.setDecimals(2)
        self.tax_spin = QDoubleSpinBox()
        self.tax_spin.setRange(0, 100)
        self.tax_spin.setDecimals(2)
        self.stock_spin = QDoubleSpinBox()
        self.stock_spin.setRange(0, 1_000_000)
        self.stock_spin.setDecimals(2)
        self.restock_spin = QDoubleSpinBox()
        self.restock_spin.setRange(0, 10_000)
        self.restock_spin.setDecimals(2)
        self.active_check = QCheckBox("Active")

        form_layout.addRow("Code:", self.code_edit)
        form_layout.addRow("Name:", self.name_edit)
        form_layout.addRow("Category:", self.category_edit)
        form_layout.addRow("Price:", self.price_spin)
        form_layout.addRow("Tax %:", self.tax_spin)
        form_layout.addRow("Stock:", self.stock_spin)
        form_layout.addRow("Restock Level:", self.restock_spin)
        form_layout.addRow("", self.active_check)

        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self.new_product)
        self.save_btn = QPushButton("Save / Update")
        self.save_btn.clicked.connect(self.save_product)
        self.deactivate_btn = QPushButton("Deactivate")
        self.deactivate_btn.clicked.connect(self.deactivate_product)
        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.deactivate_btn)
        form_layout.addRow(btn_layout)

        main_layout.addLayout(left_layout, 2)
        main_layout.addWidget(right_group, 1)

    # ---------- DB actions ---------- #

    def load_products(self) -> None:
        search_text = self.search_edit.text().strip()
        rows = self.db.get_products(active_only=False, search_text=search_text)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(row["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(row["code"]))
            self.table.setItem(r, 2, QTableWidgetItem(row["name"]))
            self.table.setItem(r, 3, QTableWidgetItem(row["category"] or ""))
            self.table.setItem(r, 4, QTableWidgetItem(f"{row['price']:.2f}"))
            self.table.setItem(r, 5, QTableWidgetItem(f"{row['tax_rate']:.2f}"))
            self.table.setItem(r, 6, QTableWidgetItem(f"{row['stock']:.2f}"))
            self.table.setItem(r, 7, QTableWidgetItem(f"{row['restock_level']:.2f}"))

    def on_row_double_clicked(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.current_product_id = int(self.table.item(row, 0).text())
        self.code_edit.setText(self.table.item(row, 1).text())
        self.name_edit.setText(self.table.item(row, 2).text())
        self.category_edit.setText(self.table.item(row, 3).text())
        self.price_spin.setValue(float(self.table.item(row, 4).text()))
        self.tax_spin.setValue(float(self.table.item(row, 5).text()))
        self.stock_spin.setValue(float(self.table.item(row, 6).text()))
        self.restock_spin.setValue(float(self.table.item(row, 7).text()))
        # Load active flag from DB
        products = self.db.get_products(active_only=False)
        for p in products:
            if p["id"] == self.current_product_id:
                self.active_check.setChecked(bool(p["active"]))
                break

    def new_product(self) -> None:
        self.current_product_id = None
        self.code_edit.clear()
        self.name_edit.clear()
        self.category_edit.clear()
        self.price_spin.setValue(0)
        self.tax_spin.setValue(0)
        self.stock_spin.setValue(0)
        self.restock_spin.setValue(5)
        self.active_check.setChecked(True)

    def save_product(self) -> None:
        code = self.code_edit.text().strip()
        name = self.name_edit.text().strip()
        category = self.category_edit.text().strip()
        price = float(self.price_spin.value())
        tax_rate = float(self.tax_spin.value())
        stock = float(self.stock_spin.value())
        restock_level = float(self.restock_spin.value())
        active = self.active_check.isChecked()

        if not code or not name:
            show_error(self, "Code and Name are required.")
            return

        try:
            if self.current_product_id is None:
                self.db.add_product(code, name, category, price, tax_rate, stock, active, restock_level)
                show_info(self, "Product added.")
            else:
                self.db.update_product(
                    self.current_product_id, code, name, category, price, tax_rate, stock, active, restock_level
                )
                show_info(self, "Product updated.")
        except Exception as e:
            show_error(self, str(e))

        self.load_products()

    def deactivate_product(self) -> None:
        if self.current_product_id is None:
            show_error(self, "Select a product to deactivate.")
            return
        self.db.deactivate_product(self.current_product_id)
        show_info(self, "Product deactivated.")
        self.load_products()


# --------- Customers Tab --------- #

class CustomersTab(QWidget):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.current_customer_id: Optional[int] = None
        self.init_ui()
        self.load_customers()

    def init_ui(self) -> None:
        main_layout = QHBoxLayout(self)

        left_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search customers...")
        self.search_edit.textChanged.connect(self.load_customers)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_customers)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(refresh_btn)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Phone", "Email", "Loyalty", "Active"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.on_row_double_clicked)

        left_layout.addLayout(search_layout)
        left_layout.addWidget(self.table)

        right_group = QGroupBox("Customer Details")
        form_layout = QFormLayout(right_group)

        self.name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.loyalty_spin = QSpinBox()
        self.loyalty_spin.setRange(0, 1_000_000)
        self.active_check = QCheckBox("Active")

        form_layout.addRow("Name:", self.name_edit)
        form_layout.addRow("Phone:", self.phone_edit)
        form_layout.addRow("Email:", self.email_edit)
        form_layout.addRow("Loyalty Points:", self.loyalty_spin)
        form_layout.addRow("", self.active_check)

        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self.new_customer)
        self.save_btn = QPushButton("Save / Update")
        self.save_btn.clicked.connect(self.save_customer)
        self.deactivate_btn = QPushButton("Deactivate")
        self.deactivate_btn.clicked.connect(self.deactivate_customer)
        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.deactivate_btn)

        form_layout.addRow(btn_layout)

        main_layout.addLayout(left_layout, 2)
        main_layout.addWidget(right_group, 1)

    def load_customers(self) -> None:
        search_text = self.search_edit.text().strip()
        rows = self.db.get_customers(active_only=False, search_text=search_text)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(row["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(row["name"]))
            self.table.setItem(r, 2, QTableWidgetItem(row["phone"] or ""))
            self.table.setItem(r, 3, QTableWidgetItem(row["email"] or ""))
            self.table.setItem(r, 4, QTableWidgetItem(str(row["loyalty_points"])))
            self.table.setItem(r, 5, QTableWidgetItem("Yes" if row["active"] else "No"))

    def on_row_double_clicked(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.current_customer_id = int(self.table.item(row, 0).text())
        self.name_edit.setText(self.table.item(row, 1).text())
        self.phone_edit.setText(self.table.item(row, 2).text())
        self.email_edit.setText(self.table.item(row, 3).text())
        self.loyalty_spin.setValue(int(self.table.item(row, 4).text()))

        customers = self.db.get_customers(active_only=False)
        for c in customers:
            if c["id"] == self.current_customer_id:
                self.active_check.setChecked(bool(c["active"]))
                break

    def new_customer(self) -> None:
        self.current_customer_id = None
        self.name_edit.clear()
        self.phone_edit.clear()
        self.email_edit.clear()
        self.loyalty_spin.setValue(0)
        self.active_check.setChecked(True)

    def save_customer(self) -> None:
        name = self.name_edit.text().strip()
        phone = self.phone_edit.text().strip()
        email = self.email_edit.text().strip()
        loyalty = int(self.loyalty_spin.value())
        active = self.active_check.isChecked()

        if not name:
            show_error(self, "Name is required.")
            return

        try:
            if self.current_customer_id is None:
                self.db.add_customer(name, phone, email, loyalty, active)
                show_info(self, "Customer added.")
            else:
                self.db.update_customer(self.current_customer_id, name, phone, email, loyalty, active)
                show_info(self, "Customer updated.")
        except ValueError as e:
            show_error(self, str(e))
        self.load_customers()



    def deactivate_customer(self) -> None:
        if self.current_customer_id is None:
            show_error(self, "Select a customer to deactivate.")
            return
        self.db.deactivate_customer(self.current_customer_id)
        show_info(self, "Customer deactivated.")
        self.load_customers()
        self.new_customer()


# --------- Reports Tab --------- #

class ReportsTab(QWidget):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        filter_layout = QHBoxLayout()
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)

        today = QDate.currentDate()
        self.start_date_edit.setDate(today.addDays(-7))
        self.end_date_edit.setDate(today)

        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self.load_reports)
        # --- PATCH START: Export / Email / Cloud Buttons ---
        self.export_btn = QPushButton("💾 Export Sales Data")
        self.export_btn.clicked.connect(self.export_sales_data)

        self.email_btn = QPushButton("📧 Send Email Report")
        self.email_btn.clicked.connect(self.send_email_report)

        self.sync_btn = QPushButton("☁️ Sync to Google Sheets")
        self.sync_btn.clicked.connect(self.sync_to_google)
        # --- PATCH END ---

        filter_layout.addWidget(QLabel("From:"))
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(QLabel("To:"))
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addWidget(self.load_btn)
        filter_layout.addWidget(self.export_btn)
        filter_layout.addWidget(self.email_btn)
        filter_layout.addWidget(self.sync_btn)
        filter_layout.addStretch()


        main_layout.addLayout(filter_layout)

        # Summary
        summary_group = QGroupBox("Summary")
        summary_layout = QHBoxLayout(summary_group)
        self.total_invoices_label = QLabel("0")
        self.total_subtotal_label = QLabel("0.00")
        self.total_discount_label = QLabel("0.00")
        self.total_tax_label = QLabel("0.00")
        self.total_grand_label = QLabel("0.00")

        summary_layout.addWidget(QLabel("Invoices:"))
        summary_layout.addWidget(self.total_invoices_label)
        summary_layout.addSpacing(15)
        summary_layout.addWidget(QLabel("Subtotal:"))
        summary_layout.addWidget(self.total_subtotal_label)
        summary_layout.addSpacing(15)
        summary_layout.addWidget(QLabel("Discount:"))
        summary_layout.addWidget(self.total_discount_label)
        summary_layout.addSpacing(15)
        summary_layout.addWidget(QLabel("Tax:"))
        summary_layout.addWidget(self.total_tax_label)
        summary_layout.addSpacing(15)
        summary_layout.addWidget(QLabel("Grand:"))
        summary_layout.addWidget(self.total_grand_label)
        summary_layout.addStretch()

        main_layout.addWidget(summary_group)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "DateTime",
                "Customer",
                "Subtotal",
                "Discount",
                "Tax",
                "Total",
                "Payment",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self.show_invoice_detail)

        main_layout.addWidget(self.table)

    def load_reports(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        start_pydate = date(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_pydate = date(end_qdate.year(), end_qdate.month(), end_qdate.day())

        rows = self.db.get_invoices_between_dates(start_pydate, end_pydate)
        self.table.setRowCount(len(rows))

        total_subtotal = 0.0
        total_discount = 0.0
        total_tax = 0.0
        total_grand = 0.0

        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(row["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(row["datetime"]))
            self.table.setItem(r, 2, QTableWidgetItem(row["customer_name"] or "Walk-in"))
            self.table.setItem(r, 3, QTableWidgetItem(f"{row['subtotal']:.2f}"))
            self.table.setItem(r, 4, QTableWidgetItem(f"{row['discount']:.2f}"))
            self.table.setItem(r, 5, QTableWidgetItem(f"{row['tax_total']:.2f}"))
            self.table.setItem(r, 6, QTableWidgetItem(f"{row['grand_total']:.2f}"))
            self.table.setItem(r, 7, QTableWidgetItem(row["payment_method"]))

            total_subtotal += row["subtotal"]
            total_discount += row["discount"]
            total_tax += row["tax_total"]
            total_grand += row["grand_total"]

        self.total_invoices_label.setText(str(len(rows)))
        self.total_subtotal_label.setText(f"{total_subtotal:.2f}")
        self.total_discount_label.setText(f"{total_discount:.2f}")
        self.total_tax_label.setText(f"{total_tax:.2f}")
        self.total_grand_label.setText(f"{total_grand:.2f}")

    def show_invoice_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        invoice_id = int(self.table.item(row, 0).text())
        items = self.db.get_invoice_items(invoice_id)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Invoice #{invoice_id} - Details")
        layout = QVBoxLayout(dlg)

        text = QTextEdit()
        text.setReadOnly(True)

        lines = []
        lines.append(f"Invoice #{invoice_id} - Item Details")
        lines.append("-" * 40)
        lines.append("{:<4} {:<18} {:>5} {:>7} {:>8}".format("#", "Item", "Qty", "Price", "Total"))
        for i, it in enumerate(items, start=1):
            name = (it["product_name"] or "")[:18]
            qty = it["quantity"]
            price = it["unit_price"]
            total = it["line_total"]
            lines.append(
                "{:<4} {:<18} {:>5} {:>7.2f} {:>8.2f}".format(
                    i, name, qty, price, total
                )
            )

        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.resize(600, 500)
        dlg.exec_()



        # --- PATCH START: Export, Email, and Google Sheets ---

    def export_sales_data(self):
        rows = self.db.get_all_invoices_data()
        if not rows:
            show_info(self, "No invoice data available.")
            return

        df = pd.DataFrame(
            rows,
            columns=["Invoice ID", "DateTime", "Customer", "Subtotal", "Discount", "Tax", "Total", "Payment Method"],
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sales Data",
            f"sales_report_{datetime.now():%Y-%m-%d}",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not file_path:
            return

        if file_path.endswith(".csv"):
            df.to_csv(file_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(file_path, index=False, engine="openpyxl")

        show_info(self, f"✅ Sales data exported successfully to:\n{file_path}")

    def send_email_report(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select File to Email", "", "All Files (*)"
            )
            if not file_path:
                return

            sender = "your_email@gmail.com"
            receiver = "recipient_email@example.com"
            password = "your_app_password"

            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = receiver
            msg["Subject"] = "Supermarket Sales Report"
            body = "Please find attached the latest sales report."
            msg.attach(MIMEText(body, "plain"))

            with open(file_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file_path)}")
            msg.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                server.login(sender, password)
                server.sendmail(sender, receiver, msg.as_string())

            show_info(self, "✅ Email sent successfully.")
        except Exception as e:
            show_error(self, f"❌ Failed to send email:\n{e}")

    def sync_to_google(self):
        try:
            creds = Credentials.from_service_account_file(
                "google_credentials.json",
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            client = gspread.authorize(creds)
            sheet = client.open("Supermarket POS Sync").sheet1
            rows = self.db.get_all_invoices_data()
            if not rows:
                show_info(self, "No data to sync.")
                return
            df = pd.DataFrame(
                rows,
                columns=["ID", "DateTime", "Customer", "Subtotal", "Discount", "Tax", "Total", "Payment"],
            )
            sheet.clear()
            sheet.update([df.columns.values.tolist()] + df.values.tolist())
            show_info(self, "✅ Synced to Google Sheets successfully.")
        except Exception as e:
            show_error(self, f"❌ Google Sheets sync failed:\n{e}")

    # --- PATCH END ---

        # --------- Dashboard Tab --------- #

class MplCanvas(FigureCanvasQTAgg):
    """Qt canvas wrapper for Matplotlib figures."""
    def __init__(self, width=6, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)


class DashboardTab(QWidget):
    """Visual stock and sales analytics dashboard."""
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.init_ui()
        self.refresh_charts()

    def init_ui(self):
        layout = QVBoxLayout(self)
        header = QLabel("📊 Stock & Sales Dashboard – Visual Overview")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        layout.addSpacing(10)   # ✅ Adds breathing space below title


        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Trend Range:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["7 Days", "30 Days", "90 Days"])
        filter_layout.addWidget(self.range_combo)
        self.refresh_btn = QPushButton("🔄 Refresh Charts")
        self.refresh_btn.clicked.connect(self.refresh_charts)
        filter_layout.addStretch()
        filter_layout.addWidget(self.refresh_btn)
        layout.addLayout(filter_layout)

        # Charts
        self.bar_canvas = MplCanvas(width=8, height=5)
        self.pie_canvas = MplCanvas(width=8, height=4)
        self.trend_canvas = MplCanvas(width=8, height=5)
        layout.addWidget(self.bar_canvas)
        layout.addWidget(self.pie_canvas)
        layout.addWidget(self.trend_canvas)

    def refresh_charts(self):
        data = self.db.get_stock_levels()
        if not data:
            show_info(self, "No active products found.")
            return

        # --- Chart 1: Stock vs Restock ---
        names = [r["name"] for r in data]
        stocks = [r["stock"] for r in data]
        restock_lvls = [r["restock_level"] for r in data]
        categories = [r["category"] or "Uncategorized" for r in data]

        self.bar_canvas.fig.clear()
        self.bar_canvas.fig.clear()
        ax1 = self.bar_canvas.fig.add_subplot(111)
        x = range(len(names))
        ax1.bar(x, stocks, label="Current Stock", alpha=0.7)
        ax1.bar(x, restock_lvls, label="Restock Level", alpha=0.7)
        ax1.set_xticks(x)
        ax1.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
        ax1.set_ylabel("Quantity")
        ax1.set_title("Stock vs Restock Thresholds")
        ax1.legend()
        self.bar_canvas.draw()

        # --- Chart 2: Category Pie ---
        self.pie_canvas.fig.clear()
        ax2 = self.pie_canvas.fig.add_subplot(111)
        cat_totals = {}
        for cat, qty in zip(categories, stocks):
            cat_totals[cat] = cat_totals.get(cat, 0) + qty
        ax2.pie(cat_totals.values(), labels=cat_totals.keys(), autopct="%1.1f%%", startangle=90)
        ax2.set_title("Stock Distribution by Category")
        self.pie_canvas.fig.subplots_adjust(top=0.85)  # ✅ Gives space for title
        self.pie_canvas.draw()

        # --- Chart 3: Sales vs Stock (Twin-Axis for Supermarkets) ---
        days = int(self.range_combo.currentText().split()[0])
        sales = self.db.get_sales_trend(days)
        stock = self.db.get_stock_trend(days)

        dates = [r["day"] for r in sales]
        sales_values = [r["total"] for r in sales]
        avg_stock = stock[0][1] if stock else 0

        self.trend_canvas.fig.clear()
        fig = self.trend_canvas.fig
        ax1 = fig.add_subplot(111)

        # Left Y-axis → Sales
        if sales:
            ax1.plot(dates, sales_values, "o-", color="royalblue", label="Sales Total (₹)", linewidth=2)
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Sales (₹)", color="royalblue")
        ax1.tick_params(axis="y", labelcolor="royalblue")
        ax1.set_ylim(bottom=0)   # ✅ Prevents squashed chart when sales > 10k


        # Right Y-axis → Stock
        ax2 = ax1.twinx()
        ax2.plot(dates, [avg_stock]*len(dates), "--", color="seagreen", label=f"Avg Stock ({avg_stock:.1f})", linewidth=1.8)
        ax2.set_ylabel("Stock (Qty)", color="seagreen")
        ax2.tick_params(axis="y", labelcolor="seagreen")

        # Titles and legend
        fig.suptitle(f"Sales & Stock Trends (Last {days} Days)", fontsize=12, fontweight="bold")
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc="upper left")

        fig.autofmt_xdate(rotation=45)
        fig.tight_layout(rect=[0, 0, 1, 0.95])   # ✅ Prevents legend cutoff
        self.trend_canvas.draw()



        # --- PATCH START: X-axis spacing (fixed) ---
        import matplotlib.ticker
        ax1.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(8))
        # --- PATCH END ---



# --- PATCH START: AI Insights Tab (Enhanced with Forecast Chart) ---

class AIInsightsEngine:
    """Handles analytics, forecasting, and recommendations."""
    def __init__(self, db: Database):
        self.db = db

    def get_sales_dataframe(self, days: int = 30) -> pd.DataFrame:
        rows = self.db.get_sales_details(days)
        if not rows:
            return pd.DataFrame(columns=["Product", "Qty", "Day"])
        df = pd.DataFrame(rows, columns=["Product", "Qty", "Day"])
        df["Day"] = pd.to_datetime(df["Day"])
        return df

    def top_products(self, df: pd.DataFrame, n: int = 5) -> pd.Series:
        return df.groupby("Product")["Qty"].sum().sort_values(ascending=False).head(n)

    def slow_products(self, df: pd.DataFrame, n: int = 5) -> pd.Series:
        return df.groupby("Product")["Qty"].sum().sort_values(ascending=True).head(n)

    def forecast_sales(self, df: pd.DataFrame, days_forward: int = 7) -> pd.DataFrame:
        """Forecast total daily sales using Linear Regression."""
        daily = df.groupby("Day")["Qty"].sum().reset_index()
        daily["t"] = np.arange(len(daily))
        if len(daily) < 3:
            return pd.DataFrame(columns=["Day", "Forecast"])
        model = LinearRegression()
        model.fit(daily[["t"]], daily["Qty"])
        future_t = np.arange(len(daily), len(daily) + days_forward).reshape(-1, 1)
        preds = model.predict(future_t)
        future_dates = pd.date_range(daily["Day"].max() + pd.Timedelta(days=1), periods=days_forward)
        return pd.DataFrame({"Day": future_dates, "Forecast": preds})

    def restock_suggestions(self) -> pd.DataFrame:
        rows = self.db.get_stock_levels()
        df = pd.DataFrame(rows, columns=["name", "category", "stock", "restock_level"])
        return df[df["stock"] <= df["restock_level"]]

    def top_customers(self, days: int = 30) -> pd.Series:
        rows = self.db.get_all_invoices_data()
        if not rows:
            return pd.Series(dtype=float)
        df = pd.DataFrame(rows, columns=["ID", "DateTime", "Customer", "Subtotal", "Discount", "Tax", "Total", "Payment"])
        df["DateTime"] = pd.to_datetime(df["DateTime"])
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df["DateTime"] >= cutoff]
        return df.groupby("Customer")["Total"].sum().sort_values(ascending=False).head(5)


class AIInsightsTab(QWidget):
    """Enhanced AI Insights Dashboard with chart and export."""
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.engine = AIInsightsEngine(db)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        header = QLabel("🧠 AI Insights & Forecast Dashboard")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(header)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Analyze Period:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["7 Days", "30 Days", "90 Days"])
        controls.addWidget(self.range_combo)

        self.refresh_btn = QPushButton("🔍 Generate Insights")
        self.refresh_btn.clicked.connect(self.generate_insights)
        controls.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("💾 Export Insights")
        self.export_btn.clicked.connect(self.export_insights)
        controls.addWidget(self.export_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Insights Text
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text, 2)

        # Forecast Chart
        self.chart_canvas = MplCanvas(width=6, height=4, dpi=100)
        layout.addWidget(self.chart_canvas, 3)

    def generate_insights(self):
        try:
            days = int(self.range_combo.currentText().split()[0])
            df = self.engine.get_sales_dataframe(days)
            if df.empty:
                self.result_text.setPlainText("No sales data available for this period.")
                self.chart_canvas.fig.clear()
                self.chart_canvas.draw()
                return

            summary = []

            # Top / slow products
            top = self.engine.top_products(df)
            slow = self.engine.slow_products(df)
            summary.append(f"🏆 Top {len(top)} Products (Last {days} days):")
            summary.extend([f"  • {p}: {q:.0f} units" for p, q in top.items()])
            summary.append("")
            summary.append(f"🐢 Slowest {len(slow)} Products:")
            summary.extend([f"  • {p}: {q:.0f} units" for p, q in slow.items()])
            summary.append("")

            # Restock suggestions
            low = self.engine.restock_suggestions()
            if not low.empty:
                summary.append("⚠️ Restock Recommendations:")
                for _, row in low.iterrows():
                    summary.append(f"  • {row['name']} (Stock: {row['stock']}, Restock @ {row['restock_level']})")
                summary.append("")
            else:
                summary.append("✅ All items are above restock thresholds.\n")

            # Top customers
            top_cust = self.engine.top_customers(days)
            if not top_cust.empty:
                summary.append("💎 Top Customers:")
                for name, total in top_cust.items():
                    summary.append(f"  • {name}: ₹{total:,.2f}")
                summary.append("")

            # Forecast
            forecast = self.engine.forecast_sales(df)
            if not forecast.empty:
                summary.append("📈 Next 7-Day Sales Forecast:")
                for _, row in forecast.iterrows():
                    summary.append(f"  • {row['Day'].strftime('%Y-%m-%d')}: {row['Forecast']:.0f} units")
                summary.append("")
                self.plot_forecast(forecast)
            else:
                summary.append("⚙️ Not enough data for forecast.")
                self.chart_canvas.fig.clear()
                self.chart_canvas.draw()

            self.result_text.setPlainText("\n".join(summary))

        except Exception as e:
            self.result_text.setPlainText(f"❌ Error generating insights:\n{e}")

    def plot_forecast(self, forecast_df: pd.DataFrame):
        """Draw forecast line chart."""
        self.chart_canvas.fig.clear()
        ax = self.chart_canvas.fig.add_subplot(111)
        ax.plot(forecast_df["Day"], forecast_df["Forecast"], marker="o", linestyle="-")
        ax.set_title("Projected Daily Sales (Next 7 Days)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Predicted Units Sold")
        ax.tick_params(axis="x", rotation=45)
        self.chart_canvas.fig.tight_layout()
        self.chart_canvas.draw()

    def export_insights(self):
        text = self.result_text.toPlainText().strip()
        if not text:
            show_info(self, "No insights to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save AI Insights",
            f"ai_insights_{datetime.now():%Y-%m-%d}.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        show_info(self, f"✅ Insights exported successfully to:\n{file_path}")

# --- PATCH END ---

# --------- Main Window --------- #

class MainWindow(QMainWindow):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Luxe Supermarket Billing System")
        self.resize(1300, 750)

        tabs = QTabWidget()
        tabs.addTab(BillingTab(db, self), "Billing / POS")
        tabs.addTab(ProductsTab(db, self), "Products")
        tabs.addTab(CustomersTab(db, self), "Customers")
        tabs.addTab(ReportsTab(db, self), "Reports")
        tabs.addTab(DashboardTab(db, self), "Dashboard")
        tabs.addTab(AIInsightsTab(db, self), "AI Insights")

        self.setCentralWidget(tabs)

    # --------- UI Helper Functions (GLOBAL) --------- #
from PySide6.QtWidgets import QApplication, QMessageBox

def apply_premium_style(app: QApplication) -> None:
    """Apply a luxurious, glass-like UI theme with premium color palette."""
    style = """
        * {
            font-family: 'Segoe UI', 'Helvetica Neue', 'Avenir Next', 'SF Pro Display';
            font-size: 11.5pt;
        }

        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 #f9f9fb, stop:1 #eceef5);
        }

        QTabWidget::pane {
            border: 1px solid #d0d4e6;
            border-radius: 14px;
            background: #ffffff;
            margin-top: 8px;
        }

        QTabBar::tab {
            background: #f0f2fa;
            color: #222;
            padding: 8px 18px;
            border-radius: 10px;
            margin-right: 6px;
            font-weight: 600;
        }

        QTabBar::tab:hover {
            background: #e0e5ff;
            color: #111;
        }

        QTabBar::tab:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #4a6fff, stop:1 #6a89ff);
            color: white;
            font-weight: 700;
        }

        QGroupBox {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #d6d9e9;
            border-radius: 12px;
            margin-top: 10px;
            padding: 12px;
        }

        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 #637dff, stop:1 #4a6fff);
            color: white;
            font-weight: 600;
            border: none;
            border-radius: 10px;
            padding: 8px 14px;
            min-width: 100px;
        }

        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 #738cff, stop:1 #5c7aff);
        }

        QPushButton:pressed {
            background: #3e59e3;
        }

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QDateEdit {
            border: 1px solid #c5cae9;
            border-radius: 8px;
            padding: 5px 7px;
            background-color: #fafbff;
        }

        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QComboBox:focus, QTextEdit:focus {
            border: 1px solid #4a6fff;
            background-color: #ffffff;
        }

        QHeaderView::section {
            background: #f0f2fa;
            color: #222;
            border: none;
            padding: 6px;
            font-weight: 600;
        }

        QTableWidget {
            gridline-color: #dce0f0;
            selection-background-color: #4a6fff;
            selection-color: white;
            alternate-background-color: #f7f8fc;
        }

        QMessageBox {
            background-color: #ffffff;
        }

        QLabel {
            color: #222;
        }

        QScrollBar:vertical {
            background: #f0f2fa;
            width: 12px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background: #bcc3de;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical:hover {
            background: #98a2d0;
        }
    """
    app.setStyleSheet(style)


def show_error(parent, message: str) -> None:
    QMessageBox.critical(parent, "Error", message)

def show_info(parent, message: str) -> None:
    QMessageBox.information(parent, "Info", message)

    # ------------------ IMPORTS ------------------
from PySide6.QtWidgets import (
    QApplication, QSplashScreen, QLabel, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QPalette, QColor, QPixmap, QFont
from PySide6.QtCore import Qt, QPropertyAnimation, QTimer
import sys

# ------------------ SPLASH SCREEN CLASS ------------------
class LuxeSplashScreen(QSplashScreen):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.label = QLabel(self)
        self.label.setText("Luxe Market POS")
        self.label.setFont(QFont("Georgia", 28, QFont.Bold))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                  stop:0 #2e3b62, stop:1 #6a89ff);
                border-radius: 20px;
                padding: 30px;
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.label.setGraphicsEffect(shadow)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.label.setGeometry(self.rect())

        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(1000)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.start()

    def show_and_fade(self, duration=2000, on_finish=None):
        self.show()
        QTimer.singleShot(duration, lambda: self.fade_out(on_finish))

    def fade_out(self, on_finish=None):
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(800)
        self.opacity_anim.setStartValue(1)
        self.opacity_anim.setEndValue(0)
        self.opacity_anim.finished.connect(lambda: self._done(on_finish))
        self.opacity_anim.start()

    def _done(self, on_finish=None):
        self.close()
        if on_finish:
            on_finish()

# ------------------ MAIN FUNCTION ------------------
def main() -> None:
    app = QApplication(sys.argv)

    # 🌈 Apply Fusion base + luxury palette with proper text contrast
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#f4f6fb"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f2f4fa"))
    palette.setColor(QPalette.Text, QColor("#1a1a1a"))
    palette.setColor(QPalette.WindowText, QColor("#1a1a1a"))
    palette.setColor(QPalette.Button, QColor("#4a6fff"))
    palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.Highlight, QColor("#4a6fff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipText, QColor("#1a1a1a"))
    app.setPalette(palette)

    # 🎨 Apply your premium stylesheet (define this function somewhere above)
    apply_premium_style(app)

    # 🗄️ Initialize the database
    db = Database()

    # ✅ Keep MainWindow alive after showing
    window_holder = {}

    def show_main_window():
        window_holder["window"] = MainWindow(db)
        window_holder["window"].showMaximized()

    # 🚀 Show splash screen, then show main window
    splash = LuxeSplashScreen()
    splash.show_and_fade(on_finish=show_main_window)

    # 🧼 Start event loop
    sys.exit(app.exec())

# ------------------ ENTRY POINT ------------------
if __name__ == "__main__":
    main()
