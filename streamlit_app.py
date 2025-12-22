import streamlit as st
import pandas as pd
from datetime import datetime
import os
# --- 0. Global Configuration ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1CFyv3g4E4HzbP04iyv3SvSN4XkvedzYMMkrAH-RSHyY/edit#gid=0"
# --- 1. Robust Import Check ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("The 'st-gsheets-connection' library is not installed correctly. Please check requirements.txt.")
    st.stop()

# --- 2. Adaptive Page Config ---
st.set_page_config(page_title="Cloud Report Manager", layout="wide")

# --- 3. Authentication & Registration System ---
def check_password():
    """Returns True if the user has a valid login."""
    # Connecting to the specific User Registration Sheet
    user_sheet_url = "https://docs.google.com/spreadsheets/d/1CFyv3g4E4HzbP04iyv3SvSN4XkvedzYMMkrAH-RSHyY/edit#gid=0"
    conn_users = st.connection("gsheets", type=GSheetsConnection)
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Access Control")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Register New User"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                try:
                    # Read from the specific user sheet
                    user_db = conn_users.read(spreadsheet=user_sheet_url, worksheet="users", ttl=0)
                    match = user_db[(user_db['username'].astype(str) == user) & (user_db['password'].astype(str) == pw)]
                    if not match.empty:
                        st.session_state["password_correct"] = True
                        st.session_state["current_user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                except Exception as e:
                    st.error(f"Connection Error: Ensure the 'users' tab exists in the provided Google Sheet.")

    with tab2:
        st.info("Registration saves credentials to the centralized user database.")
        with st.form("register_form"):
            new_user = st.text_input("Choose a Username")
            new_pw = st.text_input("Choose a Password", type="password")
            confirm_pw = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Create Account"):
                try:
                    user_db = conn_users.read(spreadsheet=user_sheet_url, worksheet="users", ttl=0)
                    if new_user in user_db['username'].astype(str).values:
                        st.warning("Username already exists!")
                    elif new_pw != confirm_pw:
                        st.error("Passwords do not match")
                    elif len(new_pw) < 4:
                        st.error("Password must be at least 4 characters")
                    else:
                        new_entry = pd.DataFrame([{"username": new_user, "password": new_pw}])
                        updated_users = pd.concat([user_db, new_entry], ignore_index=True)
                        conn_users.update(spreadsheet=user_sheet_url, worksheet="users", data=updated_users)
                        st.success("Account created! You can now log in.")
                except Exception as e:
                    st.error("Failed to register. Check spreadsheet permissions.")
    return False

# --- 4. Main Application Logic ---
if check_password():
    # This connection uses the default spreadsheet defined in your Secrets for report data
    conn_reports = st.connection("gsheets", type=GSheetsConnection)
    
    st.title("☁️ Cloud Inventory Consolidator")
    st.sidebar.write(f"Logged in as: **{st.session_state.get('current_user', 'User')}**")

    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]

    # --- STEP 1: SCHEMA CONFIGURATION ---
    with st.expander("⚙️ Step 1: Configure Target Format"):
        cols_to_remove = []
        for i, col in enumerate(st.session_state.target_columns):
            c1, c2 = st.columns([5, 1])
            st.session_state.target_columns[i] = c1.text_input(f"Col {i+1}", value=col, key=f"edit_{i}")
            if c2.button("🗑️", key=f"del_{i}"): cols_to_remove.append(col)
        for col in cols_to_remove: 
            st.session_state.target_columns.remove(col)
            st.rerun()
        nc1, nc2 = st.columns([5, 1])
        new_

