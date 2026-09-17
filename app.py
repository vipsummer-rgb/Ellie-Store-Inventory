import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

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
        return pd.DataFrame(columns=["id", "sku", "name", "quantity", "price"])
    return pd.DataFrame(records)

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

st.divider()

# --- SECTION 1: ADD / REMOVE STOCK ITEMS ---
col_add, col_remove = st.columns(2)

# Initialize reset flags in session_state if they don't exist
if "clear_add_flag" not in st.session_state:
    st.session_state["clear_add_flag"] = False
if "clear_remove_flag" not in st.session_state:
    st.session_state["clear_remove_flag"] = False

# Callback functions to reset inputs BEFORE the rerun cycle finishes
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
        
        # Get unique existing names and valid SKUs
        existing_names = sorted(df["name"].dropna().unique().tolist()) if not df.empty else []
        existing_skus = sorted([str(s) for s in df["sku"].dropna().unique() if str(s).upper() != "N/A"]) if not df.empty else []

        if is_new_item or not existing_names:
            add_name = st.text_input("Item Name", key="add_name_input").strip()
            add_sku = st.text_input("SKU Code (Optional)", key="add_sku_input").strip().upper()
            add_price = st.number_input("Price (₱)", min_value=0.0, step=0.5, format="%.2f", key="add_price_input")
        else:
            # Dropdown for existing items
            add_name = st.selectbox(
                "Search & Select Item Name", 
                options=existing_names, 
                index=None, 
                placeholder="Type or select item name...",
                key="add_name_select"
            )
            
            # Dropdown suggestion for existing SKUs
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
        
        if st.button("Save Stock", key="btn_save_new"):
            if add_name:
                sku_val = add_sku if add_sku else "N/A"
                
                # Check for match by Name OR by SKU (case-insensitive)
                name_match = df[df["name"].astype(str).str.lower() == add_name.lower()]
                sku_match = df[(df["sku"].astype(str).str.upper() == sku_val.upper()) & (sku_val.upper() != "N/A")]
                
                existing_match = name_match if not name_match.empty else sku_match
                
                if not existing_match.empty:
                    # MATCH FOUND: Merge and update existing row
                    row_idx = existing_match.index[0]
                    current_qty = int(df.iloc[row_idx]["quantity"])
                    new_qty = current_qty + add_quantity
                    
                    row_number = row_idx + 2
                    qty_col_idx = df.columns.get_loc("quantity") + 1
                    sheet.update_cell(row_number, qty_col_idx, new_qty)
                    
                    log_action(
                        st.session_state["username"], 
                        "ADD STOCK", 
                        f"Added {add_quantity} to existing '{add_name}' [SKU: {sku_val}] (New Total: {new_qty})"
                    )
                    st.success(f"Added {add_quantity} to existing item '{add_name}'. New total: {new_qty}")
                else:
                    # NEW ITEM: Save SKU in clean UPPERCASE
                    new_id = len(df) + 1
                    sheet.append_row([new_id, sku_val, add_name, add_quantity, add_price])
                    
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
    # Fetch latest data from Google Sheets on every 30s cycle
    df_live = load_data()
    
    if not df_live.empty:
        edited_df = st.data_editor(
            df_live,
            key="inventory_editor",
            use_container_width=True,
            hide_index=True,
            disabled=["id", "sku"],
            column_config={
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
    
    # Auto-refresh log container every 30 seconds (30000 ms)
    @st.fragment(run_every=30)
    def render_live_logs():
        with st.expander("📜 View Audit Log (Live - Auto Refreshes Every 30s)", expanded=True):
            # Fetch fresh data from Google Sheets
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
