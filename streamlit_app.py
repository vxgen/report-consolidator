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
    st.error("Missing libraries. Ensure 'requirements.txt' includes: st-gsheets-connection, pytz")
    st.stop()

def get_sydney_time():
    sydney_tz = pytz.timezone('Australia/Sydney')
    return datetime.now(sydney_tz).strftime("%Y-%m-%d %H:%M:%S")

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="Cloud Inventory Manager", layout="wide")

# --- 3. AUTHENTICATION ---
def check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Inventory System Access")
    with st.form("login_form"):
        user = st.text_input("Username").strip()
        pw = st.text_input("Password", type="password").strip()
        if st.form_submit_button("Login"):
            try:
                user_db = conn.read(spreadsheet=USER_SHEET_URL, worksheet="users", ttl="30s")
                user_db.columns = user_db.columns.str.strip()
                match = user_db[(user_db['username'].astype(str) == user) & (user_db['password'].astype(str) == pw)]
                if not match.empty and str(match.iloc[0]['approved']).strip().upper() == "YES":
                    st.session_state["password_correct"] = True
                    st.session_state["current_user"] = user
                    st.rerun()
                else: st.error("Access Denied.")
            except: st.error("Cloud Connection Error.")
    return False

if check_password():
    conn_cloud = st.connection("gsheets", type=GSheetsConnection)
    
    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]
    
    st.title("☁️ Cloud Inventory Consolidator")
    main_tab, preset_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "🗺️ Mapping Presets", "📁 Historical Archive"])

    # --- TAB 2: MAPPING PRESETS ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="5s")
        except:
            presets_db = pd.DataFrame(columns=["client_name", "rule_name"] + st.session_state.target_columns)

        # NEW: Search Bar for Presets
        search_query = st.text_input("🔍 Search Presets (Client or Rule Name):", placeholder="e.g. Umart").strip().lower()
        
        if not presets_db.empty:
            filtered_presets = presets_db[
                presets_db['client_name'].str.lower().str.contains(search_query) | 
                presets_db['rule_name'].str.lower().str.contains(search_query)
            ]
            st.subheader("Filtered Rules")
            st.dataframe(filtered_presets, use_container_width=True)
        
        with st.expander("➕ Create New Mapping Rule"):
            with st.form("new_rule_form"):
                p_client = st.text_input("Client Name")
                p_rule = st.text_input("Rule Name")
                new_mapping = {"client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    new_mapping[t_col] = st.text_input(f"CSV Header for '{t_col}':")
                
                if st.form_submit_button("Save Mapping Rule"):
                    if p_client and p_rule:
                        updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                        conn_cloud.update(worksheet="presets", data=updated_presets)
                        st.success("Saved!")
                        st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        # Step 1: Format
        with st.expander("⚙️ Step 1: Target Format"):
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5, 1])
                st.session_state.target_columns[i] = c1.text_input(f"Col {i+1}", value=col, key=f"e_{i}")
                if c2.button("🗑️", key=f"d_{i}"): cols_to_remove.append(col)
            for col in cols_to_remove: 
                st.session_state.target_columns.remove(col)
                st.rerun()

        # Step 2: Upload & Map
        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)
        
        if uploaded_files:
            try: rules = conn_cloud.read(worksheet="presets", ttl="5s")
            except: rules = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    
                    preset_options = ["Manual / Smart Match"]
                    if not rules.empty:
                        preset_options += (rules['client_name'] + " - " + rules['rule_name']).tolist()
                    
                    sel_rule_full = st.selectbox("Apply Saved Rule:", preset_options, key=f"rs_{i}")
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    source_cols = df_source.columns.tolist()
                    
                    mapping_dict = {}
                    m_cols = st.columns(3)
                    
                    # Logic for Preset or Smart Match
                    active_rule = None
                    if sel_rule_full != "Manual / Smart Match":
                        c_name, r_name = sel_rule_full.split(" - ")
                        active_rule = rules[(rules['client_name'] == c_name) & (rules['rule_name'] == r_name)].iloc[0]

                    for idx, t_col in enumerate(st.session_state.target_columns):
                        default_idx = 0
                        
                        # A: Priority - Preset Match
                        if active_rule is not None and t_col in active_rule:
                            target_header = active_rule[t_col]
                            if target_header in source_cols:
                                default_idx = source_cols.index(target_header) + 1
                        
                        # B: Secondary - Smart Match (Containment Logic)
                        if default_idx == 0:
                            for s_col in source_cols:
                                if t_col.lower() in s_col.lower() or s_col.lower() in t_col.lower():
                                    default_idx = source_cols.index(s_col) + 1
                                    break
                        
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(
                            f"Map {t_col}", [None] + source_cols, index=default_idx, key=f"m_{file.name}_{t_col}"
                        )

                    if st.button(f"Confirm & Save {file.name}", key=f"b_{file.name}"):
                        valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                        if valid_maps:
                            new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                            new_df['batch_id'] = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                            new_df['upload_time'] = get_sydney_time()
                            new_df['file_display_name'] = file.name
                            new_df['uploaded_by'] = st.session_state['current_user']

                            # Concatenate to Cloud
                            try:
                                master = conn_cloud.read(worksheet="Sheet1", ttl="0s")
                                updated = pd.concat([master, new_df], ignore_index=True)
                                conn_cloud.update(worksheet="Sheet1", data=updated)
                                st.success("Saved!")
                                time.sleep(1)
                                st.rerun()
                            except: st.error("Cloud Busy.")

        st.divider()
        st.header("📋 Step 3: Manage Cloud Segments")
        # (Step 3 deletion and consolidation logic remains here)
        try:
            master_data = conn_cloud.read(worksheet="Sheet1", ttl="5s")
            if not master_data.empty:
                unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
                selected_batches = []
                for _, row in unique_imports.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 2])
                        if c1.checkbox("", key=f"s_{row['batch_id']}"): selected_batches.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}**")
                        if c3.button("🗑️", key=f"d_{row['batch_id']}"):
                            conn_cloud.update(worksheet="Sheet1", data=master_data[master_data['batch_id'] != row['batch_id']])
                            st.rerun()

                if selected_batches and st.button("📊 Consolidated Report"):
                    st.dataframe(master_data[master_data['batch_id'].isin(selected_batches)], use_container_width=True)
            else: st.info("No active segments.")
        except: pass

    with archive_tab:
        st.header("Archive")
        try:
            archived = conn_cloud.read(worksheet="archive", ttl="10s")
            if not archived.empty: st.dataframe(archived, use_container_width=True)
        except: st.warning("Ready for archive data.")
