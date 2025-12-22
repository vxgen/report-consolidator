import streamlit as st
import pandas as pd
from datetime import datetime
import os

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
    conn = st.connection("gsheets", type=GSheetsConnection)
    
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
                    user_db = conn.read(worksheet="users", ttl=0)
                    match = user_db[(user_db['username'] == user) & (user_db['password'] == pw)]
                    if not match.empty:
                        st.session_state["password_correct"] = True
                        st.session_state["current_user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                except Exception as e:
                    st.error("Error connecting to user database. Check if 'users' tab exists.")

    with tab2:
        st.info("Registration will save credentials to your Google Sheet.")
        with st.form("register_form"):
            new_user = st.text_input("Choose a Username")
            new_pw = st.text_input("Choose a Password", type="password")
            confirm_pw = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Create Account"):
                user_db = conn.read(worksheet="users", ttl=0)
                if new_user in user_db['username'].astype(str).values:
                    st.warning("Username already exists!")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match")
                elif len(new_pw) < 4:
                    st.error("Password must be at least 4 characters")
                else:
                    new_entry = pd.DataFrame([{"username": new_user, "password": new_pw}])
                    updated_users = pd.concat([user_db, new_entry], ignore_index=True)
                    conn.update(worksheet="users", data=updated_users)
                    st.success("Account created! You can now log in on the left tab.")
    return False

# --- 4. Main Application Logic ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    st.title("☁️ Cloud Inventory Consolidator")
    st.caption(f"Logged in as: {st.session_state.get('current_user', 'Admin')}")

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
        new_name = nc1.text_input("New Column Name:")
        if nc2.button("➕ Add"):
            if new_name: 
                st.session_state.target_columns.append(new_name)
                st.rerun()

    # --- STEP 2: UPLOAD & MAPPING ---
    st.header("📤 Step 2: Upload & Map")
    uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)

    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            with st.container(border=True):
                st.subheader(f"📄 {file.name}")
                d_name = st.text_input("Friendly Name:", value=f"Import_{i+1}", key=f"d_{file.name}")
                df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                
                mapping_dict = {}
                m_cols = st.columns(3)
                for idx, t_col in enumerate(st.session_state.target_columns):
                    mapping_dict[t_col] = m_cols[idx % 3].selectbox(f"Map to {t_col}", [None] + df_source.columns.tolist(), key=f"m_{file.name}_{t_col}")

                if st.button(f"Process & Save {d_name}", key=f"b_{file.name}"):
                    valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                    if valid_maps:
                        new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                        batch_id = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_df['batch_id'], new_df['upload_time'] = batch_id, now
                        new_df['file_display_name'] = d_name

                        try:
                            existing_data = conn.read(worksheet="Sheet1", ttl=0)
                            updated_df = pd.concat([existing_data, new_df], ignore_index=True, sort=False)
                        except:
                            updated_df = new_df
                        
                        conn.update(worksheet="Sheet1", data=updated_df)
                        st.success(f"Saved {d_name} to Cloud!")
                        st.rerun()

    st.divider()

    # --- STEP 3: MANAGE SEGMENTS ---
    st.header("📋 Step 3: Manage Cloud Segments")
    try:
        master_data = conn.read(worksheet="Sheet1", ttl=0)
        if not master_data.empty and 'batch_id' in master_data.columns:
            unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
            selected_batches = []
            
            for _, row in unique_imports.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 4, 2])
                    if c1.checkbox("", key=f"sel_{row['batch_id']}"):
                        selected_batches.append(row['batch_id'])
                    c2.write(f"**{row['file_display_name']}**")
                    c2.caption(f"Time: {row['upload_time']}")
                    
                    if c3.button("🗑️ Delete", key=f"del_{row['batch_id']}"):
                        remaining = master_data[master_data['batch_id'] != row['batch_id']]
                        conn.update(worksheet="Sheet1", data=remaining)
                        st.rerun()

            if selected_batches:
                if st.button("Generate Combined Report"):
                    combined = master_data[master_data['batch_id'].isin(selected_batches)]
                    st.dataframe(combined[[c for c in st.session_state.target_columns if c in combined.columns]])
                    csv = combined.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Combined", data=csv, file_name="combined.csv")
        else:
            st.info("No data in cloud.")
    except Exception as e:
        st.error(f"Error fetching data: {e}")

    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()
