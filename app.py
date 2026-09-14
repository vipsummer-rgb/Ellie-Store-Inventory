import streamlit as st
import gspread
import pandas as pd

# Page Configuration
st.set_page_config(page_title="Ellie Store Inventory", page_icon="📦", layout="wide")

st.title("📦 Ellie Store Inventory")
st.caption("Cloud-Connected Google Sheets Dashboard")

# Connect to Google Sheets
@st.cache_resource
def get_gsheet():
    credentials = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open("Inventory DB").sheet1

sheet = get_gsheet()

# Helper function to fetch data as DataFrame
def load_data():
    records = sheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=["id", "sku", "name", "quantity", "price"])
    df = pd.DataFrame(records)
    return df

df = load_data()

# Refresh Button
if st.button("🔄 Refresh Data"):
    st.rerun()

st.divider()

# Section 1: Add New Item
with st.expander("➕ Add New Stock Item", expanded=True):
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
                st.success(f"Added {name} successfully!")
                st.rerun()
            else:
                st.error("Please fill out both SKU and Item Name.")

# Section 2: Display & Manage Inventory
st.subheader("Current Stock Levels")

if not df.empty:
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "price": st.column_config.NumberColumn("Price", format="₱%.2f"),
            "quantity": st.column_config.NumberColumn("Quantity"),
        },
        hide_index=True,
    )
else:
    st.info("No items found in your inventory sheet.")
