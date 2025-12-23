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

    # --- TAB 2: MAPPING PRESETS (With Add/Edit/Delete) ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="0s")
        except:
            presets_db = pd.DataFrame(columns=["preset_id", "client_name", "rule_name"] + st.session_state.target_columns)

        # 1. ADD NEW PRESET
        with st.expander("➕ Add New Mapping Rule"):
            with st.form("add_preset_form"):
                p_client = st.text_input("Client Name")
                p_rule = st.text_input("Rule/Report Category")
                new_mapping = {"preset_id": f"PR_{int(time.time())}", "client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    new_mapping[t_col] = st.text_input(f"CSV Header for '{t_col}':")
                
                if st.form_submit_button("Save Rule"):
                    if p_client and p_rule:
                        updated_presets = pd.concat([presets_db, pd.DataFrame([new_mapping])], ignore_index=True)
                        conn_cloud.update(worksheet="presets", data=updated_presets)
                        st.success("Rule Added!")
                        st.rerun()

        st.divider()

        # 2. SEARCH & MANAGE (EDIT/DELETE)
        search = st.text_input("🔍 Search existing rules:", placeholder="Search Client or Rule...").lower()
        
        if not presets_db.empty:
            for idx, row in presets_db.iterrows():
                if search in row['client_name'].lower() or search in row['rule_name'].lower():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 1, 1])
                        c1.write(f"**{row['client_name']}** - {row['rule_name']}")
                        
                        # DELETE button
                        if c3.button("🗑️ Delete", key=f"del_{row['preset_id']}"):
                            updated_presets = presets_db.drop(idx)
                            conn_cloud.update(worksheet="presets", data=updated_presets)
                            st.rerun()
                        
                        # EDIT expander
                        with st.expander("✏️ Edit Mapping"):
                            with st.form(key=f"edit_form_{row['preset_id']}"):
                                updated_row = {"preset_id": row['preset_id'], "client_name": row['client_name'], "rule_name": row['rule_name']}
                                st.write("Update Source Column Headers:")
                                for t_col in st.session_state.target_columns:
                                    updated_row[t_col] = st.text_input(f"Header for {t_col}:", value=row[t_col])
                                
                                if st.form_submit_button("Update Rule"):
                                    presets_db.iloc[idx] = updated_row
                                    conn_cloud.update(worksheet="presets", data=presets_db)
                                    st.success("Rule Updated!")
                                    st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        # Step 1: Format
        with st.expander("⚙️ Step 1: Configure Target Format"):
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5, 1])
                st.session_state.target_columns[i] = c1.text_input(f"Col {i+1}", value=col, key=f"e_col_{i}")
                if c2.button("🗑️", key=f"d_col_{i}"): cols_to_remove.append(col)
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
                    
                    # Apply Preset Logic
                    active_rule = None
                    if sel_rule_full != "Manual / Smart Match":
                        c_part, r_part = sel_rule_full.split(" - ", 1)
                        match = rules[(rules['client_name'] == c_part) & (rules['rule_
