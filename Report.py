import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import os

# --- 1. Password Protection ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "admin123": # <--- CHANGE PASSWORD HERE
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    return True

if check_password():
    # --- 2. Initialize GSheets Connection ---
    # This replaces the SQLite DB_NAME and init_db()
    conn = st.connection("gsheets", type=GSheetsConnection)

    st.set_page_config(page_title="Cloud Report Consolidator", layout="wide")
    st.title("☁️ Cloud Inventory Consolidator (Google Sheets)")

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
            if new_name: st.session_state.target_columns.append(new_name); st.rerun()

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
                        # Process new data
                        new_df = df_source[list(valid_maps.keys())].rename(columns=valid_maps)
                        batch_id = f"ID_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_df['batch_id'], new_df['upload_time'] = batch_id, now
                        new_df['file_display_name'] = d_name # Store for segmenting later

                        # Fetch existing data from Google Sheets
                        try:
                            existing_data = conn.read(ttl=0) # ttl=0 ensures we get fresh data
                            # Combine with existing
                            updated_df = pd.concat([existing_data, new_df], ignore_index=True, sort=False)
                        except:
                            # If sheet is empty
                            updated_df = new_df
                        
                        # Update Google Sheets
                        conn.update(data=updated_df)
                        st.success(f"Successfully saved {d_name} to Google Sheets!")
                        st.rerun()
                    else:
                        st.warning("Please map at least one column.")

    st.divider()

    # --- STEP 3: SEGMENTED VIEW (FROM GSHEETS) ---
    st.header("📋 Step 3: Manage Segments from Cloud")
    try:
        # Read the master data from Google Sheets
        master_data = conn.read(ttl=0)
        
        if not master_data.empty and 'batch_id' in master_data.columns:
            # Get unique imports based on batch_id
            unique_imports = master_data[['batch_id', 'file_display_name', 'upload_time']].drop_duplicates()
            
            selected_batches = []
            st.subheader("Select Reports to Combine")
            
            for _, row in unique_imports.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 4, 2])
                    
                    is_selected = c1.checkbox("", key=f"sel_{row['batch_id']}")
                    if is_selected: selected_batches.append(row['batch_id'])
                    
                    c2.write(f"**{row['file_display_name']}**")
                    c2.caption(f"Imported: {row['upload_time']} | ID: {row['batch_id']}")
                    
                    # Filter data for this specific segment
                    seg_df = master_data[master_data['batch_id'] == row['batch_id']]
                    clean_seg = seg_df[[c for c in st.session_state.target_columns if c in seg_df.columns]]
                    
                    csv_data = clean_seg.to_csv(index=False).encode('utf-8')
                    c3.download_button("📥 Download", data=csv_data, file_name=f"{row['file_display_name']}.csv", key=f"dl_{row['batch_id']}")
                    
                    if c3.button("🗑️ Delete from Cloud", key=f"del_{row['batch_id']}"):
                        # Remove this batch from the master dataframe
                        remaining_data = master_data[master_data['batch_id'] != row['batch_id']]
                        conn.update(data=remaining_data)
                        st.success("Deleted from Cloud!")
                        st.rerun()

            st.divider()
            # --- COMBINE SECTION ---
            st.subheader("🔗 Combined Cloud Export")
            if selected_batches:
                if st.button("Generate Combined Report"):
                    combined_df = master_data[master_data['batch_id'].isin(selected_batches)]
                    final_cols = [c for c in st.session_state.target_columns if c in combined_df.columns]
                    display_df = combined_df[final_cols]
                    st.dataframe(display_df)
                    csv_comb = display_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Combined Report", data=csv_comb, file_name="combined_cloud_report.csv")
        else:
            st.info("No data found in Google Sheets.")
    except Exception as e:
        st.error(f"Waiting for data or Error: {e}")

    st.divider()

    # --- STEP 4: HARD RESET ---
    if st.button("🔥 WIPE ALL GOOGLE SHEET DATA"):
        # We update with an empty dataframe containing only our tracking columns
        empty_df = pd.DataFrame(columns=st.session_state.target_columns + ['batch_id', 'upload_time', 'file_display_name'])
        conn.update(data=empty_df)
        st.success("Cloud data wiped!")
        st.rerun()
