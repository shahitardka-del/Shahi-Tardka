import streamlit as st
import libsql
import pandas as pd
import bcrypt
import plotly.express as px
from datetime import datetime, date
from fpdf import FPDF
import io
import base64

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Shahi Tardka - Business Manager",
    page_icon="🌶️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- CUSTOM CSS (Creative Theme) ----------------
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #fef2f2 0%, #fff7ed 50%, #fffbeb 100%);
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #b91c1c 0%, #7f1d1d 60%, #78350f 100%);
    }
    section[data-testid="stSidebar"] * { color: #fff !important; }
    section[data-testid="stSidebar"] .stRadio label { color: #fff !important; }
    h1, h2, h3 { color: #7f1d1d !important; font-weight: 800 !important; }
    .metric-card {
        background: #fff;
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(185,28,28,0.08);
        border-left: 5px solid #dc2626;
    }
    .stButton>button {
        background: linear-gradient(90deg, #dc2626, #b45309) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 8px 20px !important;
    }
    .stButton>button:hover { opacity: 0.9; }
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

# ---------------- DB CONNECTION ----------------
@st.cache_resource
def get_db():
    url = st.secrets["TURSO_URL"]
    token = st.secrets["TURSO_TOKEN"]
    return libsql.connect(url, auth_token=token)

def run(sql, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args)
    conn.commit()
    return cur

def q(sql, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description] if cur.description else []
    return pd.DataFrame(cur.fetchall(), columns=cols)

# ---------------- INIT DB ----------------
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
        name TEXT NOT NULL, unit TEXT DEFAULT 'kg',
        rate REAL DEFAULT 0, stock_qty REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, sku TEXT, unit TEXT DEFAULT 'pcs',
        sale_price REAL DEFAULT 0, cost_price REAL DEFAULT 0,
        stock_qty REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        qty REAL NOT NULL, rate REAL NOT NULL, amount REAL NOT NULL
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
        qty REAL NOT NULL, rate REAL NOT NULL, amount REAL NOT NULL
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
        qty REAL NOT NULL, rate REAL NOT NULL, amount REAL NOT NULL
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
        qty_used REAL NOT NULL, rate REAL NOT NULL, amount REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL, description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    for stmt in schema.split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)
    # default admin
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", pw))
    conn.commit()

try:
    init_db()
except Exception as e:
    st.error(f"DB init error: {e}")

# ---------------- SEED PRODUCTS (once) ----------------
def seed_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        items = [
            ("Chili Powder 250 g", 250, 0, 250),
            ("Chili Powder 100 g", 100, 0, 100),
            ("Chili Flakes 250 g", 250, 0, 250),
            ("Chili Flakes 100 g", 100, 0, 100),
            ("Turmeric Powder 250 g", 250, 0, 250),
            ("Turmeric Powder 100 g", 100, 0, 100),
            ("Chili 20 Rs.", 20, 0, 20),
            ("Chili 10 Rs.", 10, 0, 10),
            ("Turmeric 20 Rs.", 20, 0, 20),
            ("Turmeric 10 Rs.", 10, 0, 10),
            ("Whole Coriander", 1, 0, 0),
            ("Other Spices", 1, 0, 0),
        ]
        for name, price, cost, stock in items:
            cur.execute(
                "INSERT INTO products (name, sale_price, cost_price, stock_qty, unit) VALUES (?,?,?,?,?)",
                (name, price, cost, stock, "pcs"),
            )
        conn.commit()
seed_products()

# ---------------- SESSION ----------------
if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- LOGIN ----------------
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

# ---------------- SIDEBAR NAV ----------------
st.sidebar.markdown("<h2 style='text-align:center'>🌶️ Shahi Tardka</h2>", unsafe_allow_html=True)
st.sidebar.markdown(f"<p style='text-align:center;font-size:0.85rem'>👤 {user['username']}</p>", unsafe_allow_html=True)
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "📊 Dashboard",
        "🛒 Sale Entry",
        "🛍️ Purchase Entry",
        "↩️ Sale Return",
        "💰 Cash / Bank",
        "📦 Stock Report",
        "🏭 Production",
        "🧾 Expenses",
        "📒 Ledger",
        "📈 Reports",
        "🍽️ Products",
        "🧂 Raw Materials",
        "👥 Customers",
        "🚚 Vendors",
        "⚙️ Master Setup",
        "💾 Backup / Restore",
    ],
    label_visibility="collapsed",
)

if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.user = None
    st.rerun()

# ============================================================
#                       PAGES
# ============================================================

# ---------- DASHBOARD ----------
if menu == "📊 Dashboard":
    st.markdown("<h1 class='big-title'>Dashboard</h1>", unsafe_allow_html=True)
    st.caption("Real-time overview of your business")

    s = q("SELECT COALESCE(SUM(total),0) t FROM sales").iloc[0]["t"]
    p = q("SELECT COALESCE(SUM(total),0) t FROM purchases").iloc[0]["t"]
    e = q("SELECT COALESCE(SUM(amount),0) t FROM expenses").iloc[0]["t"]
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
            fig = px.area(d, x="date", y="total", title="Last 14 Days Sales",
                          color_discrete_sequence=["#dc2626"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sales yet")

    with col2:
        m = q("""SELECT substr(date,1,7) as month, SUM(total) as total FROM sales
                 GROUP BY month ORDER BY month DESC LIMIT 6""")
        if len(m):
            fig = px.bar(m.iloc[::-1], x="month", y="total", title="Monthly Sales",
                         color_discrete_sequence=["#b45309"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sales yet")

    st.markdown("### ⚠️ Low Stock Alerts")
    low = q("SELECT name, stock_qty FROM products WHERE stock_qty < 10 ORDER BY stock_qty LIMIT 8")
    if len(low):
        st.dataframe(low, use_container_width=True, hide_index=True)
    else:
        st.success("All products sufficiently stocked ✅")

# ---------- SALE ENTRY ----------
elif menu == "🛒 Sale Entry":
    st.markdown("<h1 class='big-title'>Sale Entry</h1>", unsafe_allow_html=True)

    customers = q("SELECT id, name FROM customers ORDER BY name")
    products = q("SELECT id, name, sale_price, stock_qty FROM products ORDER BY name")

    if len(customers) == 0 or len(products) == 0:
        st.warning("Pehle Customers aur Products add karo")
        st.stop()

    if "cart" not in st.session_state:
        st.session_state.cart = []

    col1, col2, col3 = st.columns(3)
    with col1:
        cust = st.selectbox("Customer", customers["name"].tolist())
        cust_id = int(customers[customers["name"] == cust].iloc[0]["id"])
    with col2:
        inv_date = st.date_input("Date", value=date.today())
    with col3:
        inv_no = st.text_input("Invoice #", value=f"INV-{datetime.now().strftime('%y%m%d%H%M%S')}")

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
        st.write("")
        st.write("")
        if st.button("➕ Add"):
            st.session_state.cart.append({
                "product_id": int(p_row["id"]),
                "name": prod, "qty": qty, "rate": rate, "amount": qty * rate,
            })
            st.rerun()

    if st.session_state.cart:
        df_cart = pd.DataFrame(st.session_state.cart)
        st.dataframe(df_cart, use_container_width=True, hide_index=True)
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
                (inv_no, cust_id, str(inv_date), total, discount, paid),
            )
            sale_id = cur.lastrowid
            for it in st.session_state.cart:
                run("INSERT INTO sale_items (sale_id, product_id, qty, rate, amount) VALUES (?,?,?,?,?)",
                    (sale_id, it["product_id"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?",
                    (it["qty"], it["product_id"]))
            if paid > 0:
                run("""INSERT INTO transactions (date, type, party_type, party_id, amount, description)
                       VALUES (?,?,?,?,?,?)""",
                    (str(inv_date), "cash_receipt", "customer", cust_id, paid, f"Sale {inv_no}"))
            st.success(f"✅ Saved: {inv_no}")
            st.session_state.cart = []
            st.rerun()
        if colB.button("🗑️ Clear Cart", use_container_width=True):
            st.session_state.cart = []
            st.rerun()
        if colC.button("🖨️ Print Invoice", use_container_width=True):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_text_color(220, 38, 38)
            pdf.cell(0, 10, "SHAHI TARDKA", ln=True, align="C")
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(100)
            pdf.cell(0, 6, "Premium Spices & Foods", ln=True, align="C")
            pdf.ln(5)
            pdf.set_text_color(0)
            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 6, f"Invoice: {inv_no}", ln=True)
            pdf.cell(0, 6, f"Date: {inv_date}", ln=True)
            pdf.cell(0, 6, f"Customer: {cust}", ln=True)
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(220, 38, 38)
            pdf.set_text_color(255)
            for w, h in [(15, "#"), (70, "Item"), (25, "Qty"), (30, "Rate"), (35, "Amount")]:
                pdf.cell(w, 8, h, 1, 0, "C", True)
            pdf.ln()
            pdf.set_text_color(0)
            pdf.set_font("Helvetica", "", 10)
            for i, it in enumerate(st.session_state.cart, 1):
                pdf.cell(15, 7, str(i), 1)
                pdf.cell(70, 7, it["name"][:35], 1)
                pdf.cell(25, 7, str(it["qty"]), 1, 0, "R")
                pdf.cell(30, 7, f"{it['rate']:.2f}", 1, 0, "R")
                pdf.cell(35, 7, f"{it['amount']:.2f}", 1, 0, "R")
                pdf.ln()
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(140, 7, "Subtotal:", 0, 0, "R")
            pdf.cell(35, 7, f"{subtotal:.2f}", 0, 1, "R")
            pdf.cell(140, 7, "Discount:", 0, 0, "R")
            pdf.cell(35, 7, f"{discount:.2f}", 0, 1, "R")
            pdf.set_text_color(220, 38, 38)
            pdf.cell(140, 8, "TOTAL:", 0, 0, "R")
            pdf.cell(35, 8, f"{total:.2f}", 0, 1, "R")
            pdf.set_text_color(0)
            pdf.cell(140, 7, "Paid:", 0, 0, "R")
            pdf.cell(35, 7, f"{paid:.2f}", 0, 1, "R")
            pdf.cell(140, 7, "Balance:", 0, 0, "R")
            pdf.cell(35, 7, f"{(total-paid):.2f}", 0, 1, "R")

            pdf_bytes = bytes(pdf.output())
            b64 = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/pdf;base64,{b64}" download="{inv_no}.pdf" target="_blank">📄 Download/Print Invoice PDF</a>'
            st.markdown(href, unsafe_allow_html=True)

# ---------- PURCHASE ENTRY ----------
elif menu == "🛍️ Purchase Entry":
    st.markdown("<h1 class='big-title'>Purchase Entry</h1>", unsafe_allow_html=True)
    vendors = q("SELECT id, name FROM vendors ORDER BY name")
    raws = q("SELECT id, name, rate FROM raw_materials ORDER BY name")

    if len(vendors) == 0 or len(raws) == 0:
        st.warning("Pehle Vendors aur Raw Materials add karo")
        st.stop()

    if "p_cart" not in st.session_state:
        st.session_state.p_cart = []

    c1, c2, c3 = st.columns(3)
    with c1:
        v = st.selectbox("Vendor", vendors["name"].tolist())
        v_id = int(vendors[vendors["name"] == v].iloc[0]["id"])
    with c2:
        p_date = st.date_input("Date", value=date.today(), key="p_date")
    with c3:
        bill_no = st.text_input("Bill #", value=f"BILL-{datetime.now().strftime('%y%m%d%H%M%S')}")

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
                "raw_material_id": int(r_row["id"]),
                "name": rname, "qty": pqty, "rate": prate, "amount": pqty * prate,
            })
            st.rerun()

    if st.session_state.p_cart:
        st.dataframe(pd.DataFrame(st.session_state.p_cart), use_container_width=True, hide_index=True)
        p_total = sum(x["amount"] for x in st.session_state.p_cart)
        st.metric("Total", f"Rs. {p_total:,.0f}")
        paid_p = st.number_input("Paid", min_value=0.0, value=float(p_total), key="pur_paid")

        cA, cB = st.columns(2)
        if cA.button("💾 Save Purchase", use_container_width=True):
            cur = run(
                "INSERT INTO purchases (bill_no, vendor_id, date, total, paid) VALUES (?,?,?,?,?)",
                (bill_no, v_id, str(p_date), p_total, paid_p),
            )
            pid = cur.lastrowid
            for it in st.session_state.p_cart:
                run("INSERT INTO purchase_items (purchase_id, raw_material_id, qty, rate, amount) VALUES (?,?,?,?,?)",
                    (pid, it["raw_material_id"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE raw_materials SET stock_qty = stock_qty + ?, rate = ? WHERE id = ?",
                    (it["qty"], it["rate"], it["raw_material_id"]))
            if paid_p > 0:
                run("""INSERT INTO transactions (date, type, party_type, party_id, amount, description)
                       VALUES (?,?,?,?,?,?)""",
                    (str(p_date), "cash_payment", "vendor", v_id, paid_p, f"Purchase {bill_no}"))
            st.success(f"✅ Saved: {bill_no}")
            st.session_state.p_cart = []
            st.rerun()
        if cB.button("🗑️ Clear", use_container_width=True):
            st.session_state.p_cart = []
            st.rerun()

# ---------- SALE RETURN ----------
elif menu == "↩️ Sale Return":
    st.markdown("<h1 class='big-title'>Sale Return</h1>", unsafe_allow_html=True)
    customers = q("SELECT id, name FROM customers ORDER BY name")
    products = q("SELECT id, name, sale_price FROM products ORDER BY name")

    if len(customers) == 0 or len(products) == 0:
        st.warning("Pehle Customers aur Products add karo")
        st.stop()

    if "r_cart" not in st.session_state:
        st.session_state.r_cart = []

    c1, c2, c3 = st.columns(3)
    with c1:
        rc = st.selectbox("Customer", customers["name"].tolist())
        rc_id = int(customers[customers["name"] == rc].iloc[0]["id"])
    with c2:
        r_date = st.date_input("Date", value=date.today(), key="r_date")
    with c3:
        r_no = st.text_input("Return #", value=f"RET-{datetime.now().strftime('%y%m%d%H%M%S')}")

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
                "product_id": int(rp_row["id"]),
                "name": rp, "qty": rq, "rate": rr, "amount": rq * rr,
            })
            st.rerun()

    if st.session_state.r_cart:
        st.dataframe(pd.DataFrame(st.session_state.r_cart), use_container_width=True, hide_index=True)
        r_total = sum(x["amount"] for x in st.session_state.r_cart)
        st.metric("Total Return", f"Rs. {r_total:,.0f}")

        if st.button("💾 Save Return", use_container_width=True):
            cur = run(
                "INSERT INTO sale_returns (return_no, customer_id, date, total) VALUES (?,?,?,?)",
                (r_no, rc_id, str(r_date), r_total),
            )
            rid = cur.lastrowid
            for it in st.session_state.r_cart:
                run("INSERT INTO sale_return_items (return_id, product_id, qty, rate, amount) VALUES (?,?,?,?,?)",
                    (rid, it["product_id"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                    (it["qty"], it["product_id"]))
            st.success(f"✅ Return saved: {r_no}")
            st.session_state.r_cart = []
            st.rerun()

# ---------- CASH / BANK ----------
elif menu == "💰 Cash / Bank":
    st.markdown("<h1 class='big-title'>Cash / Bank Transactions</h1>", unsafe_allow_html=True)

    with st.form("txn"):
        c1, c2 = st.columns(2)
        with c1:
            t_date = st.date_input("Date", value=date.today())
            t_type = st.selectbox("Type", ["cash_receipt", "cash_payment", "bank_receipt", "bank_payment"])
        with c2:
            p_type = st.selectbox("Party Type", ["customer", "vendor"])
            if p_type == "customer":
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
                (str(t_date), t_type, p_type, p_id, amount, desc))
            st.success("✅ Saved")
            st.rerun()

    st.markdown("### Recent Transactions")
    df = q("""SELECT date, type, party_type, party_id, amount, description
              FROM transactions ORDER BY id DESC LIMIT 50""")
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- STOCK ----------
elif menu == "📦 Stock Report":
    st.markdown("<h1 class='big-title'>Stock Report</h1>", unsafe_allow_html=True)

    t1, t2 = st.tabs(["📦 Finished Goods", "🧂 Raw Materials"])

    with t1:
        df = q("SELECT id, name, sku, unit, sale_price, cost_price, stock_qty FROM products ORDER BY name")
        st.dataframe(df, use_container_width=True, hide_index=True)
        total_val = (df["stock_qty"] * df["cost_price"]).sum()
        st.metric("Total Stock Value (at cost)", f"Rs. {total_val:,.0f}")

    with t2:
        df2 = q("SELECT id, name, unit, rate, stock_qty FROM raw_materials ORDER BY name")
        st.dataframe(df2, use_container_width=True, hide_index=True)
        if len(df2):
            total_val2 = (df2["stock_qty"] * df2["rate"]).sum()
            st.metric("Total Raw Material Value", f"Rs. {total_val2:,.0f}")

# ---------- PRODUCTION ----------
elif menu == "🏭 Production":
    st.markdown("<h1 class='big-title'>Production (with Wastage)</h1>", unsafe_allow_html=True)
    products = q("SELECT id, name FROM products ORDER BY name")
    raws = q("SELECT id, name, rate FROM raw_materials ORDER BY name")

    if len(products) == 0:
        st.warning("Pehle Products add karo")
        st.stop()

    if "prod_mats" not in st.session_state:
        st.session_state.prod_mats = []

    c1, c2, c3 = st.columns(3)
    with c1:
        pr_date = st.date_input("Date", value=date.today(), key="pr_date")
    with c2:
        pr_prod = st.selectbox("Product Produced", products["name"].tolist())
        pr_pid = int(products[products["name"] == pr_prod].iloc[0]["id"])
    with c3:
        qty_prod = st.number_input("Qty Produced", min_value=0.01, value=1.0)

    wastage = st.number_input("Wastage (in same unit)", min_value=0.0, value=0.0)
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
                "raw_material_id": int(rm_row["id"]),
                "name": rm, "qty": rm_qty, "rate": rm_rate, "amount": rm_qty * rm_rate,
            })
            st.rerun()

    if st.session_state.prod_mats:
        st.dataframe(pd.DataFrame(st.session_state.prod_mats), use_container_width=True, hide_index=True)
        total_cost = sum(x["amount"] for x in st.session_state.prod_mats)
        st.metric("Total Production Cost", f"Rs. {total_cost:,.0f}")

        if st.button("💾 Save Production", use_container_width=True):
            cur = run(
                "INSERT INTO production (date, product_id, qty_produced, wastage, notes) VALUES (?,?,?,?,?)",
                (str(pr_date), pr_pid, qty_prod, wastage, notes),
            )
            prod_id = cur.lastrowid
            for it in st.session_state.prod_mats:
                run("INSERT INTO production_materials (production_id, raw_material_id, qty_used, rate, amount) VALUES (?,?,?,?,?)",
                    (prod_id, it["raw_material_id"], it["qty"], it["rate"], it["amount"]))
                run("UPDATE raw_materials SET stock_qty = stock_qty - ? WHERE id = ?",
                    (it["qty"], it["raw_material_id"]))
            # Add produced qty to product stock, update cost price
            run("UPDATE products SET stock_qty = stock_qty + ?, cost_price = ? WHERE id = ?",
                (qty_prod, total_cost / qty_prod if qty_prod else 0, pr_pid))
            st.success("✅ Production saved")
            st.session_state.prod_mats = []
            st.rerun()

    st.markdown("### Production History")
    hist = q("""SELECT p.id, p.date, pr.name as product, p.qty_produced, p.wastage, p.notes
                FROM production p LEFT JOIN products pr ON p.product_id = pr.id
                ORDER BY p.id DESC LIMIT 30""")
    st.dataframe(hist, use_container_width=True, hide_index=True)

# ---------- EXPENSES ----------
elif menu == "🧾 Expenses":
    st.markdown("<h1 class='big-title'>Expenses</h1>", unsafe_allow_html=True)

    with st.form("exp"):
        c1, c2, c3 = st.columns(3)
        with c1:
            e_date = st.date_input("Date", value=date.today())
        with c2:
            cat = st.text_input("Category", value="General")
        with c3:
            amt = st.number_input("Amount", min_value=0.0, value=0.0)
        desc = st.text_input("Description")
        if st.form_submit_button("💾 Save Expense") and amt > 0:
            run("INSERT INTO expenses (date, category, amount, description) VALUES (?,?,?,?)",
                (str(e_date), cat, amt, desc))
            st.success("✅ Saved")
            st.rerun()

    st.markdown("### Recent Expenses")
    df = q("SELECT * FROM expenses ORDER BY id DESC LIMIT 50")
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- LEDGER ----------
elif menu == "📒 Ledger":
    st.markdown("<h1 class='big-title'>Customer & Vendor Ledger</h1>", unsafe_allow_html=True)
    ltype = st.radio("Select", ["Customer", "Vendor"], horizontal=True)
    if ltype == "Customer":
        parties = q("SELECT id, name FROM customers ORDER BY name")
        table_sales, field, party_type = "sales", "customer_id", "customer"
    else:
        parties = q("SELECT id, name FROM vendors ORDER BY name")
        table_sales, field, party_type = "purchases", "vendor_id", "vendor"

    if len(parties) == 0:
        st.info(f"No {ltype}s added yet")
        st.stop()

    p_name = st.selectbox(f"{ltype}", parties["name"].tolist())
    p_id = int(parties[parties["name"] == p_name].iloc[0]["id"])
    opening = float(parties[parties["name"] == p_name].iloc[0].get("opening_balance", 0) or 0)

    total_debit = q(f"SELECT COALESCE(SUM(total),0) t FROM {table_sales} WHERE {field} = ?",
                    (p_id,)).iloc[0]["t"]
    total_paid = q("""SELECT COALESCE(SUM(amount),0) t FROM transactions
                      WHERE party_type = ? AND party_id = ?""", (party_type, p_id)).iloc[0]["t"]
    balance = opening + total_debit - total_paid

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Opening", f"Rs. {opening:,.0f}")
    c2.metric("Total Business", f"Rs. {total_debit:,.0f}")
    c3.metric("Total Paid", f"Rs. {total_paid:,.0f}")
    c4.metric("Balance", f"Rs. {balance:,.0f}")

    st.markdown("### Transactions")
    df = q("""SELECT date, type, amount, description FROM transactions
              WHERE party_type = ? AND party_id = ?
              ORDER BY date DESC""", (party_type, p_id))
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- REPORTS ----------
elif menu == "📈 Reports":
    st.markdown("<h1 class='big-title'>Reports</h1>", unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["Sales", "Purchases", "Expenses", "Profit & Loss"])

    with tab1:
        d1 = st.date_input("From", value=date.today().replace(day=1), key="s_from")
        d2 = st.date_input("To", value=date.today(), key="s_to")
        df = q("SELECT * FROM sales WHERE date BETWEEN ? AND ? ORDER BY date DESC",
               (str(d1), str(d2)))
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Sales", f"Rs. {df['total'].sum():,.0f}")

    with tab2:
        df = q("SELECT * FROM purchases ORDER BY date DESC LIMIT 100")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Purchases", f"Rs. {df['total'].sum():,.0f}")

    with tab3:
        df = q("SELECT * FROM expenses ORDER BY date DESC LIMIT 100")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if len(df):
            st.metric("Total Expenses", f"Rs. {df['amount'].sum():,.0f}")

    with tab4:
        s = q("SELECT COALESCE(SUM(total),0) t FROM sales").iloc[0]["t"]
        p = q("SELECT COALESCE(SUM(total),0) t FROM purchases").iloc[0]["t"]
        e = q("SELECT COALESCE(SUM(amount),0) t FROM expenses").iloc[0]["t"]
        ret = q("SELECT COALESCE(SUM(total),0) t FROM sale_returns").iloc[0]["t"]
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

# ---------- PRODUCTS ----------
elif menu == "🍽️ Products":
    st.markdown("<h1 class='big-title'>Products (Finished Goods)</h1>", unsafe_allow_html=True)

    with st.expander("➕ Add New Product", expanded=False):
        with st.form("add_prod"):
            c1, c2, c3 = st.columns(3)
            with c1:
                n = st.text_input("Name")
                sku = st.text_input("SKU")
            with c2:
                unit = st.selectbox("Unit", ["pcs", "kg", "g", "box", "packet"])
                sp = st.number_input("Sale Price", min_value=0.0, value=0.0)
            with c3:
                cp = st.number_input("Cost Price", min_value=0.0, value=0.0)
                sq = st.number_input("Opening Stock", min_value=0.0, value=0.0)
            if st.form_submit_button("Add Product") and n:
                run("INSERT INTO products (name, sku, unit, sale_price, cost_price, stock_qty) VALUES (?,?,?,?,?,?)",
                    (n, sku, unit, sp, cp, sq))
                st.success("✅ Added")
                st.rerun()

    df = q("SELECT * FROM products ORDER BY name")
    st.dataframe(df, use_container_width=True, hide_index=True)

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
                nun = st.text_input("Unit", value=row["unit"] or "pcs")
                nsp = st.number_input("Sale Price", value=float(row["sale_price"]))
            with c3:
                ncp = st.number_input("Cost Price", value=float(row["cost_price"]))
                nsq = st.number_input("Stock", value=float(row["stock_qty"]))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("""UPDATE products SET name=?, sku=?, unit=?, sale_price=?, cost_price=?, stock_qty=?
                       WHERE id=?""", (nn, nsku, nun, nsp, ncp, nsq, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM products WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

# ---------- RAW MATERIALS ----------
elif menu == "🧂 Raw Materials":
    st.markdown("<h1 class='big-title'>Raw Materials</h1>", unsafe_allow_html=True)

    with st.form("add_rm"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            n = st.text_input("Name")
        with c2:
            unit = st.selectbox("Unit", ["kg", "g", "liter", "pcs"])
        with c3:
            rate = st.number_input("Rate", min_value=0.0, value=0.0)
        with c4:
            stock = st.number_input("Opening Stock", min_value=0.0, value=0.0)
        if st.form_submit_button("Add Raw Material") and n:
            run("INSERT INTO raw_materials (name, unit, rate, stock_qty) VALUES (?,?,?,?)",
                (n, unit, rate, stock))
            st.success("✅ Added")
            st.rerun()

    df = q("SELECT * FROM raw_materials ORDER BY name")
    st.dataframe(df, use_container_width=True, hide_index=True)

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
                nstock = st.number_input("Stock", value=float(row["stock_qty"]))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("UPDATE raw_materials SET name=?, unit=?, rate=?, stock_qty=? WHERE id=?",
                    (nn, nun, nrate, nstock, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM raw_materials WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

# ---------- CUSTOMERS ----------
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
                (n, ph, ad, ob))
            st.success("✅ Added")
            st.rerun()

    df = q("SELECT * FROM customers ORDER BY name")
    st.dataframe(df, use_container_width=True, hide_index=True)

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
                nob = st.number_input("Opening Bal", value=float(row["opening_balance"] or 0))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("UPDATE customers SET name=?, phone=?, address=?, opening_balance=? WHERE id=?",
                    (nn, nph, nad, nob, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM customers WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

# ---------- VENDORS ----------
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
                (n, ph, ad, ob))
            st.success("✅ Added")
            st.rerun()

    df = q("SELECT * FROM vendors ORDER BY name")
    st.dataframe(df, use_container_width=True, hide_index=True)

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
                nob = st.number_input("Opening Bal", value=float(row["opening_balance"] or 0))
            cc1, cc2 = st.columns(2)
            if cc1.form_submit_button("💾 Update"):
                run("UPDATE vendors SET name=?, phone=?, address=?, opening_balance=? WHERE id=?",
                    (nn, nph, nad, nob, int(row["id"])))
                st.success("Updated")
                st.rerun()
            if cc2.form_submit_button("🗑️ Delete"):
                run("DELETE FROM vendors WHERE id=?", (int(row["id"]),))
                st.success("Deleted")
                st.rerun()

# ---------- MASTER SETUP ----------
elif menu == "⚙️ Master Setup":
    st.markdown("<h1 class='big-title'>Master Setup</h1>", unsafe_allow_html=True)
    st.info("Yahan se apna password change karo, aur business info dekh sakte ho.")

    with st.form("chpw"):
        old = st.text_input("Old Password", type="password")
        new = st.text_input("New Password", type="password")
        if st.form_submit_button("🔐 Change Password"):
            df = q("SELECT * FROM users WHERE id=?", (user["id"],))
            if bcrypt.checkpw(old.encode(), df.iloc[0]["password_hash"].encode()):
                h = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
                run("UPDATE users SET password_hash=? WHERE id=?", (h, user["id"]))
                st.success("✅ Password changed")
            else:
                st.error("Old password incorrect")

    st.markdown("---")
    st.markdown("### 📊 Database Summary")
    counts = {
        "Products": q("SELECT COUNT(*) c FROM products").iloc[0]["c"],
        "Customers": q("SELECT COUNT(*) c FROM customers").iloc[0]["c"],
        "Vendors": q("SELECT COUNT(*) c FROM vendors").iloc[0]["c"],
        "Raw Materials": q("SELECT COUNT(*) c FROM raw_materials").iloc[0]["c"],
        "Sales": q("SELECT COUNT(*) c FROM sales").iloc[0]["c"],
        "Purchases": q("SELECT COUNT(*) c FROM purchases").iloc[0]["c"],
    }
    for k, v in counts.items():
        st.write(f"**{k}**: {v}")

# ---------- BACKUP ----------
elif menu == "💾 Backup / Restore":
    st.markdown("<h1 class='big-title'>Backup & Restore</h1>", unsafe_allow_html=True)

    st.markdown("### ⬇️ Download Backup (CSV)")
    tables = ["products", "customers", "vendors", "raw_materials", "sales",
              "sale_items", "purchases", "purchase_items", "expenses", "transactions",
              "sale_returns", "sale_return_items", "production", "production_materials"]
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
    Turso automatically backs up your database. Aap Turso dashboard se snapshots le sakte ho:
    1. https://turso.tech/app par jao
    2. Apna database select karo
    3. "Snapshots" tab me jao
    """)
