import streamlit as st
import gspread
import pandas as pd
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Ellie Store Inventory", page_icon="📦", layout="wide")

# --- USER AUTHENTICATION ---
# Users and Passwords defined in Secrets or local fallback
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
                st.success(f"Welcome, {username}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

if not st.session_state["authenticated"]:
    login()
    st.stop()

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_gsheet():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open("Inventory DB")
    
    # Ensure audit log worksheet exists
    try:
        log_sheet = sh.worksheet("Logs")
    except gspread.exceptions.WorksheetNotFound:
        log_sheet = sh.add_worksheet(title="Logs", rows="1000", cols="4")
        log_sheet.append_row(["Timestamp", "User", "Action", "Details"])
        
    return sh.sheet1, log_sheet

sheet, log_sheet = get_gsheet()

# --- AUDIT LOG FUNCTION ---
def log_action(action: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = st.session_state["username"]
    log_sheet.append_row([timestamp, user, action, details])

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
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.rerun()

st.title("📦 Ellie Store Inventory")
st.caption(f"Logged in as **{st.session_state['username']}** | Connected to Google Sheets")

st.divider()

# --- SECTION 1: ADD NEW ITEM ---
with st.expander("➕ Add New Stock Item", expanded=False):
    with st.form("add_item_form", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            sku = st.text_input("SKU Code")
        with col2:
            name = st.text_input("Item Name")
        with col3:
            quantity = st.number_input("Quantity", min_value=0, step=1)
        with col4:
            price = st.number_input("Price (₱)", min_value=0.0, step=0.5, format="%.2f")
        
        submitted = st.form_submit_button("Save Item")
        if submitted:
            if sku and name:
                new_id = len(df) + 1
                sheet.append_row([new_id, sku, name, quantity, price])
                log_action("ADD ITEM", f"Added SKU: {sku}, Name: {name}, Qty: {quantity}, Price: ₱{price}")
                st.success(f"Added '{name}' successfully!")
                st.rerun()
            else:
                st.error("Please fill out both SKU and Item Name.")

# --- SECTION 2: EDIT & MANAGE INVENTORY ---
st.subheader("📋 Current Stock Levels")

if not df.empty:
    edited_df = st.data_editor(
        df,
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
                row_number = row_idx + 2  # Header is row 1
                item_name = df.iloc[row_idx]["name"]
                
                for col_name, new_val in updated_cols.items():
                    col_idx = df.columns.get_loc(col_name) + 1
                    old_val = df.iloc[row_idx][col_name]
                    sheet.update_cell(row_number, col_idx, new_val)
                    
                    log_action(
                        "UPDATE ITEM", 
                        f"Changed '{item_name}' ({col_name}): {old_val} ➔ {new_val}"
                    )
            
            st.success("All edits saved and logged successfully!")
            st.rerun()
        else:
            st.info("No changes were made.")
else:
    st.info("No items found in your inventory sheet.")

# --- SECTION 3: AUDIT LOG VIEWER ---
st.divider()
with st.expander("📜 View Audit Log (Worker Actions)", expanded=False):
    logs = log_sheet.get_all_records()
    if logs:
        log_df = pd.DataFrame(logs)
        st.dataframe(log_df.sort_values(by="Timestamp", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No activity recorded yet.")
