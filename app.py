import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import uuid

# =============================================================================
# 1. CẤU HÌNH HỆ THỐNG & SCHEMA (CONFIG & SCHEMA)
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường Học",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/3209/3209265.png" # Placeholder logo

# Định nghĩa Schema chuẩn. Hàm load_data sẽ dựa vào đây để fix cột thiếu.
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'Periods': ['TenDot', 'TrangThai'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV', 'DiemHaiLong_PH', 'NhanXet_PH'],
    'FinalReviews': ['Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH', 'TrangThai_CuoiKy']
}

if 'user' not in st.session_state:
    st.session_state.user = None

# =============================================================================
# 2. DATA LAYER (AUTO-SCHEMA MIGRATION & CACHING)
# =============================================================================

def get_client():
    """Kết nối Google API an toàn"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🔴 Lỗi kết nối API: {e}")
        return None

@st.cache_data(ttl=10)
def load_data(sheet_name):
    """
    Load data và TỰ ĐỘNG THÊM CỘT nếu thiếu (Schema Migration).
    """
    client = get_client()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # Init sheet mới
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA[sheet_name])
            return pd.DataFrame(columns=SCHEMA[sheet_name])

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- AUTO MIGRATION LOGIC ---
        expected_cols = SCHEMA[sheet_name]
        
        # Nếu DF rỗng (chỉ có header hoặc sheet trắng)
        if df.empty:
            return pd.DataFrame(columns=expected_cols)

        # Kiểm tra và fill cột thiếu
        for col in expected_cols:
            if col not in df.columns:
                # Default values
                val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH'] else ""
                df[col] = val
        
        # Reorder columns & Drop extra columns (Optional: Keep extra if needed)
        # Ở đây ta giữ lại cột thừa để an toàn, nhưng ưu tiên thứ tự chuẩn
        cols_in_df = [c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]
        df = df[cols_in_df]

        # --- TYPE CASTING ---
        if sheet_name == 'Users':
            df['SiSo'] = pd.to_numeric(df['SiSo'], errors='coerce').fillna(0).astype(int)
            df['Password'] = df['Password'].astype(str)
        if sheet_name == 'OKRs':
            for c in ['MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
        
        return df
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu {sheet_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def save_df(sheet_name, df):
    """Lưu DataFrame (Ghi đè - Dùng cho Edit/Delete)"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")
        return False

def append_row(sheet_name, row_data):
    """Thêm dòng mới (Append - Dùng cho Create)"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        # Convert types for JSON safety
        safe_row = []
        for x in row_data:
            if isinstance(x, (int, float)): safe_row.append(x)
            elif x is None: safe_row.append("")
            else: safe_row.append(str(x))
        
        ws.append_row(safe_row, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi thêm dữ liệu: {e}")
        return False

def batch_append(sheet_name, list_data):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.append_rows(list_data, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi import: {e}")
        return False

# =============================================================================
# 3. SIDEBAR & GLOBAL CONTROLLER
# =============================================================================

def sidebar_controller():
    with st.sidebar:
        st.image(LOGO_URL, width=80)
        st.markdown("### SCHOOL OKR")
        
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            
            # --- GLOBAL FILTER: PERIOD ---
            st.divider()
            st.markdown("📅 **CHỌN ĐỢT ĐÁNH GIÁ**")
            df_p = load_data('Periods')
            p_opts = df_p['TenDot'].tolist() if not df_p.empty else []
            
            if not p_opts:
                return None, False
            
            # Default to first "Mở" period
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts:
                idx = p_opts.index(opens[0])
            
            sel_period = st.selectbox("Đợt:", p_opts, index=idx, label_visibility="collapsed")
            status = df_p[df_p['TenDot'] == sel_period].iloc[0]['TrangThai']
            is_open = (status == 'Mở')
            
            if is_open: st.success(f"Trạng thái: {status} 🟢")
            else: st.error(f"Trạng thái: {status} 🔒")
            
            # --- CHANGE PASSWORD ---
            with st.expander("🔑 Đổi mật khẩu"):
                with st.form("chg_pass"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        df_u = load_data('Users')
                        # Find index
                        if u['Role'] == 'PhuHuynh':
                            # PH ko đổi pass (dùng pass con), hoặc logic riêng.
                            # Ở đây giả sử PH dùng pass của con -> Đổi pass con.
                            target_email = u['ChildEmail']
                        else:
                            target_email = u['Email']
                        
                        mask = df_u['Email'] == target_email
                        if mask.any():
                            df_u.loc[mask, 'Password'] = np
                            save_df('Users', df_u)
                            st.success("Đổi thành công!")
                        else: st.error("Lỗi tìm user.")

            st.divider()
            if st.button("Đăng xuất", use_container_width=True):
                st.session_state.user = None
                st.rerun()
            
            return sel_period, is_open
    return None, False

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏫 CỔNG ĐĂNG NHẬP</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                # Bypass Admin
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()

                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu User.")
                    return
                
                # Check Normal Users
                match = df[(df['Email'] == email) & (df['Password'] == password)]
                if not match.empty:
                    st.session_state.user = match.iloc[0].to_dict()
                    st.rerun()
                
                # Check Parent (Login by EmailPH)
                # Logic: Find row where EmailPH matches input AND Password matches student password
                ph_match = df[(df['EmailPH'] == email) & (df['Password'] == password)]
                if not ph_match.empty:
                    child = ph_match.iloc[0]
                    st.session_state.user = {
                        'Email': email, 'Role': 'PhuHuynh',
                        'HoTen': f"PH em {child['HoTen']}",
                        'ChildEmail': child['Email'], 'ChildName': child['HoTen']
                    }
                    st.rerun()
                
                st.error("Sai thông tin đăng nhập.")

# =============================================================================
# 4. MODULES (ROLES)
# =============================================================================

# --- A. ADMIN ---
def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2 = st.tabs(["📊 Thống Kê & Lớp", "👨‍🏫 Quản lý Giáo Viên"])
    
    with t1:
        st.subheader(f"Thống kê chi tiết Đợt: {period}")
        df_users = load_data('Users')
        df_okr = load_data('OKRs')
        df_rev = load_data('FinalReviews')
        
        # Filter by Period
        df_okr_p = df_okr[df_okr['Dot'] == period]
        df_rev_p = df_rev[df_rev['Dot'] == period]
        
        # Get Classes (Unique from Users where Role=HocSinh)
        classes = df_users[df_users['Role'] == 'HocSinh']['Lop'].unique()
        
        stats_data = []
        for cls in classes:
            hs_in_class = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == cls)]
            siso_thuc = len(hs_in_class)
            
            # Get SiSo from GV of this class (Optional, but per requirement)
            gv_of_class = df_users[(df_users['Role'] == 'GiaoVien') & (df_users['Lop'] == cls)]
            siso_dk = int(gv_of_class.iloc[0]['SiSo']) if not gv_of_class.empty else 0
            
            # Count OKR submitted (Unique Emails in OKRs table for this class)
            hs_emails = hs_in_class['Email'].tolist()
            okr_submitted = df_okr_p[df_okr_p['Email'].isin(hs_emails)]['Email'].nunique()
            
            # Count OKR Approved (All OKRs of a student must be approved? Or just has approved OKRs?)
            # Simplest: Count students who have at least one Approved OKR
            okr_approved = df_okr_p[(df_okr_p['Email'].isin(hs_emails)) & (df_okr_p['TrangThai'] == 'Đã duyệt')]['Email'].nunique()
            
            # Count Final Reviews
            reviews_done = df_rev_p[(df_rev_p['Email'].isin(hs_emails)) & (df_rev_p['TrangThai_CuoiKy'] != '')]['Email'].nunique()
            
            stats_data.append({
                "Lớp": cls,
                "Sĩ Số (GV khai)": siso_dk,
                "Sĩ Số (App)": siso_thuc,
                "Đã Nộp OKR": okr_submitted,
                "Đã Duyệt": okr_approved,
                "Đã Đánh Giá CK": reviews_done
            })
            
        st.dataframe(pd.DataFrame(stats_data), use_container_width=True)

    with t2:
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
        with c2:
            st.markdown("#### Thêm GV")
            with st.form("add_gv"):
                e = st.text_input("Email")
                n = st.text_input("Họ tên")
                l = st.text_input("Lớp")
                s = st.number_input("Sĩ số", min_value=0)
                if st.form_submit_button("Thêm"):
                    if e not in df_users['Email'].values:
                        append_row('Users', [e, "123", "GiaoVien", n, l, "", s])
                        st.success("Đã thêm!")
                        st.rerun()
                    else: st.error("Email trùng.")
            
            with st.expander("Import Excel"):
                f = st.file_uploader("File XLSX", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            rows.append([str(r['Email']), "123", "GiaoVien", str(r['HoTen']), str(r['Lop']), "", int(r['SiSo'])])
                    batch_append('Users', rows)
                    st.success("Xong!")
                    st.rerun()

# --- B. TEACHER (COMMAND CENTER) ---
def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    st.title(f"👩‍🏫 GVCN Lớp {my_class}")
    
    if not my_class:
        st.error("Tài khoản chưa có lớp.")
        return

    # Load Data Scope
    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    df_okr = load_data('OKRs')
    # Filter OKR by Class & Period
    df_okr_p = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    df_rev = load_data('FinalReviews')
    df_rev_p = df_rev[(df_rev['Dot'] == period)]

    st.markdown("### 📋 DANH SÁCH HỌC SINH")
    
    # Render Student Rows (Command Center Style)
    for i, hs in df_hs.iterrows():
        email_hs = hs['Email']
        hs_name = hs['HoTen']
        
        # Determine Statuses
        okrs_of_hs = df_okr_p[df_okr_p['Email'] == email_hs]
        rev_of_hs = df_rev_p[df_rev_p['Email'] == email_hs]
        
        # 1. OKR Status
        if okrs_of_hs.empty:
            okr_badge = "🔴 Chưa tạo"
            okr_color = "error" # Red
        else:
            if (okrs_of_hs['TrangThai'] == 'Đã duyệt').all():
                okr_badge = "🟢 Đã duyệt"
                okr_color = "success"
            elif (okrs_of_hs['TrangThai'] == 'Cần sửa').any():
                okr_badge = "🟠 Cần sửa"
                okr_color = "warning"
            else:
                okr_badge = "🟡 Chờ duyệt"
                okr_color = "secondary" # Grey/Yellowish
        
        # 2. Review Status
        is_reviewed = False
        if not rev_of_hs.empty and rev_of_hs.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
            rev_badge = "✅ Đã chốt"
            is_reviewed = True
        else:
            rev_badge = "⏳ Chưa chốt"

        # UI Row
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1])
            c1.markdown(f"**{hs_name}**\n<span style='font-size:0.8em;color:gray'>{email_hs}</span>", unsafe_allow_html=True)
            
            # Button/Badge 1: OKR
            c2.markdown(f":{okr_color}[**{okr_badge}**]")
            
            # Button/Badge 2: Review
            c3.write(rev_badge)
            
            # Button 3: Expand
            with c4:
                # Expander acts as the "Detail" button
                pass 
            
            # Detail Section (Inside Expander)
            with st.expander(f"🔽 Chi tiết & Thao tác: {hs_name}"):
                t1, t2 = st.tabs(["🎯 Duyệt OKR", "📝 Đánh giá Cuối kỳ"])
                
                # --- TAB 1: DUYỆT OKR ---
                with t1:
                    if okrs_of_hs.empty:
                        st.info("HS chưa nộp OKR.")
                    else:
                        # GROUP BY OBJECTIVE
                        objectives = okrs_of_hs['MucTieu'].unique()
                        for obj in objectives:
                            st.markdown(f"**Mục tiêu:** {obj}")
                            krs = okrs_of_hs[okrs_of_hs['MucTieu'] == obj]
                            
                            # Show KRs in a table-like format
                            for _, kr in krs.iterrows():
                                kc1, kc2, kc3 = st.columns([4, 2, 2])
                                kc1.text(f"- KR: {kr['KetQuaThenChot']} ({kr['MucTieuSo']} {kr['DonVi']})")
                                kc2.caption(f"Đạt: {kr['ThucDat']} ({kr['TienDo']}%)")
                                
                                # Individual KR Action (Optional, or bulk below)
                                if kr['YeuCauXoa'] == 'TRUE':
                                    kc3.warning("Xin xóa!")
                                    if is_open and kc3.button("Đồng ý xóa", key=f"del_{kr['ID']}"):
                                        idx = df_okr[df_okr['ID'] == kr['ID']].index[0]
                                        df_okr.drop(idx, inplace=True)
                                        save_df('OKRs', df_okr)
                                        st.rerun()

                        st.divider()
                        # BULK ACTION
                        with st.form(f"approve_{email_hs}"):
                            cmt = st.text_input("Nhận xét GV:", value=str(okrs_of_hs.iloc[0]['NhanXet_GV']), disabled=not is_open)
                            act = st.selectbox("Hành động:", ["Giữ nguyên", "Duyệt tất cả", "Yêu cầu sửa"], disabled=not is_open)
                            if st.form_submit_button("Lưu trạng thái"):
                                if is_open:
                                    indices = df_okr[df_okr['ID'].isin(okrs_of_hs['ID'])].index
                                    if act == "Duyệt tất cả":
                                        df_okr.loc[indices, 'TrangThai'] = 'Đã duyệt'
                                    elif act == "Yêu cầu sửa":
                                        df_okr.loc[indices, 'TrangThai'] = 'Cần sửa'
                                    
                                    df_okr.loc[indices, 'NhanXet_GV'] = cmt
                                    save_df('OKRs', df_okr)
                                    st.success("Đã lưu!")
                                    st.rerun()
                
                # --- TAB 2: ĐÁNH GIÁ CUỐI KỲ ---
                with t2:
                    curr_rev_txt = rev_of_hs.iloc[0]['NhanXet_CuoiKy'] if not rev_of_hs.empty else ""
                    ph_feedback = rev_of_hs.iloc[0]['PhanHoi_PH'] if not rev_of_hs.empty else "Chưa có phản hồi."
                    st.info(f"👨‍👩‍👧‍👦 Phản hồi PH: {ph_feedback}")
                    
                    with st.form(f"rev_{email_hs}"):
                        rv_txt = st.text_area("Nhận xét tổng kết:", value=curr_rev_txt, disabled=not is_open)
                        finalize = st.checkbox("Chốt đánh giá (Khóa sửa)?", value=is_reviewed, disabled=not is_open)
                        
                        if st.form_submit_button("Lưu đánh giá"):
                            if is_open:
                                stt_val = "Đã chốt" if finalize else "Chưa chốt"
                                if rev_of_hs.empty:
                                    # Create
                                    append_row('FinalReviews', [email_hs, period, rv_txt, "", stt_val])
                                else:
                                    # Update
                                    ridx = df_rev[df_rev.index.isin(rev_of_hs.index)].index[0]
                                    df_rev.at[ridx, 'NhanXet_CuoiKy'] = rv_txt
                                    df_rev.at[ridx, 'TrangThai_CuoiKy'] = stt_val
                                    save_df('FinalReviews', df_rev)
                                st.success("Đã lưu!")
                                st.rerun()

# --- C. STUDENT ---
def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    
    # 1. CREATE FORM (1-N Logic Simplified)
    # Streamlit doesn't support dynamic form fields easily.
    # Logic: User Selects/Types Objective -> Adds a KR to it.
    if is_open:
        with st.expander("➕ Thêm KR mới", expanded=my_okrs.empty):
            with st.form("add_kr"):
                # Get existing objectives to suggest
                existing_objs = my_okrs['MucTieu'].unique().tolist()
                
                # Helper to combine select/text for "New or Existing Objective"
                obj_input = st.text_input("Mục tiêu (Objective) - VD: Học tập tốt", placeholder="Nhập mục tiêu lớn...")
                
                c1, c2, c3 = st.columns(3)
                kr_in = c1.text_input("Tên KR (Key Result)")
                tgt_in = c2.number_input("Mục tiêu số (Target)", min_value=0.0, step=1.0)
                unit_in = c3.text_input("Đơn vị (VD: Điểm, Quyển)")
                
                if st.form_submit_button("Thêm KR"):
                    if obj_input and kr_in:
                        uid = uuid.uuid4().hex[:8]
                        # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai...
                        row = [uid, user['Email'], user['Lop'], period, obj_input, kr_in, tgt_in, 0.0, unit_in, 0.0, "Chờ duyệt", "FALSE", "", 0, ""]
                        append_row('OKRs', row)
                        st.success("Đã thêm KR!")
                        st.rerun()
                    else:
                        st.warning("Vui lòng nhập Mục tiêu và KR.")

    # 2. LIST & UPDATE
    st.subheader("Tiến độ của em")
    if my_okrs.empty:
        st.info("Chưa có OKR nào.")
    else:
        # Group by Objective for display
        objs = my_okrs['MucTieu'].unique()
        for obj in objs:
            with st.container(border=True):
                st.markdown(f"### 🎯 {obj}")
                krs = my_okrs[my_okrs['MucTieu'] == obj]
                
                for _, row in krs.iterrows():
                    stt_color = "green" if row['TrangThai'] == 'Đã duyệt' else "orange"
                    st.markdown(f"**KR: {row['KetQuaThenChot']}** <span style='color:{stt_color}'>({row['TrangThai']})</span>", unsafe_allow_html=True)
                    
                    # Update Progress Form
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.caption(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                    
                    cur_act = float(row['ThucDat'])
                    
                    # Edit Logic
                    if is_open and row['TrangThai'] == 'Đã duyệt':
                        new_act = c2.number_input(f"Thực đạt ##{row['ID']}", value=cur_act, label_visibility="collapsed")
                        
                        # Calculate %
                        prog = 0.0
                        if row['MucTieuSo'] > 0:
                            prog = min((new_act / row['MucTieuSo']) * 100, 100.0)
                        
                        c2.progress(int(prog))
                        c2.caption(f"{prog:.1f}%")

                        if c3.button("Lưu", key=f"up_{row['ID']}"):
                            idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                            df_okr.at[idx, 'ThucDat'] = new_act
                            df_okr.at[idx, 'TienDo'] = prog
                            save_df('OKRs', df_okr)
                            st.success("Updated!")
                            st.rerun()
                    else:
                        c2.progress(int(row['TienDo']))
                        c2.caption(f"Đạt: {cur_act} ({row['TienDo']}%)")
                        if row['TrangThai'] != 'Đã duyệt':
                            c3.info("Chờ duyệt")
                    
                    # Feedback Display
                    if row['DiemHaiLong_PH'] > 0:
                        st.caption(f"⭐ PH đánh giá: {row['DiemHaiLong_PH']}/5 - {row['NhanXet_PH']}")
                    
                    st.divider()

# --- D. PARENT ---
def parent_view(period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 Phụ huynh em: {user['ChildName']}")
    
    df_okr = load_data('OKRs')
    # Filter by Child Email
    child_okrs = df_okr[(df_okr['Email'] == user['ChildEmail']) & (df_okr['Dot'] == period)]
    
    st.subheader("Đánh giá OKR của con")
    if child_okrs.empty:
        st.write("Chưa có dữ liệu.")
    else:
        # Group by Objective
        objs = child_okrs['MucTieu'].unique()
        for obj in objs:
            st.markdown(f"#### 🎯 {obj}")
            krs = child_okrs[child_okrs['MucTieu'] == obj]
            
            for _, r in krs.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    c1.write(f"**KR:** {r['KetQuaThenChot']}")
                    c1.caption(f"Tiến độ: {r['TienDo']}% (Đạt {r['ThucDat']}/{r['MucTieuSo']})")
                    
                    # Rating Form
                    with c2:
                        val_star = int(r['DiemHaiLong_PH']) if r['DiemHaiLong_PH'] > 0 else 3
                        stars = st.slider(f"Mức hài lòng ({r['ID']})", 1, 5, val_star)
                        cmt_ph = st.text_input(f"Nhận xét ({r['ID']})", value=str(r['NhanXet_PH']))
                        
                        if st.button("Gửi đánh giá", key=f"rate_{r['ID']}"):
                            idx = df_okr[df_okr['ID'] == r['ID']].index[0]
                            df_okr.at[idx, 'DiemHaiLong_PH'] = stars
                            df_okr.at[idx, 'NhanXet_PH'] = cmt_ph
                            save_df('OKRs', df_okr)
                            st.success("Đã gửi!")
                            st.rerun()

# =============================================================================
# 5. MAIN EXECUTION
# =============================================================================

def main():
    if not st.session_state.user:
        login_ui()
    else:
        period, is_open = sidebar_controller()
        if not period:
            st.warning("Vui lòng liên hệ Admin để tạo Đợt đánh giá đầu tiên.")
            return

        role = st.session_state.user['Role']
        
        if role == 'Admin':
            admin_view(period, is_open)
        elif role == 'GiaoVien':
            teacher_view(period, is_open)
        elif role == 'HocSinh':
            student_view(period, is_open)
        elif role == 'PhuHuynh':
            parent_view(period, is_open)
        else:
            st.error("Role không hợp lệ.")

if __name__ == "__main__":
    main()
