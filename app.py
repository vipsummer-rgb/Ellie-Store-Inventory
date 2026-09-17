import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import requests

# Page Configuration
st.set_page_config(page_title="Ellie Store Inventory", page_icon="📦", layout="wide")

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open("Inventory DB - TEST")
    
    # Ensure audit log worksheet exists
    try:
        log_sheet = sh.worksheet("Logs")
    except gspread.exceptions.WorksheetNotFound:
        log_sheet = sh.add_worksheet(title="Logs", rows="1000", cols="4")
        log_sheet.append_row(["Timestamp", "User", "Action", "Details"])
        
    return sh.sheet1, log_sheet

sheet, log_sheet = get_gsheet()

# --- HELPER: UPLOAD IMAGE TO FREE HOSTING (IMGUR) ---
def upload_image_to_cloud(image_file):
    """Uploads an image file object to Imgur and returns the direct image URL."""
    try:
        headers = {"Authorization": "Client-ID 1c8091f8ed1a1ee"}  # Public client ID for quick upload
        payload = {"image": image_file.getvalue()}
        response = requests.post("https://api.imgur.com/3/upload", headers=headers, data=payload)
        res_data = response.json()
        if res_data.get("success"):
            return res_data["data"]["link"]
        else:
            st.error(f"Image upload failed: {res_data.get('data', {}).get('error', 'Unknown error')}")
            return ""
    except Exception as e:
        st.error(f"Error uploading image: {e}")
        return ""

# --- AUDIT LOG FUNCTION ---
def log_action(user: str, action: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_sheet.append_row([timestamp, user, action, details])

# --- USER AUTHENTICATION ---
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

# --- DATA LOADING ---
def load_data():
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["id", "sku", "name", "quantity", "price", "photo_url"])
    
    df_loaded = pd.DataFrame(records)
    # Ensure photo_url column exists in dataframe
    if "photo_url" not in df_loaded.columns:
        df_loaded["photo_url"] = ""
    return df_loaded

df = load_data()

# --- HEADER & NAVIGATION ---
st.sidebar.title(f"👤 User: {st.session_state['username']}")
if st.sidebar.button("Log Out"):
    current_user = st.session_state["username"]
    log_action(current_user, "LOGOUT", f"User '{current_user}' logged out.")
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.rerun()

st.title("📦 Ellie Store Inventory")
st.caption(f"Logged in as **{st.session_state['username']}** | Connected to Google Sheets")

tab_pos, tab_inventory = st.tabs(["🛒 Orders / POS", "📦 Inventory Management"])

# ==========================================
# TAB 1: ORDERS / POS
# ==========================================
with tab_pos:
    st.subheader("🛒 New Customer Order")

    if "cart" not in st.session_state:
        st.session_state["cart"] = []

    col_catalog, col_cart = st.columns([1, 1.3])

    # --- LEFT COLUMN: ALWAYS-VISIBLE PRODUCT SELECTION ---
    with col_catalog:
        st.markdown("##### Add Item to Cart")
        
        # 1. Order Name
        order_name = st.text_input("Order Name (Optional)", placeholder="e.g., Name", key="pos_order_name").strip()
        
        # Build dropdown options (Product name + Stock level only)
        in_stock_df = df[df["quantity"] > 0] if not df.empty else pd.DataFrame()
        
        if not in_stock_df.empty:
            item_options = in_stock_df.apply(
                lambda r: f"{r['name']} | Stock: {r['quantity']}", axis=1
            ).tolist()
        else:
            item_options = []

        # 2. Product Dropdown
        selected_item_str = st.selectbox(
            "Product", 
            options=item_options, 
            index=None, 
            placeholder="Select or type product..." if item_options else "No items in stock",
            disabled=len(item_options) == 0,
            key="pos_item_select"
        )

        # 3. Product Photo Preview
        max_available = 9999
        item_data = None
        if selected_item_str and not in_stock_df.empty:
            selected_idx = item_options.index(selected_item_str)
            item_data = in_stock_df.iloc[selected_idx]
            max_available = int(item_data["quantity"])
            
            photo = str(item_data.get("photo_url", "")).strip()
            if photo:
                st.image(photo, width=120)

        # 4. Quantity Input (Always visible)
        order_qty = st.number_input(
            "Qty", 
            min_value=1, 
            max_value=max_available if selected_item_str else 1, 
            value=1, 
            step=1, 
            disabled=not selected_item_str,
            key="pos_qty_input"
        )
        
        # 5. Add to Cart Button (Always visible)
        if st.button("➕ Add to Cart", use_container_width=True, type="secondary", disabled=not selected_item_str):
            if selected_item_str and item_data is not None:
                existing_cart_item = next((item for item in st.session_state["cart"] if item["name"] == item_data["name"]), None)
                
                if existing_cart_item:
                    if existing_cart_item["qty"] + order_qty > max_available:
                        st.error(f"Cannot add more. Max available stock is {max_available}.")
                    else:
                        existing_cart_item["qty"] += order_qty
                        st.success(f"Updated '{item_data['name']}' quantity!")
                        st.rerun()
                else:
                    st.session_state["cart"].append({
                        "sku": item_data["sku"],
                        "name": item_data["name"],
                        "qty": order_qty,
                        "price": float(item_data["price"]),
                        "max_stock": max_available
                    })
                    st.success(f"Added '{item_data['name']}' to cart!")
                    st.rerun()

    # --- RIGHT COLUMN: CART WITH DIRECT QTY EDITING ---
    with col_cart:
        st.markdown("##### Current Cart")
        
        if st.session_state["cart"]:
            # Table Header
            c_name, c_qty, c_price, c_subtotal = st.columns([2.5, 1.8, 1.5, 1.5])
            c_name.caption("**Name**")
            c_qty.caption("**Qty**")
            c_price.caption("**Unit Price**")
            c_subtotal.caption("**Subtotal**")
            st.divider()

            grand_total = 0.0
            items_to_remove = []

            # Dynamic Cart Rows with Editable Number Inputs
            for idx, item in enumerate(st.session_state["cart"]):
                subtotal = item["qty"] * item["price"]
                grand_total += subtotal

                row_name, row_qty, row_price, row_subtotal = st.columns([2.5, 1.8, 1.5, 1.5])
                
                row_name.write(item["name"])
                
                # Direct Manual Input for Quantity
                new_qty = row_qty.number_input(
                    label=f"qty_{idx}",
                    min_value=0,
                    max_value=int(item["max_stock"]),
                    value=int(item["qty"]),
                    step=1,
                    label_visibility="collapsed",
                    key=f"cart_qty_{idx}"
                )

                # Track if quantity was updated manually
                if new_qty != item["qty"]:
                    if new_qty == 0:
                        items_to_remove.append(idx)
                    else:
                        item["qty"] = new_qty
                    st.rerun()

                row_price.write(f"₱{item['price']:.2f}")
                row_subtotal.write(f"**₱{subtotal:,.2f}**")

            # Remove items whose quantity was set to 0
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
                    # Deduct quantities in Google Sheets
                    for item in st.session_state["cart"]:
                        match = df[df["name"] == item["name"]]
                        if not match.empty:
                            row_idx = match.index[0]
                            current_qty = int(df.iloc[row_idx]["quantity"])
                            new_qty = current_qty - item["qty"]
                            
                            row_number = row_idx + 2
                            qty_col_idx = df.columns.get_loc("quantity") + 1
                            sheet.update_cell(row_number, qty_col_idx, new_qty)
                    
                    # Construct audit log string
                    order_ref = f" [Order Ref: {order_name}]" if order_name else ""
                    order_summary = ", ".join([f"{i['name']} (x{i['qty']})" for i in st.session_state["cart"]])
                    
                    log_action(
                        st.session_state["username"],
                        "ORDER COMPLETED",
                        f"Items: [{order_summary}]{order_ref} | Total: ₱{grand_total:,.2f}"
                    )
                    
                    st.success(f"Order completed! Total: ₱{grand_total:,.2f}")
                    st.session_state["cart"] = []
                    st.rerun()
        else:
            st.info("Cart is empty. Select a product on the left to start.")

# ==========================================
# TAB 2: INVENTORY MANAGEMENT
# ==========================================
with tab_inventory:
    # --- SECTION 1: ADD / REMOVE STOCK ITEMS ---
    col_add, col_remove = st.columns(2)

    if "clear_add_flag" not in st.session_state:
        st.session_state["clear_add_flag"] = False
    if "clear_remove_flag" not in st.session_state:
        st.session_state["clear_remove_flag"] = False

    def reset_add_inputs():
        st.session_state["clear_add_flag"] = True

    def reset_remove_inputs():
        st.session_state["clear_remove_flag"] = True

    # --- ADD STOCK SECTION ---
    with col_add:
        with st.expander("➕ Add Stock Item", expanded=False):
            if st.session_state["clear_add_flag"]:
                st.session_state["add_name_input"] = ""
                st.session_state["add_sku_input"] = ""
                st.session_state["add_name_select"] = None
                st.session_state["add_sku_select"] = None
                st.session_state["add_qty_input"] = 1
                st.session_state["add_price_input"] = 0.0
                st.session_state["chk_is_new"] = False
                st.session_state["clear_add_flag"] = False

            is_new_item = st.checkbox("New Product (Not in list yet)", key="chk_is_new")
            
            # --- SAFELY BUILD EXISTING NAMES & SKUS LISTS ---
            if not df.empty and "name" in df.columns:
                existing_names = sorted(list(set([
                    str(name).strip() 
                    for name in df["name"].dropna().tolist() 
                    if str(name).strip() != ""
                ])))
            else:
                existing_names = []

            if not df.empty and "sku" in df.columns:
                existing_skus = sorted(list(set([
                    str(s).strip().upper() 
                    for s in df["sku"].dropna().tolist() 
                    if str(s).strip().upper() not in ["N/A", ""]
                ])))
            else:
                existing_skus = []
                
                selected_sku_type = st.selectbox(
                    "Search & Select Existing SKU (Optional)",
                    options=existing_skus,
                    index=None,
                    placeholder="Type or select existing SKU...",
                    key="add_sku_select"
                )

                if add_name:
                    selected_row = df[df["name"] == add_name].iloc[0]
                    add_sku = selected_sku_type if selected_sku_type else str(selected_row["sku"]).upper()
                    add_price = float(selected_row["price"])
                    st.caption(f"Current Price: ₱{add_price:.2f} | SKU: {add_sku}")
                elif selected_sku_type:
                    selected_row = df[df["sku"].astype(str).str.upper() == selected_sku_type.upper()].iloc[0]
                    add_name = selected_row["name"]
                    add_sku = selected_sku_type.upper()
                    add_price = float(selected_row["price"])
                    st.caption(f"Selected Item: {add_name} | Price: ₱{add_price:.2f}")
                else:
                    add_sku = ""
                    add_price = 0.0

            add_quantity = st.number_input("Quantity to Add", min_value=1, step=1, key="add_qty_input")

            # Product Photo Capture / Upload (Triggered on Demand)
            st.markdown("**Product Photo (Optional)**")
            
            photo_file = None
            
            # Toggle/Button to activate camera feed
            use_camera = st.checkbox("📷 Use Camera to Capture Photo", key="add_use_cam")
            
            if use_camera:
                cam_photo = st.camera_input("Take Photo", key="add_cam_photo")
                if cam_photo:
                    photo_file = cam_photo
            else:
                uploaded_photo = st.file_uploader("Upload Image File", type=["jpg", "jpeg", "png"], key="add_file_photo")
                if uploaded_photo:
                    photo_file = uploaded_photo

            if st.button("Save Stock", key="btn_save_new"):
                if add_name:
                    sku_val = add_sku if add_sku else "N/A"
                    photo_url = upload_image_to_cloud(photo_file) if photo_file else ""
                    
                    name_match = df[df["name"].astype(str).str.lower() == add_name.lower()]
                    sku_match = df[(df["sku"].astype(str).str.upper() == sku_val.upper()) & (sku_val.upper() != "N/A")]
                    
                    existing_match = name_match if not name_match.empty else sku_match
                    
                    if not existing_match.empty:
                        row_idx = existing_match.index[0]
                        current_qty = int(df.iloc[row_idx]["quantity"])
                        new_qty = current_qty + add_quantity
                        
                        row_number = row_idx + 2
                        qty_col_idx = df.columns.get_loc("quantity") + 1
                        sheet.update_cell(row_number, qty_col_idx, new_qty)
                        
                        # Update photo URL if a new photo was uploaded
                        if photo_url and "photo_url" in df.columns:
                            photo_col_idx = df.columns.get_loc("photo_url") + 1
                            sheet.update_cell(row_number, photo_col_idx, photo_url)

                        log_action(
                            st.session_state["username"], 
                            "ADD STOCK", 
                            f"Added {add_quantity} to existing '{add_name}' [SKU: {sku_val}] (New Total: {new_qty})"
                        )
                        st.success(f"Added {add_quantity} to existing item '{add_name}'. New total: {new_qty}")
                    else:
                        new_id = len(df) + 1
                        sheet.append_row([new_id, sku_val, add_name, add_quantity, add_price, photo_url])
                        
                        log_action(
                            st.session_state["username"], 
                            "ADD ITEM", 
                            f"Created new item SKU: {sku_val}, Name: {add_name}, Qty: {add_quantity}, Price: ₱{add_price}"
                        )
                        st.success(f"Added new item '{add_name}' successfully!")
                    
                    reset_add_inputs()
                    st.rerun()
                else:
                    st.error("Please select or enter an Item Name first.")

    # --- REMOVE STOCK SECTION ---
    with col_remove:
        with st.expander("➖ Remove / Deduct Stock", expanded=False):
            if not df.empty:
                if st.session_state["clear_remove_flag"]:
                    st.session_state["remove_select_input"] = None
                    st.session_state["remove_qty_input"] = 1
                    st.session_state["remove_reason_input"] = ""
                    st.session_state["clear_remove_flag"] = False

                item_options = df.apply(lambda r: f"{r['name']} - {r['sku']} (Current: {r['quantity']})", axis=1).tolist()
                selected_item_str = st.selectbox(
                    "Select Item to Deduct", 
                    options=item_options, 
                    index=None,
                    placeholder="Type or select an item...",
                    key="remove_select_input"
                )
                
                deduct_qty = st.number_input("Quantity to Remove", min_value=1, step=1, key="remove_qty_input")
                reason = st.text_input("Reason (Optional)", placeholder="e.g., Sold, Damaged, Expired", key="remove_reason_input")
                
                if st.button("Deduct Stock", key="btn_deduct_stock"):
                    if selected_item_str:
                        selected_idx = item_options.index(selected_item_str)
                        row_data = df.iloc[selected_idx]
                        current_qty = int(row_data["quantity"])
                        item_name = row_data["name"]
                        
                        if deduct_qty > current_qty:
                            st.error(f"Cannot remove {deduct_qty}. Only {current_qty} in stock!")
                        else:
                            new_qty = current_qty - deduct_qty
                            row_number = selected_idx + 2
                            qty_col_idx = df.columns.get_loc("quantity") + 1
                            
                            sheet.update_cell(row_number, qty_col_idx, new_qty)
                            reason_str = f" | Reason: {reason}" if reason else ""
                            
                            log_action(
                                st.session_state["username"],
                                "REMOVE STOCK",
                                f"Deducted {deduct_qty} from '{item_name}' (Remaining: {new_qty}){reason_str}"
                            )
                            st.success(f"Deducted {deduct_qty} from '{item_name}'. New total: {new_qty}")
                            
                            reset_remove_inputs()
                            st.rerun()
                    else:
                        st.error("Please select an item to deduct.")
            else:
                st.info("No items in inventory to remove.")

    # --- SECTION 2: EDIT & MANAGE INVENTORY ---
    st.subheader("📋 Current Stock Levels")

    @st.fragment(run_every=30)
    def render_live_inventory():
        df_live = load_data()
        
        if not df_live.empty:
            edited_df = st.data_editor(
                df_live,
                key="inventory_editor",
                use_container_width=True,
                hide_index=True,
                disabled=["id", "sku"],
                column_config={
                    "photo_url": st.column_config.ImageColumn("Image", help="Product image thumbnail", width="small"),
                    "price": st.column_config.NumberColumn("Price", format="₱%.2f"),
                    "quantity": st.column_config.NumberColumn("Quantity"),
                }
            )

            if st.button("💾 Save All Edits"):
                changes = st.session_state["inventory_editor"]["edited_rows"]
                if changes:
                    for row_idx, updated_cols in changes.items():
                        row_number = row_idx + 2
                        item_name = df_live.iloc[row_idx]["name"]
                        
                        for col_name, new_val in updated_cols.items():
                            col_idx = df_live.columns.get_loc(col_name) + 1
                            old_val = df_live.iloc[row_idx][col_name]
                            sheet.update_cell(row_number, col_idx, new_val)
                            
                            log_action(
                                st.session_state["username"],
                                "UPDATE ITEM", 
                                f"Changed '{item_name}' ({col_name}): {old_val} ➔ {new_val}"
                            )
                    
                    st.success("All edits saved and logged successfully!")
                    st.rerun()
                else:
                    st.info("No changes were made.")
        else:
            st.info("No items found in your inventory sheet.")

    render_live_inventory()

    # --- SECTION 3: AUDIT LOG VIEWER (ADMIN ONLY) ---
    if st.session_state["username"] == "admin":
        st.divider()
        
        @st.fragment(run_every=30)
        def render_live_logs():
            with st.expander("📜 View Audit Log (Live - Auto Refreshes Every 30s)", expanded=True):
                logs = log_sheet.get_all_records()
                if logs:
                    log_df = pd.DataFrame(logs)
                    st.dataframe(
                        log_df.sort_values(by="Timestamp", ascending=False), 
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.info("No activity recorded yet.")
                
                st.caption("🔄 Auto-sync active. Checking for new staff updates every 30 seconds...")

        render_live_logs()
