import streamlit as st
import libsql
import pandas as pd
import bcrypt
import plotly.express as px
from datetime import datetime, date
from fpdf import FPDF
import base64
import re
import streamlit.components.v1 as components

# ============================================================
#               PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Shahi Tardka - Business Manager",
    page_icon="🌶️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
#               CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #fef2f2 0%, #fff7ed 50%, #fffbeb 100%); }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #b91c1c 0%, #7f1d1d 60%, #78350f 100%);
    }
    section[data-testid="stSidebar"] * { color: #fff !important; }
    section[data-testid="stSidebar"] .stRadio label { color: #fff !important; }
    h1, h2, h3 { color: #7f1d1d !important; font-weight: 800 !important; }
    .stButton>button {
        background: linear-gradient(90deg, #dc2626, #b45309) !important;
        color: white !important; border: none !important;
        border-radius: 10px !important; font-weight: 600 !important;
        padding: 8px 20px !important;
    }
    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
    .block-container { padding-top: 2rem; }
    .big-title {
        font-size: 2.2rem; font-weight: 900;
        background: linear-gradient(90deg, #dc2626, #b45309);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
#               HELPERS
# ============================================================

def fmt_date(d):
    if d is None:
        return ""
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(d, fmt)
                return dt.strftime("%d-%m-%Y")
            except Exception:
                continue
        return d
    try:
        return d.strftime("%d-%m-%Y")
    except Exception:
        return str(d)


def to_iso(d):
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")


def title_case(s):
    if s is None:
        return ""
    return str(s).title()


# ============================================================
#               DATABASE
# ============================================================

@st.cache_resource
def get_db():
    return libsql.connect(
        st.secrets["TURSO_URL"],
        auth_token=st.secrets["TURSO_TOKEN"]
    )


def run(sql, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args)
    conn.commit()
    q.clear()
    return cur


@st.cache_data(ttl=120, show_spinner=False, max_entries=80)
def q(sql, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description] if cur.description else []
    return pd.DataFrame(cur.fetchall(), columns=cols)


# ============================================================
#               SHORT SERIAL
# ============================================================

def next_serial(prefix, table, column):
    try:
        df = q(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL")
        used = set()
        for v in df[column].tolist():
            s = str(v)
            if "-" in s:
                try:
                    used.add(int(s.split("-")[-1]))
                except Exception:
                    pass
        n = 1
        while n in used:
            n += 1
        return f"{prefix}-{n}"
    except Exception:
        return f"{prefix}-1"


# ============================================================
#               DB INIT
# ============================================================

@st.cache_resource
def init_db():
    conn = get_db()
    cur = conn.cursor()
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, phone TEXT, address TEXT,
        opening_balance REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, phone TEXT, address TEXT,
        opening_balance REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS raw_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, unit TEXT DEFAULT 'Kg',
        rate REAL DEFAULT 0, stock_qty REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, sku TEXT, unit TEXT DEFAULT 'Pcs',
        sale_price REAL DEFAULT 0, cost_price REAL DEFAULT 0,
        stock_qty REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS product_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        sale_price REAL NOT NULL,
        cost_price REAL NOT NULL,
        effective_from DATETIME DEFAULT CURRENT_TIMESTAMP,
        changed_by TEXT
    );
    CREATE TABLE IF NOT EXISTS raw_material_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_material_id INTEGER NOT NULL,
        rate REAL NOT NULL,
        effective_from DATETIME DEFAULT CURRENT_TIMESTAMP,
        changed_by TEXT
    );
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_no TEXT UNIQUE, customer_id INTEGER,
        date TEXT NOT NULL, total REAL DEFAULT 0,
        discount REAL DEFAULT 0, paid REAL DEFAULT 0,
        notes TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER, product_id INTEGER,
        product_name TEXT, qty REAL NOT NULL,
        rate REAL NOT NULL, amount REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_no TEXT UNIQUE, vendor_id INTEGER,
        date TEXT NOT NULL, total REAL DEFAULT 0,
        paid REAL DEFAULT 0, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_id INTEGER, raw_material_id INTEGER,
        raw_name TEXT, qty REAL NOT NULL,
        rate REAL NOT NULL, amount REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sale_returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_no TEXT UNIQUE, customer_id INTEGER,
        date TEXT NOT NULL, total REAL DEFAULT 0, notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sale_return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER, product_id INTEGER,
        product_name TEXT, qty REAL NOT NULL,
        rate REAL NOT NULL, amount REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, type TEXT NOT NULL,
        party_type TEXT NOT NULL, party_id INTEGER,
        amount REAL NOT NULL, description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS production (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, product_id INTEGER,
        qty_produced REAL NOT NULL, wastage REAL DEFAULT 0,
        notes TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS production_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        production_id INTEGER, raw_material_id INTEGER,
        raw_name TEXT, qty_used REAL NOT NULL,
        rate REAL NOT NULL, amount REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL, description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);
    CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
    CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_party ON transactions(party_type, party_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
    CREATE INDEX IF NOT EXISTS idx_purchases_vendor ON purchases(vendor_id);
    CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase ON purchase_items(purchase_id);
    CREATE INDEX IF NOT EXISTS idx_prod_price_history ON product_price_history(product_id);
    CREATE INDEX IF NOT EXISTS idx_rm_price_history ON raw_material_price_history(raw_material_id);
    """
    for stmt in schema.split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)

    for tbl, col in [("sale_items", "product_name"), ("purchase_items", "raw_name"),
                     ("sale_return_items", "product_name"), ("production_materials", "raw_name")]:
        try:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} TEXT")
        except Exception:
            pass

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", pw))

    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        items = [
            ("Chili Powder 250 G", 250, 0, 250), ("Chili Powder 100 G", 100, 0, 100),
            ("Chili Flakes 250 G", 250, 0, 250), ("Chili Flakes 100 G", 100, 0, 100),
            ("Turmeric Powder 250 G", 250, 0, 250), ("Turmeric Powder 100 G", 100, 0, 100),
            ("Chili 20 Rs", 20, 0, 20), ("Chili 10 Rs", 10, 0, 10),
            ("Turmeric 20 Rs", 20, 0, 20), ("Turmeric 10 Rs", 10, 0, 10),
            ("Whole Coriander", 1, 0, 0), ("Other Spices", 1, 0, 0),
        ]
        for name, price, cost, stock in items:
            cur.execute(
                "INSERT INTO products (name, sale_price, cost_price, stock_qty, unit) VALUES (?,?,?,?,?)",
                (name, price, cost, stock, "Pcs"),
            )
    conn.commit()
    return True


try:
    init_db()
except Exception as e:
    st.error(f"DB init error: {e}")


# ============================================================
#               LOGIN
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None


def login_page():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<div style='text-align:center;font-size:4rem'>🌶️</div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center'>Shahi Tardka</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#78716c'>Business Management System</p>", unsafe_allow_html=True)
        st.write("")
        with st.form("login"):
            u = st.text_input("Username", value="admin")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Sign In", use_container_width=True)
            if ok:
                df = q("SELECT * FROM users WHERE username = ?", (u,))
                if len(df) and bcrypt.checkpw(p.encode(), df.iloc[0]["password_hash"].encode()):
                    st.session_state.user = {"id": int(df.iloc[0]["id"]), "username": u}
                    st.rerun()
                else:
                    st.error("Invalid username or password")


if not st.session_state.user:
    login_page()
    st.stop()

user = st.session_state.user


# ============================================================
#               HTML BUILDERS FOR PRINT (DIRECT PRINT)
# ============================================================

def esc(s):
    """Escape HTML entities."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def html_table(headers, rows, summary=None, title="", extra_header=None):
    """Build printable HTML string."""
    h = """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8">
    <title>Print</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, Helvetica, sans-serif; padding: 20px; color: #000; }
        .header { text-align: center; margin-bottom: 18px; }
        .header h1 { color: #dc2626; font-size: 26px; margin: 0 0 4px 0; }
        .header p { color: #666; margin: 0; font-size: 12px; }
        .title { text-align: center; font-size: 18px; font-weight: bold; margin: 16px 0 10px 0; }
        .extra { text-align: center; font-size: 12px; color: #333; margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; margin-top: 8px; }
        th { background: #dc2626; color: #fff; padding: 8px; font-size: 12px; border: 1px solid #b91c1c; }
        td { padding: 7px; font-size: 12px; border: 1px solid #ccc; }
        tr:nth-child(even) td { background: #fef2f2; }
        .summary { text-align: right; margin-top: 14px; font-weight: bold; font-size: 13px; }
        .summary div { margin: 3px 0; }
        @media print {
            @page { margin: 12mm; }
            body { padding: 0; }
        }
    </style>
    </head><body>
    <div class="header">
        <h1>SHAHI TARDKA</h1>
        <p>Premium Spices &amp; Foods</p>
    </div>
    """
    if title:
        h += f'<div class="title">{esc(title)}</div>'
    if extra_header:
        h += '<div class="extra">'
        for line in extra_header:
            h += f"{esc(line)}<br>"
        h += "</div>"

    if headers:
        h += "<table><thead><tr>"
        for x in headers:
            h += f"<th>{esc(x)}</th>"
        h += "</tr></thead><tbody>"
        for row in rows:
            h += "<tr>"
            for c in row:
                h += f"<td>{esc(c)}</td>"
            h += "</tr>"
        h += "</tbody></table>"

    if summary:
        h += '<div class="summary">'
        for line in summary:
            h += f"<div>{esc(line)}</div>"
        h += "</div>"

    h += """
    <script>
        window.onload = function() {
            setTimeout(function() { window.print(); }, 300);
        };
    </script>
    </body></html>
    """
    return h


def direct_print(html_str, height=1):
    """Render HTML in hidden iframe and auto-trigger window.print()."""
    components.html(html_str, height=height, scrolling=False)


def print_button(html_str, label="🖨️ Print Now", key=None):
    """Button that triggers direct print when clicked."""
    if st.button(label, key=key, use_container_width=False):
        direct_print(html_str)
        st.success("✅ Print dialog khul gaya — apna printer select karein")


# ============================================================
#               SIDEBAR
# ============================================================

st.sidebar.markdown("<h2 style='text-align:center'>🌶️ Shahi Tardka</h2>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='text-align:center;font-size:0.85rem'>👤 {user['username']}</p>", unsafe_allow_html=True)
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "📊 Dashboard", "🛒 Sale Entry", "🛍️ Purchase Entry", "↩️ Sale Return",
        "💰 Cash / Bank", "📦 Stock Report", "🏭 Production", "🧾 Expenses",
        "📒 Ledger", "📈 Reports", "🍽️ Products", "🧂 Raw Materials",
        "👥 Customers", "🚚 Vendors", "⚙️ Master Setup", "💾 Backup / Restore",
    ],
    label_visibility="collapsed",
)

if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()


# ============================================================
#               DASHBOARD
# ============================================================

if menu == "📊 Dashboard":
    st.markdown("<h1 class='big-title'>Dashboard</h1>", unsafe_allow_html=True)
    st.caption("Real-Time Overview Of Your Business")

    summary = q("""
        SELECT
            (SELECT COALESCE(SUM(total),0) FROM sales) as sales,
            (SELECT COALESCE(SUM(total),0) FROM purchases) as purchases,
            (SELECT COALESCE(SUM(amount),0) FROM expenses) as expenses
    """)
    s = summary.iloc[0]["sales"]
    p = summary.iloc[0]["purchases"]
    e = summary.iloc[0]["expenses"]
    profit = s - p - e

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💵 Total Sales", f"Rs. {s:,.0f}")
    c2.metric("🛍️ Purchases", f"Rs. {p:,.0f}")
    c3.metric("🧾 Expenses", f"Rs. {e:,.0f}")
    c4.metric("📈 Net Profit", f"Rs. {profit:,.0f}", delta=f"{profit:+,.0f}")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        d = q("""SELECT date, SUM(total) as total FROM sales
                 WHERE date >= date('now','-14 days')
                 GROUP BY date ORDER BY date""")
        if len(d):
            d["date_display"] = d["date"].apply(fmt_date)
            fig = px.area(d, x="date_display", y="total", title="Last 14 Days Sales",
                          color_discrete_sequence=["#dc2626"])
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No Sales Yet")

    with col2:
        m = q("""SELECT substr(date,1,7) as month, SUM(total) as total FROM sales
                 GROUP BY month ORDER BY month DESC LIMIT 6""")
        if len(m):
            fig = px.bar(m.iloc[::-1], x="month", y="total", title="Monthly Sales",
                         color_discrete_sequence=["#b45309"])
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No Sales Yet")

    st.markdown("### ⚠️ Low Stock Alerts")
    low = q("SELECT name, stock_qty FROM products WHERE stock_qty < 10 ORDER BY stock_qty LIMIT 8")
    if len(low):
        st.dataframe(low, use_container_width=True, hide_index=True)
    else:
        st.success("All Products Sufficiently Stocked ✅")


# ============================================================
#               SALE ENTRY
# ============================================================

elif menu == "🛒 Sale Entry":
    st.markdown("<h1 class='big-title'>Sale Entry</h1>", unsafe_allow_html=True)

    customers = q("SELECT id, name FROM customers ORDER BY name")
    products = q("SELECT id, name, sale_price, stock_qty FROM products ORDER BY name")

    if len(customers) == 0 or len(products) == 0:
        st.warning("Pehle Customers Aur Products Add Karo")
        st.stop()

    if "cart" not in st.session_state:
        st.session_state.cart = []

    if "auto_inv" not in st.session_state:
        st.session_state.auto_inv = next_serial("INV", "sales", "invoice_no")

    col1, col2, col3 = st.columns(3)
    with col1:
        cust = st.selectbox("Customer", customers["name"].tolist())
        cust_id = int(customers[customers["name"] == cust].iloc[0]["id"])
    with col2:
        inv_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
    with col3:
        inv_no = st.text_input("Invoice #", value=st.session_state.auto_inv)

    st.markdown("### Add Items")
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    with c1:
        prod = st.selectbox("Product", products["name"].tolist(), key="sale_prod")
        p_row = products[products["name"] == prod].iloc[0]
    with c2:
        qty = st.number_input("Qty", min_value=0.01, value=1.0, step=1.0, key="sale_qty")
    with c3:
        rate = st.number_input("Rate", min_value=0.0, value=float(p_row["sale_price"]), key="sale_rate")
    with c4:
        st.write(""); st.write("")
        if st.button("➕ Add"):
            st.session_state.cart.append({
                "product_id": int(p_row["id"]), "name": prod,
                "qty": qty, "rate": rate, "amount": qty * rate,
            })
            st.rerun()

    if st.session_state.cart:
        st.dataframe(pd.DataFrame(st.session_state.cart), use_container_width=True, hide_index=True)
        subtotal = sum(x["amount"] for x in st.session_state.cart)

        d1, d2, d3 = st.columns(3)
        with d1:
            discount = st.number_input("Discount", min_value=0.0, value=0.0)
        total = subtotal - discount
        with d2:
            st.metric("Total", f"Rs. {total:,.0f}")
        with d3:
            paid = st.number_input("Paid", min_value=0.0, value=float(total))

        colA, colB, colC = st.columns(3)
        if colA.button("💾 Save Sale", use_container_width=True):
            cur = run(
                "INSERT INTO sales (invoice_no, customer_id, date, total, discount, paid) VALUES (?,?,?,?,?,?)",
                (inv_no, cust_id, to_iso(inv_date), total, discount, paid),
            )
            sale_id = cur.lastrowid
            for it in st.session_state.cart:
                run("""INSERT INTO sale_items (sale_id, product_id, product_name, qty, rate, amount)
                       VALUES (?,?,?,?,?,?)""",
                    (sale_id, it["product_id"], it["name"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?",
                    (it["qty"], it["product_id"]))
            if paid > 0:
                run("""INSERT INTO transactions (date, type, party_type, party_id, amount, description)
                       VALUES (?,?,?,?,?,?)""",
                    (to_iso(inv_date), "cash_receipt", "customer", cust_id, paid, f"Sale {inv_no}"))
            st.success(f"✅ Saved: {inv_no}")
            st.session_state.cart = []
            st.session_state.auto_inv = next_serial("INV", "sales", "invoice_no")
            st.rerun()
        if colB.button("🗑️ Clear Cart", use_container_width=True):
            st.session_state.cart = []
            st.rerun()

        # ---- PRINT INVOICE (DIRECT) ----
        if colC.button("🖨️ Print Invoice", use_container_width=True):
            rows = []
            for i, it in enumerate(st.session_state.cart, 1):
                rows.append([i, it["name"], f"{it['qty']:g}", f"{it['rate']:.2f}", f"{it['amount']:.2f}"])
            html_str = html_table(
                ["#", "Item", "Qty", "Rate", "Amount"],
                rows,
                summary=[
                    f"Subtotal: Rs. {subtotal:,.2f}",
                    f"Discount: Rs. {discount:,.2f}",
                    f"TOTAL: Rs. {total:,.2f}",
                    f"Paid: Rs. {paid:,.2f}",
                    f"Balance: Rs. {(total-paid):,.2f}",
                ],
                title=f"Invoice: {inv_no}",
                extra_header=[
                    f"Date: {fmt_date(inv_date)}",
                    f"Customer: {title_case(cust)}",
                ],
            )
            direct_print(html_str)
            st.success("✅ Print dialog khul gaya — printer select karein")


# ============================================================
#               PURCHASE ENTRY
# ============================================================

elif menu == "🛍️ Purchase Entry":
    st.markdown("<h1 class='big-title'>Purchase Entry</h1>", unsafe_allow_html=True)
    vendors = q("SELECT id, name FROM vendors ORDER BY name")
    raws = q("SELECT id, name, rate, unit FROM raw_materials ORDER BY name")

    if len(vendors) == 0 or len(raws) == 0:
        st.warning("Pehle Vendors Aur Raw Materials Add Karo")
        st.stop()

    if "p_cart" not in st.session_state:
        st.session_state.p_cart = []

    if "auto_bill" not in st.session_state:
        st.session_state.auto_bill = next_serial("BILL", "purchases", "bill_no")

    c1, c2, c3 = st.columns(3)
    with c1:
        v = st.selectbox("Vendor", vendors["name"].tolist())
        v_id = int(vendors[vendors["name"] == v].iloc[0]["id"])
    with c2:
        p_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="p_date")
    with c3:
        bill_no = st.text_input("Bill #", value=st.session_state.auto_bill)

    st.markdown("### Add Items")
    a, b, c, d = st.columns([3, 1, 1, 1])
    with a:
        rname = st.selectbox("Raw Material", raws["name"].tolist(), key="pur_item")
        r_row = raws[raws["name"] == rname].iloc[0]
    with b:
        pqty = st.number_input("Qty", min_value=0.01, value=1.0, key="pur_qty")
    with c:
        prate = st.number_input("Rate", min_value=0.0, value=float(r_row["rate"]), key="pur_rate")
    with d:
        st.write(""); st.write("")
        if st.button("➕ Add", key="pur_add"):
            st.session_state.p_cart.append({
                "raw_material_id": int(r_row["id"]), "name": rname,
                "qty": pqty, "rate": prate, "amount": pqty * prate,
            })
            st.rerun()

    if st.session_state.p_cart:
        st.dataframe(pd.DataFrame(st.session_state.p_cart), use_container_width=True, hide_index=True)
        p_total = sum(x["amount"] for x in st.session_state.p_cart)
        st.metric("Total", f"Rs. {p_total:,.0f}")
        paid_p = st.number_input("Paid", min_value=0.0, value=float(p_total), key="pur_paid")

        cA, cB, cC = st.columns(3)
        if cA.button("💾 Save Purchase", use_container_width=True):
            cur = run(
                "INSERT INTO purchases (bill_no, vendor_id, date, total, paid) VALUES (?,?,?,?,?)",
                (bill_no, v_id, to_iso(p_date), p_total, paid_p),
            )
            pid = cur.lastrowid
            for it in st.session_state.p_cart:
                run("""INSERT INTO purchase_items (purchase_id, raw_material_id, raw_name, qty, rate, amount)
                       VALUES (?,?,?,?,?,?)""",
                    (pid, it["raw_material_id"], it["name"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE raw_materials SET stock_qty = stock_qty + ?, rate = ? WHERE id = ?",
                    (it["qty"], it["rate"], it["raw_material_id"]))
                run("""INSERT INTO raw_material_price_history (raw_material_id, rate, changed_by)
                       VALUES (?,?,?)""", (it["raw_material_id"], it["rate"], user["username"]))
            if paid_p > 0:
                run("""INSERT INTO transactions (date, type, party_type, party_id, amount, description)
                       VALUES (?,?,?,?,?,?)""",
                    (to_iso(p_date), "cash_payment", "vendor", v_id, paid_p, f"Purchase {bill_no}"))
            st.success(f"✅ Saved: {bill_no}")
            st.session_state.p_cart = []
            st.session_state.auto_bill = next_serial("BILL", "purchases", "bill_no")
            st.rerun()
        if cB.button("🗑️ Clear", use_container_width=True):
            st.session_state.p_cart = []
            st.rerun()
        if cC.button("🖨️ Print Bill", use_container_width=True):
            rows = []
            for i, it in enumerate(st.session_state.p_cart, 1):
                rows.append([i, it["name"], f"{it['qty']:g}", f"{it['rate']:.2f}", f"{it['amount']:.2f}"])
            html_str = html_table(
                ["#", "Item", "Qty", "Rate", "Amount"],
                rows,
                summary=[f"TOTAL: Rs. {p_total:,.2f}", f"Paid: Rs. {paid_p:,.2f}"],
                title=f"Purchase Bill: {bill_no}",
                extra_header=[f"Date: {fmt_date(p_date)}", f"Vendor: {title_case(v)}"],
            )
            direct_print(html_str)
            st.success("✅ Print dialog khul gaya")


# ============================================================
#               SALE RETURN
# ============================================================

elif menu == "↩️ Sale Return":
    st.markdown("<h1 class='big-title'>Sale Return</h1>", unsafe_allow_html=True)
    customers = q("SELECT id, name FROM customers ORDER BY name")
    products = q("SELECT id, name, sale_price FROM products ORDER BY name")

    if len(customers) == 0 or len(products) == 0:
        st.warning("Pehle Customers Aur Products Add Karo")
        st.stop()

    if "r_cart" not in st.session_state:
        st.session_state.r_cart = []

    if "auto_ret" not in st.session_state:
        st.session_state.auto_ret = next_serial("RET", "sale_returns", "return_no")

    c1, c2, c3 = st.columns(3)
    with c1:
        rc = st.selectbox("Customer", customers["name"].tolist())
        rc_id = int(customers[customers["name"] == rc].iloc[0]["id"])
    with c2:
        r_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="r_date")
    with c3:
        r_no = st.text_input("Return #", value=st.session_state.auto_ret)

    a, b, c, d = st.columns([3, 1, 1, 1])
    with a:
        rp = st.selectbox("Product", products["name"].tolist(), key="ret_prod")
        rp_row = products[products["name"] == rp].iloc[0]
    with b:
        rq = st.number_input("Qty", min_value=0.01, value=1.0, key="ret_qty")
    with c:
        rr = st.number_input("Rate", min_value=0.0, value=float(rp_row["sale_price"]), key="ret_rate")
    with d:
        st.write(""); st.write("")
        if st.button("➕ Add", key="ret_add"):
            st.session_state.r_cart.append({
                "product_id": int(rp_row["id"]), "name": rp,
                "qty": rq, "rate": rr, "amount": rq * rr,
            })
            st.rerun()

    if st.session_state.r_cart:
        st.dataframe(pd.DataFrame(st.session_state.r_cart), use_container_width=True, hide_index=True)
        r_total = sum(x["amount"] for x in st.session_state.r_cart)
        st.metric("Total Return", f"Rs. {r_total:,.0f}")

        if st.button("💾 Save Return", use_container_width=True):
            cur = run(
                "INSERT INTO sale_returns (return_no, customer_id, date, total) VALUES (?,?,?,?)",
                (r_no, rc_id, to_iso(r_date), r_total),
            )
            rid = cur.lastrowid
            for it in st.session_state.r_cart:
                run("""INSERT INTO sale_return_items (return_id, product_id, product_name, qty, rate, amount)
                       VALUES (?,?,?,?,?,?)""",
                    (rid, it["product_id"], it["name"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                    (it["qty"], it["product_id"]))
            st.success(f"✅ Return Saved: {r_no}")
            st.session_state.r_cart = []
            st.session_state.auto_ret = next_serial("RET", "sale_returns", "return_no")
            st.rerun()


# ============================================================
#               CASH / BANK
# ============================================================

elif menu == "💰 Cash / Bank":
    st.markdown("<h1 class='big-title'>Cash / Bank Transactions</h1>", unsafe_allow_html=True)

    with st.form("txn"):
        c1, c2 = st.columns(2)
        with c1:
            t_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
            t_type = st.selectbox("Type", ["Cash Receipt", "Cash Payment", "Bank Receipt", "Bank Payment"])
            t_type_db = t_type.lower().replace(" ", "_")
        with c2:
            p_type = st.selectbox("Party Type", ["Customer", "Vendor"])
            if p_type == "Customer":
                parties = q("SELECT id, name FROM customers ORDER BY name")
            else:
                parties = q("SELECT id, name FROM vendors ORDER BY name")
            p_name = st.selectbox("Party", parties["name"].tolist() if len(parties) else [])
        amount = st.number_input("Amount", min_value=0.0, value=0.0)
        desc = st.text_input("Description")
        ok = st.form_submit_button("💾 Save")
        if ok and amount > 0 and len(parties):
            p_id = int(parties[parties["name"] == p_name].iloc[0]["id"])
            run("""INSERT INTO transactions (date, type, party_type, party_id, amount, description)
                   VALUES (?,?,?,?,?,?)""",
                (to_iso(t_date), t_type_db, p_type.lower(), p_id, amount, desc))
            st.success("✅ Saved")
            st.rerun()

    st.markdown("### Recent Transactions")
    df = q("""SELECT date, type, party_type, party_id, amount, description
              FROM transactions ORDER BY id DESC LIMIT 50""")
    if len(df):
        df["date"] = df["date"].apply(fmt_date)
        df["type"] = df["type"].apply(lambda x: str(x).replace("_", " ").title())
        df["party_type"] = df["party_type"].apply(lambda x: str(x).title())
        df.columns = [c.replace("_", " ").title() for c in df.columns]
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
#               STOCK REPORT
# ============================================================

elif menu == "📦 Stock Report":
    st.markdown("<h1 class='big-title'>Stock Report</h1>", unsafe_allow_html=True)

    t1, t2 = st.tabs(["📦 Finished Goods", "🧂 Raw Materials"])

    with t1:
        df = q("SELECT id, name, sku, unit, sale_price, cost_price, stock_qty FROM products ORDER BY name")
        if len(df):
            df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            total_val = (df["Stock Qty"] * df["Cost Price"]).sum()
            st.metric("Total Stock Value (At Cost)", f"Rs. {total_val:,.0f}")

    with t2:
        df2 = q("SELECT id, name, unit, rate, stock_qty FROM raw_materials ORDER BY name")
        if len(df2):
            df2["Weight"] = df2.apply(lambda r: f"{r['stock_qty']:g} {r['unit']}", axis=1)
            df2.columns = [c.replace("_", " ").title() for c in df2.columns]
        st.dataframe(df2, use_container_width=True, hide_index=True)
        if len(df2):
            total_val2 = (df2["Stock Qty"] * df2["Rate"]).sum()
            st.metric("Total Raw Material Value", f"Rs. {total_val2:,.0f}")


# ============================================================
#               PRODUCTION
# ============================================================

elif menu == "🏭 Production":
    st.markdown("<h1 class='big-title'>Production (With Wastage)</h1>", unsafe_allow_html=True)
    products = q("SELECT id, name FROM products ORDER BY name")
    raws = q("SELECT id, name, rate FROM raw_materials ORDER BY name")

    if len(products) == 0:
        st.warning("Pehle Products Add Karo")
        st.stop()

    if "prod_mats" not in st.session_state:
        st.session_state.prod_mats = []

    c1, c2, c3 = st.columns(3)
    with c1:
        pr_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="pr_date")
    with c2:
        pr_prod = st.selectbox("Product Produced", products["name"].tolist())
        pr_pid = int(products[products["name"] == pr_prod].iloc[0]["id"])
    with c3:
        qty_prod = st.number_input("Qty Produced", min_value=0.01, value=1.0)

    wastage = st.number_input("Wastage (In Same Unit)", min_value=0.0, value=0.0)
    notes = st.text_input("Notes")

    st.markdown("### Raw Materials Used")
    a, b, c, d = st.columns([3, 1, 1, 1])
    with a:
        rm = st.selectbox("Raw Material", raws["name"].tolist() if len(raws) else [])
        rm_row = raws[raws["name"] == rm].iloc[0] if len(raws) else None
    with b:
        rm_qty = st.number_input("Qty", min_value=0.01, value=1.0, key="rm_qty")
    with c:
        rm_rate = st.number_input("Rate", min_value=0.0,
                                   value=float(rm_row["rate"]) if rm_row is not None else 0.0,
                                   key="rm_rate")
    with d:
        st.write(""); st.write("")
        if st.button("➕ Add", key="prod_add"):
            st.session_state.prod_mats.append({
                "raw_material_id": int(rm_row["id"]), "name": rm,
                "qty": rm_qty, "rate": rm_rate, "amount": rm_qty * rm_rate,
            })
            st.rerun()

    if st.session_state.prod_mats:
        st.dataframe(pd.DataFrame(st.session_state.prod_mats), use_container_width=True, hide_index=True)
        total_cost = sum(x["amount"] for x in st.session_state.prod_mats)
        st.metric("Total Production Cost", f"Rs. {total_cost:,.0f}")

        if st.button("💾 Save Production", use_container_width=True):
            cur = run(
                "INSERT INTO production (date, product_id, qty_produced, wastage, notes) VALUES (?,?,?,?,?)",
                (to_iso(pr_date), pr_pid, qty_prod, wastage, notes),
            )
            prod_id = cur.lastrowid
            for it in st.session_state.prod_mats:
                run("""INSERT INTO production_materials (production_id, raw_material_id, raw_name, qty_used, rate, amount)
                       VALUES (?,?,?,?,?,?)""",
                    (prod_id, it["raw_material_id"], it["name"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE raw_materials SET stock_qty = stock_qty - ? WHERE id = ?",
                    (it["qty"], it["raw_material_id"]))
            run("UPDATE products SET stock_qty = stock_qty + ?, cost_price = ? WHERE id = ?",
                (qty_prod, total_cost / qty_prod if qty_prod else 0, pr_pid))
            run("""INSERT INTO product_price_history (product_id, sale_price, cost_price, changed_by)
                   VALUES (?, (SELECT sale_price FROM products WHERE id=?), ?, ?)""",
                (pr_pid, pr_pid, total_cost / qty_prod if qty_prod else 0, user["username"]))
            st.success("✅ Production Saved")
            st.session_state.prod_mats = []
            st.rerun()

    st.markdown("### Production History")
    hist = q("""SELECT p.id, p.date, pr.name as product, p.qty_produced, p.wastage, p.notes
                FROM production p LEFT JOIN products pr ON p.product_id = pr.id
                ORDER BY p.id DESC LIMIT 30""")
    if len(hist):
        hist["date"] = hist["date"].apply(fmt_date)
        hist.columns = [c.replace("_", " ").title() for c in hist.columns]
    st.dataframe(hist, use_container_width=True, hide_index=True)


# ============================================================
#               EXPENSES
# ============================================================

elif menu == "🧾 Expenses":
    st.markdown("<h1 class='big-title'>Expenses</h1>", unsafe_allow_html=True)

    with st.form("exp"):
        c1, c2, c3 = st.columns(3)
        with c1:
            e_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
        with c2:
            cat = st.text_input("Category", value="General")
        with c3:
            amt = st.number_input("Amount", min_value=0.0, value=0.0)
        desc = st.text_input("Description")
        if st.form_submit_button("💾 Save Expense") and amt > 0:
            run("INSERT INTO expenses (date, category, amount, description) VALUES (?,?,?,?)",
                (to_iso(e_date), title_case(cat), amt, desc))
            st.success("✅ Saved")
            st.rerun()

    st.markdown("### Recent Expenses")
    df = q("SELECT * FROM expenses ORDER BY id DESC LIMIT 50")
    if len(df):
        df["date"] = df["date"].apply(fmt_date)
        df.columns = [c.replace("_", " ").title() for c in df.columns]
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
#               LEDGER
# ============================================================

elif menu == "📒 Ledger":
    st.markdown("<h1 class='big-title'>Customer & Vendor Ledger</h1>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([1, 2, 1.5, 1.5])
    with c1:
        ltype = st.radio("Select", ["Customer", "Vendor"])
    if ltype == "Customer":
        parties = q("SELECT id, name, opening_balance FROM customers ORDER BY name")
        party_type = "customer"
    else:
        parties = q("SELECT id, name, opening_balance FROM vendors ORDER BY name")
        party_type = "vendor"

    if len(parties) == 0:
        st.info(f"No {ltype}s Added Yet")
        st.stop()

    with c2:
        p_name = st.selectbox(f"{ltype}", parties["name"].tolist())
        p_row = parties[parties["name"] == p_name].iloc[0]
        p_id = int(p_row["id"])
    with c3:
        date_from = st.date_input("From Date", value=date.today().replace(day=1), format="DD/MM/YYYY")
    with c4:
        date_to = st.date_input("To Date", value=date.today(), format="DD/MM/YYYY")

    opening = float(p_row["opening_balance"] or 0)
    iso_from = to_iso(date_from)
    iso_to = to_iso(date_to)

    txn = q("""SELECT date, type, amount, description
               FROM transactions
               WHERE party_type = ? AND party_id = ?
                 AND date BETWEEN ? AND ?
               ORDER BY date""", (party_type, p_id, iso_from, iso_to))

    total_debit = 0.0
    total_credit = 0.0
    rows = []
    balance = opening
    for _, r in txn.iterrows():
        amt = float(r["amount"] or 0)
        typ = str(r["type"]).lower()
        is_payment = "payment" in typ
        if party_type == "customer":
            if is_payment:
                balance -= amt; total_credit += amt; dr, cr = 0, amt
            else:
                balance += amt; total_debit += amt; dr, cr = amt, 0
        else:
            if is_payment:
                balance += amt; total_credit += amt; dr, cr = 0, amt
            else:
                balance -= amt; total_debit += amt; dr, cr = amt, 0
        rows.append([
            fmt_date(r["date"]),
            title_case(str(r["type"]).replace("_", " ")),
            f"{dr:.2f}" if dr else "",
            f"{cr:.2f}" if cr else "",
            f"{balance:.2f}",
            str(r["description"] or ""),
        ])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Opening Balance", f"Rs. {opening:,.0f}")
    m2.metric("Total Debit", f"Rs. {total_debit:,.0f}")
    m3.metric("Total Credit", f"Rs. {total_credit:,.0f}")
    m4.metric("Closing Balance", f"Rs. {balance:,.0f}")

    st.markdown("### Transactions")
    if rows:
        st.dataframe(
            pd.DataFrame(rows, columns=["Date", "Type", "Debit", "Credit", "Balance", "Description"]),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No Transactions In This Date Range")

    # ---- PRINT LEDGER (DIRECT) ----
    if st.button("🖨️ Print Ledger"):
        html_str = html_table(
            ["Date", "Type", "Debit", "Credit", "Balance", "Description"],
            rows,
            summary=[
                f"Period: {fmt_date(date_from)} To {fmt_date(date_to)}",
                f"Opening Balance: Rs. {opening:,.2f}",
                f"Total Debit: Rs. {total_debit:,.2f}",
                f"Total Credit: Rs. {total_credit:,.2f}",
                f"Closing Balance: Rs. {balance:,.2f}",
            ],
            title=f"{ltype} Ledger - {title_case(p_name)}",
        )
        direct_print(html_str)
        st.success("✅ Print dialog khul gaya — printer select karein")


# ============================================================
#               REPORTS
# ============================================================

elif menu == "📈 Reports":
    st.markdown("<h1 class='big-title'>Reports</h1>", unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["Sales", "Purchases", "Expenses", "Profit & Loss"])

    with tab1:
        d1 = st.date_input("From", value=date.today().replace(day=1), key="s_from", format="DD/MM/YYYY")
        d2 = st.date_input("To", value=date.today(), key="s_to", format="DD/MM/YYYY")
        df = q("SELECT * FROM sales WHERE date BETWEEN ? AND ? ORDER BY date DESC",
               (to_iso(d1), to_iso(d2)))
        if len(df):
            df["date"] = df["date"].apply(fmt_date)
            df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Sales", f"Rs. {df['Total'].sum():,.0f}")

    with tab2:
        df = q("SELECT * FROM purchases ORDER BY date DESC LIMIT 100")
        if len(df):
            df["date"] = df["date"].apply(fmt_date)
            df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Purchases", f"Rs. {df['Total'].sum():,.0f}")

    with tab3:
        df = q("SELECT * FROM expenses ORDER BY date DESC LIMIT 100")
        if len(df):
            df["date"] = df["date"].apply(fmt_date)
            df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Expenses", f"Rs. {df['Amount'].sum():,.0f}")

    with tab4:
        pl = q("""
            SELECT
                (SELECT COALESCE(SUM(total),0) FROM sales) as s,
                (SELECT COALESCE(SUM(total),0) FROM purchases) as p,
                (SELECT COALESCE(SUM(amount),0) FROM expenses) as e,
                (SELECT COALESCE(SUM(total),0) FROM sale_returns) as r
        """)
        s, p, e, ret = pl.iloc[0]["s"], pl.iloc[0]["p"], pl.iloc[0]["e"], pl.iloc[0]["r"]
        gross = s - p - ret
        net = gross - e
        st.markdown(f"""
        ### 💰 Profit & Loss Summary

        | Item | Amount |
        |------|--------|
        | Sales | Rs. {s:,.0f} |
        | Less: Sale Returns | Rs. -{ret:,.0f} |
        | Less: Purchases | Rs. -{p:,.0f} |
        | **Gross Profit** | **Rs. {gross:,.0f}** |
        | Less: Expenses | Rs. -{e:,.0f} |
        | **Net Profit** | **Rs. {net:,.0f}** |
        """)


# ============================================================
#               PRODUCTS
# ============================================================

elif menu == "🍽️ Products":
    st.markdown("<h1 class='big-title'>Products (Finished Goods)</h1>", unsafe_allow_html=True)

    with st.expander("➕ Add New Product", expanded=False):
        with st.form("add_prod"):
            c1, c2, c3 = st.columns(3)
            with c1:
                n = st.text_input("Name")
                sku = st.text_input("SKU")
            with c2:
                unit = st.selectbox("Unit", ["Pcs", "Kg", "G", "Box", "Packet", "Ton"])
                sp = st.number_input("Sale Price", min_value=0.0, value=0.0)
            with c3:
                cp = st.number_input("Cost Price", min_value=0.0, value=0.0)
                sq = st.number_input("Opening Stock", min_value=0.0, value=0.0)
            if st.form_submit_button("Add Product") and n:
                cur = run("""INSERT INTO products (name, sku, unit, sale_price, cost_price, stock_qty)
                             VALUES (?,?,?,?,?,?)""",
                          (title_case(n), sku, unit, sp, cp, sq))
                pid = cur.lastrowid
                run("""INSERT INTO product_price_history (product_id, sale_price, cost_price, changed_by)
                       VALUES (?,?,?,?)""", (pid, sp, cp, user["username"]))
                st.success("✅ Added")
                st.rerun()

    df = q("SELECT * FROM products ORDER BY name")
    display_df = df.copy()
    if len(display_df):
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("### ✏️ Edit / Delete")
    if len(df):
        p_name = st.selectbox("Select Product", df["name"].tolist(), key="edit_prod")
        row = df[df["name"] == p_name].iloc[0]
        with st.form("edit_prod"):
            c1, c2, c3 = st.columns(3)
            with c1:
                nn = st.text_input("Name", value=row["name"])
                nsku = st.text_input("SKU", value=row["sku"] or "")
            with c2:
                nun = st.text_input("Unit", value=row["unit"] or "Pcs")
                nsp = st.number_input("Sale Price", value=float(row["sale_price"]))
            with c3:
                ncp = st.number_input("Cost Price", value=float(row["cost_price"]))
                nsq = st.number_input("Stock", value=float(row["stock_qty"]))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("""INSERT INTO product_price_history (product_id, sale_price, cost_price, changed_by)
                       VALUES (?,?,?,?)""", (int(row["id"]), nsp, ncp, user["username"]))
                run("""UPDATE products SET name=?, sku=?, unit=?, sale_price=?, cost_price=?, stock_qty=?
                       WHERE id=?""", (title_case(nn), nsku, nun, nsp, ncp, nsq, int(row["id"])))
                st.success("Updated - Old Prices Kept In History")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM products WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

        st.markdown("### 📜 Price History")
        hist = q("""SELECT effective_from, sale_price, cost_price, changed_by
                    FROM product_price_history WHERE product_id = ?
                    ORDER BY effective_from DESC LIMIT 20""", (int(row["id"]),))
        if len(hist):
            hist["effective_from"] = hist["effective_from"].apply(lambda x: fmt_date(str(x)[:10]))
            hist.columns = ["Effective From", "Sale Price", "Cost Price", "Changed By"]
        st.dataframe(hist, use_container_width=True, hide_index=True)


# ============================================================
#               RAW MATERIALS
# ============================================================

elif menu == "🧂 Raw Materials":
    st.markdown("<h1 class='big-title'>Raw Materials</h1>", unsafe_allow_html=True)
    st.caption("Weight Aur Unit Ke Saath - Jaise 1000 Kg, 500 G, 5 Ton. Naya Add Karne Se Purana Nahi Hatega.")

    with st.form("add_rm"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = st.text_input("Name")
        with c2:
            unit_options = ["Kg", "G", "Ton", "Liter", "Ml", "Pcs", "Packet", "Box"]
            unit = st.selectbox("Unit", unit_options)
        with c3:
            rate = st.number_input("Rate (Per Unit)", min_value=0.0, value=0.0)
        with c4:
            stock = st.number_input("Opening Stock / Weight", min_value=0.0, value=0.0,
                                    help="Jaise 1000 likho - Matlab 1000 Kg")
        if st.form_submit_button("Add Raw Material") and n:
            existing = q("SELECT id, stock_qty FROM raw_materials WHERE name = ? AND unit = ?",
                         (title_case(n), unit))
            if len(existing):
                old_stock = float(existing.iloc[0]["stock_qty"] or 0)
                new_stock = old_stock + float(stock)
                rid = int(existing.iloc[0]["id"])
                run("UPDATE raw_materials SET stock_qty = ?, rate = ? WHERE id = ?",
                    (new_stock, rate, rid))
                st.success(f"✅ Existing Stock Updated: {old_stock} + {stock} = {new_stock} {unit}")
            else:
                cur = run("INSERT INTO raw_materials (name, unit, rate, stock_qty) VALUES (?,?,?,?)",
                          (title_case(n), unit, rate, stock))
                rid = cur.lastrowid
                st.success(f"✅ New Added: {title_case(n)} ({stock} {unit})")
            run("""INSERT INTO raw_material_price_history (raw_material_id, rate, changed_by)
                   VALUES (?,?,?)""", (rid, rate, user["username"]))
            st.rerun()

    df = q("SELECT * FROM raw_materials ORDER BY name")
    if len(df):
        df["Weight"] = df.apply(lambda r: f"{r['stock_qty']:g} {r['unit']}", axis=1)
        display_df = df[["id", "name", "unit", "rate", "Weight", "created_at"]].copy()
        display_df.columns = ["ID", "Name", "Unit", "Rate", "Weight", "Created At"]
    else:
        display_df = df
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("### ✏️ Edit / Delete")
    if len(df):
        rname = st.selectbox("Select", df["name"].tolist(), key="edit_rm")
        row = df[df["name"] == rname].iloc[0]
        with st.form("edit_rm"):
            c1, c2, c3 = st.columns(3)
            with c1:
                nn = st.text_input("Name", value=row["name"])
                nun = st.text_input("Unit", value=row["unit"])
            with c2:
                nrate = st.number_input("Rate", value=float(row["rate"]))
                nstock = st.number_input("Weight / Stock", value=float(row["stock_qty"]))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("""INSERT INTO raw_material_price_history (raw_material_id, rate, changed_by)
                       VALUES (?,?,?)""", (int(row["id"]), nrate, user["username"]))
                run("UPDATE raw_materials SET name=?, unit=?, rate=?, stock_qty=? WHERE id=?",
                    (title_case(nn), nun, nrate, nstock, int(row["id"])))
                st.success("Updated - Old Rates Kept In History")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM raw_materials WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

        st.markdown("### 📜 Rate History")
        hist = q("""SELECT effective_from, rate, changed_by
                    FROM raw_material_price_history WHERE raw_material_id = ?
                    ORDER BY effective_from DESC LIMIT 20""", (int(row["id"]),))
        if len(hist):
            hist["effective_from"] = hist["effective_from"].apply(lambda x: fmt_date(str(x)[:10]))
            hist.columns = ["Effective From", "Rate", "Changed By"]
        st.dataframe(hist, use_container_width=True, hide_index=True)


# ============================================================
#               CUSTOMERS
# ============================================================

elif menu == "👥 Customers":
    st.markdown("<h1 class='big-title'>Customers</h1>", unsafe_allow_html=True)

    with st.form("add_cust"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = st.text_input("Name")
        with c2:
            ph = st.text_input("Phone")
        with c3:
            ad = st.text_input("Address")
        with c4:
            ob = st.number_input("Opening Balance", value=0.0)
        if st.form_submit_button("Add Customer") and n:
            run("INSERT INTO customers (name, phone, address, opening_balance) VALUES (?,?,?,?)",
                (title_case(n), ph, ad, ob))
            st.success("✅ Added")
            st.rerun()

    df = q("SELECT * FROM customers ORDER BY name")
    display_df = df.copy()
    if len(display_df):
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if len(df):
        st.markdown("### ✏️ Edit / Delete")
        cname = st.selectbox("Select", df["name"].tolist(), key="edit_cust")
        row = df[df["name"] == cname].iloc[0]
        with st.form("edit_cust"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nn = st.text_input("Name", value=row["name"])
            with c2:
                nph = st.text_input("Phone", value=row["phone"] or "")
            with c3:
                nad = st.text_input("Address", value=row["address"] or "")
            with c4:
                nob = st.number_input("Opening Balance", value=float(row["opening_balance"] or 0))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("UPDATE customers SET name=?, phone=?, address=?, opening_balance=? WHERE id=?",
                    (title_case(nn), nph, nad, nob, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM customers WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()


# ============================================================
#               VENDORS
# ============================================================

elif menu == "🚚 Vendors":
    st.markdown("<h1 class='big-title'>Vendors</h1>", unsafe_allow_html=True)

    with st.form("add_vend"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = st.text_input("Name")
        with c2:
            ph = st.text_input("Phone")
        with c3:
            ad = st.text_input("Address")
        with c4:
            ob = st.number_input("Opening Balance", value=0.0)
        if st.form_submit_button("Add Vendor") and n:
            run("INSERT INTO vendors (name, phone, address, opening_balance) VALUES (?,?,?,?)",
                (title_case(n), ph, ad, ob))
            st.success("✅ Added")
            st.rerun()

    df = q("SELECT * FROM vendors ORDER BY name")
    display_df = df.copy()
    if len(display_df):
        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if len(df):
        st.markdown("### ✏️ Edit / Delete")
        vname = st.selectbox("Select", df["name"].tolist(), key="edit_vend")
        row = df[df["name"] == vname].iloc[0]
        with st.form("edit_vend"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nn = st.text_input("Name", value=row["name"])
            with c2:
                nph = st.text_input("Phone", value=row["phone"] or "")
            with c3:
                nad = st.text_input("Address", value=row["address"] or "")
            with c4:
                nob = st.number_input("Opening Balance", value=float(row["opening_balance"] or 0))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("UPDATE vendors SET name=?, phone=?, address=?, opening_balance=? WHERE id=?",
                    (title_case(nn), nph, nad, nob, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM vendors WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()


# ============================================================
#               MASTER SETUP
# ============================================================

elif menu == "⚙️ Master Setup":
    st.markdown("<h1 class='big-title'>Master Setup</h1>", unsafe_allow_html=True)
    st.info("Yahan Se Apna Password Change Karo, Aur Business Info Dekh Sakte Ho.")

    with st.form("chpw"):
        old = st.text_input("Old Password", type="password")
        new = st.text_input("New Password", type="password")
        if st.form_submit_button("🔐 Change Password"):
            df = q("SELECT * FROM users WHERE id=?", (user["id"],))
            if bcrypt.checkpw(old.encode(), df.iloc[0]["password_hash"].encode()):
                h = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
                run("UPDATE users SET password_hash=? WHERE id=?", (h, user["id"]))
                st.success("✅ Password Changed")
            else:
                st.error("Old Password Incorrect")

    st.markdown("---")
    st.markdown("### 📊 Database Summary")
    counts = q("""
        SELECT
            (SELECT COUNT(*) FROM products) as products,
            (SELECT COUNT(*) FROM customers) as customers,
            (SELECT COUNT(*) FROM vendors) as vendors,
            (SELECT COUNT(*) FROM raw_materials) as raw_materials,
            (SELECT COUNT(*) FROM sales) as sales,
            (SELECT COUNT(*) FROM purchases) as purchases
    """)
    for k, v in counts.iloc[0].items():
        st.write(f"**{k.replace('_',' ').title()}**: {v}")

    st.markdown("---")
    st.markdown("### 🧹 Clear Cache")
    st.caption("Agar App Slow Lage To Yahan Se Cache Clear Karo")
    if st.button("🗑️ Clear Cache Now"):
        q.clear()
        st.cache_data.clear()
        st.success("✅ Cache Cleared — App Fresh Ho Gayi")
        st.rerun()


# ============================================================
#               BACKUP / RESTORE
# ============================================================

elif menu == "💾 Backup / Restore":
    st.markdown("<h1 class='big-title'>Backup & Restore</h1>", unsafe_allow_html=True)

    st.markdown("### ⬇️ Download Backup (CSV)")
    tables = ["products", "customers", "vendors", "raw_materials", "sales",
              "sale_items", "purchases", "purchase_items", "expenses", "transactions",
              "sale_returns", "sale_return_items", "production", "production_materials",
              "product_price_history", "raw_material_price_history"]
    if st.button("📥 Generate Backup"):
        for t in tables:
            try:
                df = q(f"SELECT * FROM {t}")
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    f"⬇️ {t}.csv",
                    data=csv,
                    file_name=f"{t}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key=f"dl_{t}",
                )
            except Exception as e:
                st.warning(f"Skip {t}: {e}")

    st.markdown("---")
    st.markdown("### ☁️ Turso Auto-Backup")
    st.info("""
    Turso Automatically Backs Up Your Database. Aap Turso Dashboard Se Snapshots Le Sakte Ho:
    1. https://turso.tech/app Par Jao
    2. Apna Database Select Karo
    3. "Snapshots" Tab Me Jao
    """)
