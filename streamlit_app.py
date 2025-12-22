import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time

# --- 0. GLOBAL CONFIGURATION ---
USER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KG8qWTYLa6GEWByYIg2vz3bHrGdW3gvqD_detwhyj7k/edit?gid=522749285#gid=522749285"

# --- 1. IMPORT CHECK ---
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    st.error("Missing libraries. Ensure 'requirements.txt' includes st-gsheets-connection.")
    st.stop()

# Helper for Sydney Time
def get_sydney_time():
    sydney_tz = pytz.timezone('Australia/Sydney')
    return datetime.now(sydney_tz).strftime("%Y-%m-%d %I:%M %p")

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 3. SECURE AUTHENTICATION SYSTEM ---
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
                    # Cache user check for 30s to save quota
                    user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl="30s")
                    user_db.columns = user_db.columns.str.strip()
                    match = user_db[(user_db['username'].astype(str) == user) & 
                                    (user_db['password'].astype(str) == pw)]
                    if not match.empty:
                        if str(match.iloc[0]['approved']).strip().upper() == "YES":
                            st.session_state["password_correct"] = True
                            st.session_state["current_user"] = user
                            st.rerun()
                        else:
                            st.warning("⚠️ Account pending approval.")
                    else:
                        st.error("❌ Invalid credentials")
                except Exception as e:
                    st.error("Google is busy. Wait 10 seconds.")
    return False

# --- 4. MAIN APPLICATION LOGIC ---
if check_password():
    conn_reports = st.connection("gsheets", type=GSheetsConnection)
    
    st.sidebar.title("👤 User Profile")
    st.sidebar.write(f"Logged in: **{st.session_state['current_user']}**")
    if st.sidebar.button("Log Out"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("☁️ Cloud Inventory Consolidator")
    
    main_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "📁 Historical Archive"])

    with main_tab:
        if 'target_columns' not in st.session_state:
            st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]

        # --- STEP 1: SCHEMA ---
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

        # --- STEP 2: UPLOAD & MAP ---
        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)
        if uploaded_files:
            # We fetch existing data ONCE per page load to save quota
            try:
                active_data_cache = conn_reports.read(worksheet="Sheet1", ttl="5s")
            except:
                active_data_cache = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    d_name = st.text_input("Friendly Name:", value=f"Import_{i+1}", key=f"d_{file.name}")
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    
                    mapping_dict = {}
                    m_cols = st.columns(3)
                    for idx, t_col in enumerate(st.session_state.target_columns):
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(f"Map {t_col}", [None] + df_source.columns.tolist(), key=f"m_{file.name}_{t_col}")

                    if st.button(f"Process & Save {d_name}", key=f"b_{file.name}"):
                        valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                        if valid_maps:
                            new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                            new_df['batch_id'] = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                            new_df['upload_time'] = get_sydney_time()
                            new_df['file_display_name'] = d_name
                            new_df['uploaded_by'] = st.session_state['current_user']

                            try:
                                with st.spinner("Saving to Cloud..."):
                                    # Update by appending to our local cache first
                                    updated_df = pd.concat([active_data_cache, new_df], ignore_index=True, sort=False)
                                    conn_reports.update(worksheet="Sheet1", data=updated_df)
                                    st.cache_data.clear()
                                    st.success("Successfully Saved!")
                                    time.sleep(2) # API Safety pause
                                    st.rerun()
                            except Exception as e:
                                if "429" in str(e):
                                    st.error("Too many requests! Wait 15 seconds and try again.")
                                else:
                                    st.error(f"Save Error: {e}")

        st.divider()

        # --- STEP 3: MANAGE ---
        st.header("📋 Step 3: Manage Cloud Segments")
        try:
            master_data = conn_reports.read(worksheet="Sheet1", ttl="10s")
            if not master_data.empty and 'batch_id' in master_data.columns:
                unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time', 'uploaded_by']].drop_duplicates()
                selected_batches = []
                for _, row in unique_imports.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 2])
                        if c1.checkbox("", key=f"sel_{row['batch_id']}"):
                            selected_batches.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}**")
                        c2.caption(f"By: {row['uploaded_by']} | {row['upload_time']}")
                        if c3.button("🗑️ Delete", key=f"del_{row['batch_id']}"):
                            remaining = master_data[master_data['batch_id'] != row['batch_id']]
                            conn_reports.update(worksheet="Sheet1", data=remaining)
                            st.cache_data.clear()
                            st.rerun()
                        
                        with st.expander("👁️ View & Download"):
                            ind_df = master_data[master_data['batch_id'] == row['batch_id']]
                            st.dataframe(ind_df[[c for c in st.session_state.target_columns if c in ind_df.columns]])
                            csv = ind_df.to_csv(index=False).encode('utf-8')
                            st.download_button("📥 Download", data=csv, file_name=f"{row['file_display_name']}.csv", key=f"dl_{row['batch_id']}")

                if selected_batches:
                    b1, b2 = st.columns(2)
                    if b1.button("📂 Archive Selected"):
                        with st.spinner("Archiving..."):
                            to_archive = master_data[master_data['batch_id'].isin(selected_batches)]
                            remaining = master_data[~master_data['batch_id'].isin(selected_batches)]
                            try:
                                archive_db = conn_reports.read(worksheet="archive", ttl="5s")
                                updated_archive = pd.concat([archive_db, to_archive], ignore_index=True)
                                conn_reports.update(worksheet="archive", data=updated_archive)
                                conn_reports.update(worksheet="Sheet1", data=remaining)
                                st.cache_data.clear()
                                st.success("Archived!")
                                time.sleep(2)
                                st.rerun()
                            except: st.error("Check 'archive' tab.")
            else: st.info("No active segments.")
        except: st.warning("Connecting to Cloud...")

    with archive_tab:
        st.header("📁 Archive")
        try:
            archived_df = conn_reports.read(worksheet="archive", ttl="10s")
            if not archived_df.empty:
                st.dataframe(archived_df)
                if st.button("🧹 Clear Archive"):
                    conn_reports.update(worksheet="archive", data=pd.DataFrame(columns=archived_df.columns))
                    st.cache_data.clear()
                    st.rerun()
            else: st.info("Archive is empty.")
        except: st.error("Ensure 'archive' tab exists.")
