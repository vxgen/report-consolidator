import streamlit as st
import pandas as pd
from datetime import datetime

# --- 0. GLOBAL CONFIGURATION ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gvqD_detwhyj7k/edit?gid=522749285#gid=522749285"

# --- 1. IMPORT CHECK ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("Missing libraries. Check requirements.txt")
    st.stop()

st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 2. SECURE AUTHENTICATION WITH APPROVAL ---
def check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Inventory System Access")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Register"])

    with tab1:
        with st.form("login_form"):
            user = st.text_input("Username").strip()
            pw = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl=0)
                    # Normalize columns to handle potential spaces
                    user_db.columns = user_db.columns.str.strip()
                    
                    # Search for matching user
                    match = user_db[(user_db['username'].astype(str) == user) & 
                                    (user_db['password'].astype(str) == pw)]
                    
                    if not match.empty:
                        status = str(match.iloc[0]['approved']).strip().upper()
                        if status == "YES":
                            st.session_state["password_correct"] = True
                            st.session_state["current_user"] = user
                            st.rerun()
                        else:
                            st.warning("⚠️ Your account is pending admin approval. Please contact the manager.")
                    else:
                        st.error("❌ Invalid username or password")
                except Exception as e:
                    st.error(f"Login Error: {e}")

    with tab2:
        st.info("Submit your details. An admin must approve your account before you can log in.")
        with st.form("register_form"):
            new_user = st.text_input("Desired Username").strip()
            new_pw = st.text_input("Desired Password", type="password").strip()
            confirm_pw = st.text_input("Confirm Password", type="password").strip()
            
            if st.form_submit_button("Submit Registration"):
                try:
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl=0)
                    if new_user.lower() in user_db['username'].astype(str).str.lower().values:
                        st.warning("Username already exists!")
                    elif new_pw != confirm_pw:
                        st.error("Passwords do not match")
                    elif len(new_pw) < 6:
                        st.error("Security: Password must be at least 6 characters")
                    else:
                        # New users are added with 'approved' set to 'NO'
                        new_entry = pd.DataFrame([{
                            "username": str(new_user), 
                            "password": str(new_pw),
                            "approved": "NO" 
                        }])
                        updated_users = pd.concat([user_db, new_entry], ignore_index=True)
                        conn.update(spreadsheet=USER_SHEET_URL, worksheet="users", data=updated_users)
                        st.success("✅ Registration submitted! Please wait for admin approval.")
                except Exception as e:
                    st.error(f"Registration Error: {e}")
    return False

# --- 3. MAIN APPLICATION LOGIC ---
if check_password():
    conn_reports = st.connection("gsheets", type=GSheetsConnection)
    
    st.sidebar.title("👤 Session")
    st.sidebar.write(f"User: **{st.session_state['current_user']}**")
    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("☁️ Cloud Inventory Consolidator")
    
    # Rest of your app logic (Step 1, 2, 3) goes here...
    st.write("Welcome to the secure dashboard.")
