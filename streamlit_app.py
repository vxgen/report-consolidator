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
            presets_db = conn_cloud.read(worksheet="presets", ttl="0s")
        except Exception as e:
            st.error("⚠️ The worksheet 'presets' was not found in your Google Sheet.")
            st.info("Please create a new tab named 'presets' in your Google Sheet and refresh this page.")
            presets_db = pd.DataFrame(columns=["preset_id", "client_name", "rule_name"] + st.session_state.target_columns)

        with st.expander("➕ Add New Mapping Rule"):
            with st.form("add_preset_form"):
                p_client = st.text_input("Client Name")
                p_rule = st.text_input("Rule/Report Category")
                new_mapping = {"preset_id": f"PR_{int(time.time())}", "client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    new_mapping[t_col] = st.text_input(f"CSV Header for '{t_col}':")
                
                if st.form_submit_button("Save Rule"):
                    if p_client and p_rule:
                        try:
                            updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                            conn_cloud.update(worksheet="presets", data=updated_presets)
                            st.success("Rule Saved!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving: {e}")

        st.divider()

        # SEARCH & EDIT/DELETE
        search = st.text_input("🔍 Search existing rules:").lower()
        if not presets_db.empty:
            for idx, row in presets_db.iterrows():
                if search in str(row['client_name']).lower() or search in str(row['rule_name']).lower():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 1, 1])
                        c1.write(f"**{row['client_name']}** - {row['rule_name']}")
                        
                        if c3.button("🗑️ Delete", key=f"del_{row['preset_id']}"):
                            conn_cloud.update(worksheet="presets", data=presets_db.drop(idx))
                            st.rerun()
                        
                        with st.expander("✏️ Edit Mapping"):
                            with st.form(key=f"edit_form_{row['preset_id']}"):
                                updated_row = {"preset_id": row['preset_id'], "client_name": row['client_name'], "rule_name": row['rule_name']}
                                for t_col in st.session_state.target_columns:
                                    val = row[t_col] if t_col in row else ""
                                    updated_row[t_col] = st.text_input(f"Header for {t_col}:", value=val)
                                
                                if st.form_submit_button("Update Rule"):
                                    presets_db.iloc[idx] = updated_row
                                    conn_cloud.update(worksheet="presets", data=presets_db)
                                    st.success("Rule Updated!")
                                    st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD (Step 1 - 3) ---
    with main_tab:
        with st.expander("⚙️ Step 1: Configure Target Format"):
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5, 1])
                st.session_state.target_columns[i] = c1.text_input(f"Col {i}", value=col, key=f"edit_{i}")
                if c2.button("🗑️", key=f"del_{i}"): cols_to_remove.append(col)
            
            if cols_to_remove:
                st.session_state.target_columns = [c for c in st.session_state.target_columns if c not in cols_to_remove]
                st.rerun()

            ac1, ac2 = st.columns([5, 1])
            new_col = ac1.text_input("New Column Name:")
            if ac2.button("➕ Add") and new_col:
                st.session_state.target_columns.append(new_col)
                st.rerun()

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
                    
                    sel_rule = st.selectbox("Apply Saved Rule:", preset_options, key=f"rs_{i}")
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    source_cols = df_source.columns.tolist()
                    
                    mapping_dict = {}
                    m_cols = st.columns(3)
                    
                    active_rule = None
                    if sel_rule != "Manual / Smart Match":
                        c_part, r_part = sel_rule.split(" - ", 1)
                        match = rules[(rules['client_name'] == c_part) & (rules['rule_name'] == r_part)]
                        if not match.empty: active_rule = match.iloc[0]

                    for idx, t_col in enumerate(st.session_state.target_columns):
                        default_idx = 0
                        if active_rule is not None and t_col in active_rule:
                            if active_rule[t_col] in source_cols:
                                default_idx = source_cols.index(active_rule[t_col]) + 1
                        
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(f"Map {t_col}", [None] + source_cols, index=default_idx, key=f"m_{file.name}_{t_col}")

                    if st.button(f"Confirm & Save {file.name}", key=f"b_{file.name}"):
                        valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                        if valid_maps:
                            new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                            new_df['batch_id'] = f"ID_{int(time.time())}_{i}"
                            new_df['upload_time'] = get_sydney_time()
                            new_df['file_display_name'] = file.name
                            new_df['uploaded_by'] = st.session_state['current_user']

                            master = conn_cloud.read(worksheet="Sheet1", ttl="0s")
                            updated = pd.concat([master, new_df], ignore_index=True)
                            conn_cloud.update(worksheet="Sheet1", data=updated)
                            st.success("Saved!")
                            time.sleep(1)
                            st.rerun()

        st.divider()
        st.header("📋 Step 3: Manage Cloud Segments")
        try:
            master_data = conn_cloud.read(worksheet="Sheet1", ttl="0s")
            if not master_data.empty:
                unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
                selected_batches = []
                for _, row in unique_imports.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 2])
                        if c1.checkbox("", key=f"sel_{row['batch_id']}"): selected_batches.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}**")
                        if c3.button("🗑️ Delete", key=f"del_seg_{row['batch_id']}"):
                            conn_cloud.update(worksheet="Sheet1", data=master_data[master_data['batch_id'] != row['batch_id']])
                            st.rerun()

                if selected_batches and st.button("📊 Consolidated Report"):
                    st.dataframe(master_data[master_data['batch_id'].isin(selected_batches)], use_container_width=True)
        except: pass

    with archive_tab:
        st.header("📁 Historical Archive")
        st.info("Archive data from Google Sheets will appear here.")
