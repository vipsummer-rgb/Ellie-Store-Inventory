import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

# ==========================================
# 1. PAGE & CONFIGURATION
# ==========================================
st.set_page_config(page_title="Ellie Store Inventory", page_icon="📦", layout="wide")

# ==========================================
# 2. GOOGLE SHEETS CONNECTION
# ==========================================
@st.cache_resource
def get_gsheet():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open("Inventory DB - TEST")
    
    try:
        inventory_sheet = sh.worksheet("Sheet1")
    except gspread.exceptions.WorksheetNotFound:
        inventory_sheet = sh.sheet1

    try:
        log_sheet = sh.worksheet("Logs")
    except gspread.exceptions.WorksheetNotFound:
        log_sheet = sh.add_worksheet(title="Logs", rows="1000", cols="4")
        log_sheet.append_row(["Timestamp", "User", "Action", "Details"])
        
    return inventory_sheet, log_sheet

sheet, log_sheet = get_gsheet()

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def log_action(user: str, action: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_sheet.append_row([timestamp, user, action, details])

def load_data():
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["id", "sku", "name", "quantity", "price"])
    
    df_loaded = pd.DataFrame(records)
    df_loaded.columns = [str(c).strip().lower() for c in df_loaded.columns]
    
    for col in ["sku", "name"]:
        if col in df_loaded.columns:
            df_loaded[col] = df_loaded[col].astype(str).str.strip().str.upper()
            
    return df_loaded

def get_quantity_col_idx(headers):
    """Finds the 1-based column index for quantity regardless of casing."""
    for idx, header in enumerate(headers, start=1):
        if str(header).strip().lower() in ["quantity", "qty", "stock"]:
            return idx
    return 4  # Default fallback column (D)

df = load_data()

# ==========================================
# 4. USER AUTHENTICATION
# ==========================================
USERS = st.secrets.get("users", {
    "admin": "admin123",
    "staff1": "ellie2026",
    "staff2": "ellie2026"
})

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""

def login():
    st.title("🔒 Ellie Store Login")
    with st.form("login_form"):
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log In")
        
        if submit:
            if username in USERS and USERS[username] == password:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                log_action(username, "LOGIN", f"User '{username}' logged in.")
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

if not st.session_state["authenticated"]:
    login()
    st.stop()

# ==========================================
# 5. NAVIGATION & HEADER
# ==========================================
st.sidebar.title(f"👤 User: {st.session_state['username']}")
if st.sidebar.button("Log Out"):
    current_user = st.session_state["username"]
    log_action(current_user, "LOGOUT", f"User '{current_user}' logged out.")
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.rerun()

st.title("📦 Ellie Store Inventory")
st.caption(f"Logged in as **{st.session_state['username']}** | Tab Connected: **{sheet.title}**")

tab_pos, tab_inventory = st.tabs(["🛒 Orders / POS", "📦 Inventory Management"])

# ==========================================
# 6. TAB 1: ORDERS / POS
# ==========================================
with tab_pos:
    st.subheader("🛒 New Customer Order")

    if "cart" not in st.session_state:
        st.session_state["cart"] = []

    if "clear_pos_flag" not in st.session_state:
        st.session_state["clear_pos_flag"] = False

    if st.session_state["clear_pos_flag"]:
        st.session_state["pos_order_name"] = ""
        st.session_state["pos_item_select"] = None
        st.session_state["pos_qty_input"] = 0
        st.session_state["clear_pos_flag"] = False

    col_catalog, col_cart = st.columns([1, 1.3])

    with col_catalog:
        st.markdown("##### Add Item to Cart")
        order_name = st.text_input("Order Name (Optional)", placeholder="e.g., Customer Name", key="pos_order_name").strip()
        
        in_stock_df = df[df["quantity"] > 0] if not df.empty and "quantity" in df.columns else pd.DataFrame()
        item_options = in_stock_df.apply(lambda r: f"{r['name']} | Stock: {r['quantity']}", axis=1).tolist() if not in_stock_df.empty else []

        selected_item_str = st.selectbox(
            "Product", 
            options=item_options, 
            index=None, 
            placeholder="Select or type product..." if item_options else "No items in stock",
            disabled=len(item_options) == 0,
            key="pos_item_select"
        )

        max_available = 9999
        item_data = None
        if selected_item_str and not in_stock_df.empty:
            selected_idx = item_options.index(selected_item_str)
            item_data = in_stock_df.iloc[selected_idx]
            max_available = int(item_data["quantity"])

        order_qty = st.number_input(
            "Qty", 
            min_value=0, 
            max_value=max_available if selected_item_str else 1, 
            key="pos_qty_input"
        )
        
        can_add = selected_item_str is not None and order_qty > 0

        if st.button("➕ Add to Cart", use_container_width=True, type="secondary", disabled=not can_add):
            if selected_item_str and item_data is not None and order_qty > 0:
                existing_cart_item = next((item for item in st.session_state["cart"] if item["name"].strip().upper() == str(item_data["name"]).strip().upper()), None)
                
                if existing_cart_item:
                    if existing_cart_item["qty"] + order_qty > max_available:
                        st.error(f"Cannot add more. Max stock is {max_available}.")
                    else:
                        existing_cart_item["qty"] += order_qty
                        st.rerun()
                else:
                    st.session_state["cart"].append({
                        "sku": str(item_data["sku"]).upper(),
                        "name": str(item_data["name"]).upper(),
                        "qty": order_qty,
                        "price": float(item_data["price"]),
                        "max_stock": max_available
                    })
                    st.rerun()

    with col_cart:
        st.markdown("##### Current Cart")
        if st.session_state["cart"]:
            c_name, c_qty, c_price, c_subtotal = st.columns([2.5, 1.8, 1.5, 1.5])
            c_name.caption("**Name**")
            c_qty.caption("**Qty**")
            c_price.caption("**Unit Price**")
            c_subtotal.caption("**Subtotal**")
            st.divider()

            grand_total = 0.0
            items_to_remove = []

            for idx, item in enumerate(st.session_state["cart"]):
                subtotal = item["qty"] * item["price"]
                grand_total += subtotal

                row_name, row_qty, row_price, row_subtotal = st.columns([2.5, 1.8, 1.5, 1.5])
                row_name.write(item["name"])
                
                new_qty = row_qty.number_input(label=f"qty_{idx}", min_value=0, max_value=int(item["max_stock"]), value=int(item["qty"]), step=1, label_visibility="collapsed", key=f"cart_qty_{idx}")

                if new_qty != item["qty"]:
                    if new_qty == 0:
                        items_to_remove.append(idx)
                    else:
                        item["qty"] = new_qty
                    st.rerun()

                row_price.write(f"₱{item['price']:.2f}")
                row_subtotal.write(f"**₱{subtotal:,.2f}**")

            if items_to_remove:
                for idx in sorted(items_to_remove, reverse=True):
                    st.session_state["cart"].pop(idx)
                st.rerun()

            st.divider()
            st.markdown(f"### **Total:** ₱{grand_total:,.2f}")

            col_clear, col_checkout = st.columns(2)
            with col_clear:
                if st.button("🗑️ Clear Cart", use_container_width=True):
                    st.session_state["cart"] = []
                    st.rerun()

            with col_checkout:
                if st.button("✅ Complete Order", type="primary", use_container_width=True):
                    headers = sheet.row_values(1)
                    qty_col_idx = get_quantity_col_idx(headers)
                    fresh_df = load_data()

                    for item in st.session_state["cart"]:
                        item_name_upper = str(item["name"]).strip().upper()
                        match = fresh_df[fresh_df["name"].astype(str).str.strip().str.upper() == item_name_upper]
                        
                        if not match.empty:
                            row_idx = match.index[0]
                            current_qty = int(fresh_df.iloc[row_idx]["quantity"])
                            new_qty = current_qty - item["qty"]
                            
                            row_number = row_idx + 2
                            sheet.update_cell(row_number, qty_col_idx, new_qty)
                    
                    # Read order name directly from variable captured before rerun
                    order_ref = f"Order Name: {order_name.upper()} | " if order_name else ""
                    order_summary = ", ".join([f"{i['name']} (x{i['qty']})" for i in st.session_state["cart"]])
                    
                    log_action(
                        st.session_state["username"], 
                        "ORDER COMPLETED", 
                        f"{order_ref}Items: [{order_summary}] | Total: ₱{grand_total:,.2f}"
                    )
                    
                    st.success(f"Order completed! Total: ₱{grand_total:,.2f}")
                    st.session_state["cart"] = []
                    st.session_state["clear_pos_flag"] = True
                    st.rerun()
        else:
            st.info("Cart is empty.")

# ==========================================
# 7. TAB 2: INVENTORY MANAGEMENT
# ==========================================
with tab_inventory:
    col_add, col_remove = st.columns(2)

    if "clear_add_flag" not in st.session_state:
        st.session_state["clear_add_flag"] = False

    def reset_add_inputs():
        st.session_state["clear_add_flag"] = True

    # --- ADD STOCK ---
    with col_add:
        with st.expander("➕ Add Stock Item", expanded=True):
            if st.session_state["clear_add_flag"]:
                st.session_state["add_name_input"] = ""
                st.session_state["add_sku_input"] = ""
                st.session_state["add_name_select"] = None
                st.session_state["add_qty_input"] = 1
                st.session_state["add_price_input"] = 0.0
                st.session_state["chk_is_new"] = False
                st.session_state["clear_add_flag"] = False

            is_new_item = st.checkbox("New Product (Not in list yet)", key="chk_is_new")
            existing_names = sorted(list(set([str(n).strip() for n in df["name"].dropna().tolist() if str(n).strip() != ""]))) if not df.empty and "name" in df.columns else []

            add_name, add_sku, add_price = "", "", 0.0

            if is_new_item or not existing_names:
                add_name = st.text_input("Item Name", key="add_name_input").strip()
                add_sku = st.text_input("SKU Code (Optional)", key="add_sku_input").strip().upper()
                add_price = st.number_input("Price (₱)", min_value=0.0, step=0.5, format="%.2f", key="add_price_input")
            else:
                selected_name = st.selectbox("Search & Select Item Name", options=existing_names, index=None, placeholder="Type or select item...", key="add_name_select")
                if selected_name:
                    add_name = selected_name
                    name_mask = df["name"].astype(str).str.strip().str.upper() == selected_name.upper()
                    if name_mask.any():
                        selected_row = df[name_mask].iloc[0]
                        add_sku = str(selected_row.get("sku", "N/A")).upper()
                        add_price = float(selected_row.get("price", 0.0))
                        st.caption(f"Current Price: ₱{add_price:.2f} | SKU: {add_sku}")

            add_quantity = st.number_input("Quantity to Add", min_value=1, step=1, key="add_qty_input")

            if st.button("Save Stock", key="btn_save_new"):
                if add_name:
                    try:
                        add_name = add_name.strip().upper()
                        sku_val = add_sku.strip().upper() if add_sku else "N/A"

                        headers = sheet.row_values(1)
                        qty_col_idx = get_quantity_col_idx(headers)

                        fresh_df = load_data()
                        
                        match = fresh_df[fresh_df["name"].astype(str).str.strip().str.upper() == add_name] if not fresh_df.empty and "name" in fresh_df.columns else pd.DataFrame()

                        if not match.empty:
                            row_idx = match.index[0]
                            current_qty = int(fresh_df.iloc[row_idx]["quantity"])
                            new_qty = current_qty + add_quantity
                            
                            row_number = row_idx + 2
                            sheet.update_cell(row_number, qty_col_idx, new_qty)

                            log_action(st.session_state["username"], "ADD STOCK", f"Added {add_quantity} to '{add_name}' [SKU: {sku_val}] (New Total: {new_qty})")
                            st.success(f"Successfully updated '{add_name}'! New total: {new_qty}")
                        else:
                            # Append clean 1D list row
                            new_id = len(fresh_df) + 1
                            sheet.append_row([new_id, sku_val, add_name, add_quantity, add_price])
                            log_action(st.session_state["username"], "ADD ITEM", f"Created new item: {add_name}, Qty: {add_quantity}, Price: ₱{add_price}")
                            st.success(f"Added new product '{add_name}' to inventory!")

                        reset_add_inputs()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update Google Sheet: {e}")
                else:
                    st.error("Please enter or select an Item Name.")

    # --- REMOVE STOCK ---
    with col_remove:
        with st.expander("➖ Remove / Deduct Stock", expanded=False):
            if not df.empty and "name" in df.columns:
                item_options = df.apply(lambda r: f"{r['name']} - {r['sku']} (Current: {r['quantity']})", axis=1).tolist()
                selected_item_str = st.selectbox("Select Item to Deduct", options=item_options, index=None, key="remove_select_input")
                deduct_qty = st.number_input("Quantity to Remove", min_value=1, step=1, key="remove_qty_input")
                reason = st.text_input("Reason (Optional)", key="remove_reason_input")

                if st.button("Deduct Stock", key="btn_deduct_stock"):
                    if selected_item_str:
                        # Extract exact product name before the hyphen marker
                        raw_selected_name = selected_item_str.split(" - ")[0].strip().upper()
                        
                        fresh_df = load_data()
                        match = fresh_df[fresh_df["name"].astype(str).str.strip().str.upper() == raw_selected_name]

                        if not match.empty:
                            row_idx = match.index[0]
                            current_qty = int(fresh_df.iloc[row_idx]["quantity"])
                            item_name = str(fresh_df.iloc[row_idx]["name"])

                            if deduct_qty > current_qty:
                                st.error(f"Cannot remove {deduct_qty}. Only {current_qty} in stock!")
                            else:
                                new_qty = current_qty - deduct_qty
                                headers = sheet.row_values(1)
                                qty_col_idx = get_quantity_col_idx(headers)
                                
                                row_number = row_idx + 2
                                sheet.update_cell(row_number, qty_col_idx, new_qty)
                                
                                reason_str = f" | Reason: {reason}" if reason else ""
                                log_action(st.session_state["username"], "REMOVE STOCK", f"Deducted {deduct_qty} from '{item_name}' (Remaining: {new_qty}){reason_str}")
                                st.success(f"Deducted {deduct_qty} from '{item_name}'. New total: {new_qty}")
                                st.rerun()
                        else:
                            st.error("Item not found in current inventory database.")
            else:
                st.info("No items in inventory to remove.")

    # --- STOCK LEVELS TABLE ---
    st.subheader("📋 Current Stock Levels")
    df_live = load_data()
    if not df_live.empty:
        st.dataframe(df_live, use_container_width=True, hide_index=True)
    else:
        st.info("No items found in your inventory sheet.")

    # --- AUDIT LOGS ---
    if st.session_state["username"] == "admin":
        st.divider()
        with st.expander("📜 View Audit Log", expanded=True):
            logs = log_sheet.get_all_records()
            if logs:
                st.dataframe(pd.DataFrame(logs).sort_values(by="Timestamp", ascending=False), use_container_width=True, hide_index=True)
