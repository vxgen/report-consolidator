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
                else: st.error("Access Denied or Pending Approval.")
            except: st.error("Connection error with Cloud.")
    return False

if check_password():
    conn_cloud = st.connection("gsheets", type=GSheetsConnection)
    
    # Initialize Global Session State for columns
    if 'target_columns' not in st.session_state:
        st.session_state.target_columns = ["Category", "SKU", "Product Name", "Product Description", "Stock on Hand", "Sold QTY"]
    
    st.title("☁️ Cloud Inventory Consolidator")
    main_tab, preset_tab, archive_tab = st.tabs(["🚀 Active Dashboard", "🗺️ Mapping Presets", "📁 Historical Archive"])

    # --- TAB 2: MAPPING PRESETS ---
    with preset_tab:
        st.header("🗺️ Manage Mapping Presets")
        st.info("Define rules for specific clients or report types. These will appear in Step 2 for quick mapping.")
        
        try:
            presets_db = conn_cloud.read(worksheet="presets", ttl="5s")
        except:
            presets_db = pd.DataFrame(columns=["client_name", "rule_name"] + st.session_state.target_columns)

        with st.expander("➕ Create New Mapping Rule"):
            with st.form("new_rule_form"):
                p_client = st.text_input("Client Name (e.g., Umart)")
                p_rule = st.text_input("Rule/Report Name (e.g., Laptop Category)")
                st.markdown("---")
                st.write("Enter the **Exact Header Name** from the client's CSV file for each field:")
                
                new_mapping = {"client_name": p_client, "rule_name": p_rule}
                for t_col in st.session_state.target_columns:
                    new_mapping[t_col] = st.text_input(f"CSV Header for '{t_col}':", key=f"pre_{t_col}")
                
                if st.form_submit_button("Save Mapping Rule"):
                    if p_client and p_rule:
                        new_entry = pd.DataFrame([new_mapping])
                        updated_presets = pd.concat([presets_db, new_entry], ignore_index=True)
                        conn_cloud.update(worksheet="presets", data=updated_presets)
                        st.cache_data.clear()
                        st.success(f"Rule '{p_rule}' for {p_client} saved successfully!")
                        time.sleep(1)
                        st.rerun()
                    else: st.error("Please provide both Client and Rule names.")

        if not presets_db.empty:
            st.subheader("Current Saved Rules")
            st.dataframe(presets_db, use_container_width=True)
            if st.button("🗑️ Clear All Rules"):
                conn_cloud.update(worksheet="presets", data=pd.DataFrame(columns=presets_db.columns))
                st.rerun()

    # --- TAB 1: ACTIVE DASHBOARD ---
    with main_tab:
        # Step 1: Format Configuration
        with st.expander("⚙️ Step 1: Configure Target Format"):
            cols_to_remove = []
            for i, col in enumerate(st.session_state.target_columns):
                c1, c2 = st.columns([5, 1])
                st.session_state.target_columns[i] = c1.text_input(f"Column {i+1}", value=col, key=f"edit_col_{i}")
                if c2.button("🗑️", key=f"del_col_{i}"): cols_to_remove.append(col)
            for col in cols_to_remove: 
                st.session_state.target_columns.remove(col)
                st.rerun()
            st.markdown("---")
            nc1, nc2 = st.columns([5, 1])
            new_col = nc1.text_input("New Column Name:", key="new_col_input")
            if nc2.button("➕ Add"):
                if new_col:
                    st.session_state.target_columns.append(new_col)
                    st.rerun()

        # Step 2: Upload & Map
        st.header("📤 Step 2: Upload & Map")
        uploaded_files = st.file_uploader("Upload Files", type=["csv", "xlsx"], accept_multiple_files=True)
        
        if uploaded_files:
            try: active_cache = conn_cloud.read(worksheet="Sheet1", ttl="5s")
            except: active_cache = pd.DataFrame()
            
            # Load Presets for the dropdown
            try: rules = conn_cloud.read(worksheet="presets", ttl="5s")
            except: rules = pd.DataFrame()

            for i, file in enumerate(uploaded_files):
                with st.container(border=True):
                    st.subheader(f"📄 {file.name}")
                    
                    # PRESET DROPDOWN
                    preset_options = ["Manual Mapping"]
                    if not rules.empty:
                        preset_options += (rules['client_name'] + " - " + rules['rule_name']).tolist()
                    
                    sel_rule_full = st.selectbox("Apply Saved Rule:", preset_options, key=f"rule_sel_{i}")
                    
                    df_source = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                    mapping_dict = {}
                    m_cols = st.columns(3)
                    
                    # Logic to find preset row
                    active_rule = None
                    if sel_rule_full != "Manual Mapping":
                        c_name, r_name = sel_rule_full.split(" - ")
                        active_rule = rules[(rules['client_name'] == c_name) & (rules['rule_name'] == r_name)].iloc[0]

                    for idx, t_col in enumerate(st.session_state.target_columns):
                        default_idx = 0
                        # If preset exists, find index of the mapped header in the current file
                        if active_rule is not None and t_col in active_rule:
                            target_header = active_rule[t_col]
                            if target_header in df_source.columns:
                                default_idx = df_source.columns.tolist().index(target_header) + 1
                        
                        mapping_dict[t_col] = m_cols[idx % 3].selectbox(
                            f"Map {t_col}", 
                            [None] + df_source.columns.tolist(), 
                            index=default_idx,
                            key=f"m_{file.name}_{t_col}"
                        )

                    if st.button(f"Confirm & Save {file.name}", key=f"b_{file.name}"):
                        valid_maps = {v: k for k, v in mapping_dict.items() if v is not None}
                        if valid_maps:
                            new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                            new_df['batch_id'] = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                            new_df['upload_time'] = get_sydney_time()
                            new_df['file_display_name'] = file.name
                            new_df['uploaded_by'] = st.session_state['current_user']

                            updated_df = pd.concat([active_cache, new_df], ignore_index=True, sort=False)
                            conn_cloud.update(worksheet="Sheet1", data=updated_df)
                            st.cache_data.clear()
                            st.success("Successfully Saved to Cloud!")
                            time.sleep(1)
                            st.rerun()

        st.divider()
        # Step 3: Manage Cloud Segments
        st.header("📋 Step 3: Manage Cloud Segments")
        try:
            master_data = conn_cloud.read(worksheet="Sheet1", ttl="10s")
            if not master_data.empty and 'batch_id' in master_data.columns:
                unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
                selected_batches = []
                for _, row in unique_imports.iterrows():
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([0.5, 4, 2])
                        if c1.checkbox("", key=f"sel_{row['batch_id']}"): selected_batches.append(row['batch_id'])
                        c2.write(f"**{row['file_display_name']}**")
                        c2.caption(f"Uploaded: {row['upload_time']}")
                        
                        if c3.button("🗑️ Delete", key=f"del_{row['batch_id']}"):
                            remaining = master_data[master_data['batch_id'] != row['batch_id']]
                            conn_cloud.update(worksheet="Sheet1", data=remaining)
                            st.cache_data.clear()
                            st.rerun()
                        
                        with st.expander("👁️ View & Download"):
                            ind_df = master_data[master_data['batch_id'] == row['batch_id']]
                            st.dataframe(ind_df, use_container_width=True)
                            st.download_button("📥 Download", ind_df.to_csv(index=False), f"{row['file_display_name']}.csv")

                if selected_batches:
                    st.markdown("---")
                    if st.button("📊 Generate Consolidated Report"):
                        combined = master_data[master_data['batch_id'].isin(selected_batches)]
                        st.subheader("🔗 Consolidated Preview")
                        st.dataframe(combined, use_container_width=True)
                        st.download_button("📥 Download Full CSV", combined.to_csv(index=False), "final_report.csv")
            else: st.info("No active segments.")
        except: pass

    with archive_tab:
        st.header("📁 Historical Archive")
        try:
            archived_df = conn_cloud.read(worksheet="archive", ttl="10s")
            if not archived_df.empty:
                st.dataframe(archived_df, use_container_width=True)
                if st.button("🧹 Clear Archive"):
                    conn_cloud.update(worksheet="archive", data=pd.DataFrame(columns=archived_df.columns))
                    st.rerun()
        except: st.error("Ensure 'archive' worksheet exists.")
