import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import time
import uuid

# =============================================================================
# 1. CẤU HÌNH HỆ THỐNG & KẾT NỐI
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường Học",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ID Google Sheet Cố Định
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"

# Master Key
MASTER_EMAIL = "admin@school.com"
MASTER_PASS = "123"

# Định nghĩa cấu trúc chuẩn (Để mapping dữ liệu chính xác)
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'TargetValue', 'ActualValue', 'Unit', 'TienDo', 'TrangThai', 
             'DeleteRequest', 'NhanXet_GV_L1', 'NhanXet_GV_L2'],
    'Reviews': ['Email', 'Dot', 'GV_General_Comment', 'PH_Comment'],
    'Settings': ['Key', 'Value']
}

if 'user' not in st.session_state:
    st.session_state.user = None

# -----------------------------------------------------------------------------
# XỬ LÝ KẾT NỐI GOOGLE SHEETS
# -----------------------------------------------------------------------------

def get_gspread_client():
    """Kết nối Google Sheets với Error Handling chi tiết"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Lấy credentials từ secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"🔴 LỖI KẾT NỐI API: {str(e)}")
        return None

@st.cache_data(ttl=30) # Giảm TTL xuống 30s để cập nhật nhanh hơn
def load_data(sheet_name):
    """Đọc dữ liệu từ Sheet"""
    client = get_gspread_client()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # Tự tạo sheet nếu chưa có
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA.get(sheet_name, []))
            return pd.DataFrame(columns=SCHEMA.get(sheet_name, []))

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- FIX SCHEMA: Tự động thêm cột thiếu ---
        expected_cols = SCHEMA.get(sheet_name, [])
        if expected_cols:
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = "" if col not in ['TargetValue', 'ActualValue', 'TienDo', 'SiSo'] else 0
            # Sắp xếp lại cột cho đúng thứ tự chuẩn
            # Lọc các cột có trong dữ liệu khớp với schema
            existing_cols = [c for c in expected_cols if c in df.columns]
            df = df[existing_cols]

        # --- FIX DATA TYPES: Chuyển đổi kiểu số để tránh lỗi tính toán ---
        if sheet_name == 'Users':
            df['Password'] = df['Password'].astype(str)
            df['Lop'] = df['Lop'].astype(str)
        
        if sheet_name == 'OKRs' and not df.empty:
            for col in ['TargetValue', 'ActualValue', 'TienDo']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            df['Lop'] = df['Lop'].astype(str) # Quan trọng cho việc lọc

        return df
    except Exception as e:
        st.error(f"🔴 Lỗi tải dữ liệu sheet '{sheet_name}': {e}")
        return pd.DataFrame()

def clear_cache():
    """Xóa cache để tải lại dữ liệu mới nhất"""
    st.cache_data.clear()

def append_data_safe(sheet_name, row_data):
    """
    Hàm thêm dữ liệu an toàn.
    Chuyển đổi toàn bộ dữ liệu sang string hoặc float chuẩn Python.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        
        # Chuẩn hóa dữ liệu trước khi gửi (Tránh lỗi JSON của NumPy types)
        clean_row = []
        for item in row_data:
            if isinstance(item, (int, float)):
                clean_row.append(item) # Giữ nguyên số
            elif item is None:
                clean_row.append("")
            else:
                clean_row.append(str(item)) # Ép kiểu chuỗi

        # Ghi dữ liệu
        ws.append_row(clean_row, value_input_option='USER_ENTERED')
        clear_cache() # Xóa cache ngay lập tức
        return True
    except Exception as e:
        st.error(f"🔴 KHÔNG LƯU ĐƯỢC DỮ LIỆU: {str(e)}")
        return False

def save_dataframe(sheet_name, df):
    """Lưu toàn bộ DataFrame (Dùng cho Sửa/Xóa)"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.clear()
        # Update header & data
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"🔴 Lỗi lưu bảng: {e}")
        return False

def batch_append_data(sheet_name, data_list):
    """Import nhiều dòng"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.append_rows(data_list, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"🔴 Lỗi import batch: {e}")
        return False

# =============================================================================
# 2. LOGIC NGHIỆP VỤ
# =============================================================================

def get_current_dot():
    df = load_data('Settings')
    if df.empty: return "HocKy1"
    row = df[df['Key'] == 'CurrentDot']
    return str(row.iloc[0]['Value']) if not row.empty else "HocKy1"

def is_dot_active():
    df = load_data('Settings')
    if df.empty: return True
    row = df[df['Key'] == 'IsActive']
    val = str(row.iloc[0]['Value']).strip().lower()
    return val == 'true'

def calculate_progress(actual, target):
    try:
        t = float(target)
        a = float(actual)
        if t == 0: return 100.0 if a > 0 else 0.0
        prog = (a / t) * 100.0
        return min(prog, 100.0) # Max 100% (tuỳ chọn)
    except:
        return 0.0

# =============================================================================
# 3. CHỨC NĂNG BÁO CÁO (WORD)
# =============================================================================

def create_docx_report(hs_list, df_okr, df_rev, current_dot):
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    for index, hs in enumerate(hs_list):
        email_hs = hs['Email']
        p = doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {current_dot}", 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph(f"Họ tên: {hs['HoTen']}")
        doc.add_paragraph(f"Lớp: {hs['Lop']} | Email: {email_hs}")
        doc.add_paragraph("-" * 60)

        # I. OKR
        doc.add_heading('I. KẾT QUẢ THỰC HIỆN MỤC TIÊU', level=1)
        hs_okrs = df_okr[df_okr['Email'] == email_hs]
        
        if not hs_okrs.empty:
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text = 'Mục Tiêu'
            hdr[1].text = 'Kết Quả Then Chốt'
            hdr[2].text = 'Đích'
            hdr[3].text = 'Đạt'
            hdr[4].text = '%'
            hdr[5].text = 'ĐV'
            
            for _, row in hs_okrs.iterrows():
                cells = table.add_row().cells
                cells[0].text = str(row['MucTieu'])
                cells[1].text = str(row['KetQuaThenChot'])
                cells[2].text = str(row['TargetValue'])
                cells[3].text = str(row['ActualValue'])
                cells[4].text = f"{float(row['TienDo']):.1f}%"
                cells[5].text = str(row['Unit'])
        else:
            doc.add_paragraph("(Học sinh chưa đăng ký OKR)")

        # II. Nhận xét
        doc.add_heading('II. NHẬN XÉT & ĐÁNH GIÁ', level=1)
        hs_rev = df_rev[(df_rev['Email'] == email_hs) & (df_rev['Dot'] == current_dot)]
        
        gv_gen = hs_rev.iloc[0]['GV_General_Comment'] if not hs_rev.empty else "..."
        ph_cmt = hs_rev.iloc[0]['PH_Comment'] if not hs_rev.empty else "..."
        
        doc.add_paragraph(f"1. Nhận xét chung của GVCN:")
        doc.add_paragraph(str(gv_gen))
        doc.add_paragraph(f"2. Ý kiến của Phụ Huynh:")
        doc.add_paragraph(str(ph_cmt))
        
        if index < len(hs_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. GIAO DIỆN & AUTH
# =============================================================================

def change_password_ui():
    with st.expander("🔐 Đổi mật khẩu"):
        with st.form("change_pass_form"):
            old_pass = st.text_input("Mật khẩu cũ", type="password")
            new_pass = st.text_input("Mật khẩu mới", type="password")
            confirm_pass = st.text_input("Nhập lại mật khẩu mới", type="password")
            btn = st.form_submit_button("Xác nhận đổi")
            
            if btn:
                user_email = st.session_state.user['Email']
                df_users = load_data('Users')
                # Tìm index người dùng
                user_indices = df_users[df_users['Email'] == user_email].index
                
                if not user_indices.empty:
                    idx = user_indices[0]
                    current_db_pass = str(df_users.at[idx, 'Password'])
                    if old_pass != current_db_pass:
                        st.error("Mật khẩu cũ không đúng.")
                    elif new_pass != confirm_pass:
                        st.error("Mật khẩu mới không khớp.")
                    else:
                        df_users.at[idx, 'Password'] = new_pass
                        if save_dataframe('Users', df_users):
                            st.success("Đổi mật khẩu thành công!")
                        else:
                            st.error("Lỗi khi lưu mật khẩu mới.")
                else:
                    st.error("Không tìm thấy user.")

def sidebar_info():
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3209/3209265.png", width=80)
        st.markdown(f"**Xin chào: {st.session_state.user['HoTen']}**")
        st.code(f"Role: {st.session_state.user['Role']}")
        
        if 'Lop' in st.session_state.user and st.session_state.user['Lop']:
            st.write(f"Lớp: **{st.session_state.user['Lop']}**")
        else:
            if st.session_state.user['Role'] in ['HocSinh', 'GiaoVien']:
                st.error("⚠️ TÀI KHOẢN CHƯA CÓ LỚP! Vui lòng liên hệ Admin.")
        
        change_password_ui()
        
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.user = None
            st.rerun()

def login_screen():
    st.title("🏫 CỔNG QUẢN LÝ OKR TRƯỜNG HỌC")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("frm_login"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            is_parent = st.checkbox("Phụ huynh đăng nhập")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                if email == MASTER_EMAIL and password == MASTER_PASS:
                    st.session_state.user = {'Email': MASTER_EMAIL, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()

                df_users = load_data('Users')
                if df_users.empty:
                    st.error("Không thể kết nối CSDL Users.")
                    return

                if is_parent:
                    # Logic PH: Check EmailPH và Pass của HS
                    user_match = df_users[(df_users['EmailPH'] == email) & (df_users['Password'] == password)]
                    if not user_match.empty:
                        hs_info = user_match.iloc[0]
                        st.session_state.user = {
                            'Email': email, 
                            'Role': 'PhuHuynh',
                            'HoTen': f"PH em {hs_info['HoTen']}",
                            'ChildEmail': hs_info['Email'],
                            'ChildName': hs_info['HoTen']
                        }
                        st.rerun()
                    else:
                        st.error("Sai thông tin (Dùng mật khẩu của Học sinh).")
                else:
                    # Logic GV/HS/Admin thường
                    user_match = df_users[(df_users['Email'] == email) & (df_users['Password'] == password)]
                    if not user_match.empty:
                        user_data = user_match.iloc[0].to_dict()
                        # Đảm bảo trường Lop luôn là string
                        user_data['Lop'] = str(user_data.get('Lop', ''))
                        st.session_state.user = user_data
                        st.rerun()
                    else:
                        st.error("Sai Email hoặc Mật khẩu.")

# =============================================================================
# 5. DASHBOARD CHỨC NĂNG TỪNG ROLE
# =============================================================================

# --- A. ADMIN ---
def admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    tab1, tab2, tab3 = st.tabs(["👨‍🏫 Quản lý Giáo Viên", "⚙️ Quản lý Đợt", "📊 Thống kê"])
    
    with tab1:
        st.subheader("Danh sách Giáo Viên")
        df_users = load_data('Users')
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
        
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("##### Thêm Giáo Viên")
            with st.form("add_gv"):
                e = st.text_input("Email")
                n = st.text_input("Họ Tên")
                l = st.text_input("Lớp")
                s = st.number_input("Sĩ số", min_value=0)
                if st.form_submit_button("Thêm"):
                    if e not in df_users['Email'].values:
                        append_data_safe('Users', [e, "123", "GiaoVien", n, l, "", s])
                        st.success("Đã thêm!")
                        st.rerun()
                    else:
                        st.error("Email trùng!")
        
        with c2:
            st.markdown("##### Import Excel")
            f = st.file_uploader("File Excel", type=['xlsx'])
            if f and st.button("Import"):
                try:
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            rows.append([str(r['Email']), "123", "GiaoVien", str(r['HoTen']), str(r['Lop']), "", int(r['SiSo'])])
                    batch_append_data('Users', rows)
                    st.success("Xong!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")
        
        st.divider()
        st.markdown("##### ❌ Xóa Tài Khoản")
        del_email = st.selectbox("Chọn User để xóa", df_users['Email'])
        if st.button("Xác nhận xóa User"):
            df_users = df_users[df_users['Email'] != del_email]
            save_dataframe('Users', df_users)
            st.success("Đã xóa!")
            st.rerun()

    with tab2:
        curr = get_current_dot()
        act = is_dot_active()
        st.write(f"Hiện tại: **{curr}** ({'MỞ' if act else 'KHÓA'})")
        with st.form("set_dot"):
            nd = st.text_input("Đợt mới", value=curr)
            na = st.selectbox("Trạng thái", ["True", "False"], index=0 if act else 1)
            if st.form_submit_button("Lưu"):
                df_set = pd.DataFrame([['CurrentDot', nd], ['IsActive', na]], columns=['Key', 'Value'])
                save_dataframe('Settings', df_set)
                st.success("Đã lưu!")
                st.rerun()

    with tab3:
        df_okr = load_data('OKRs')
        st.metric("Tổng OKR", len(df_okr))

# --- B. GIÁO VIÊN ---
def teacher_dashboard():
    user = st.session_state.user
    st.title(f"👩‍🏫 GV: {user['HoTen']}")
    
    lop = str(user.get('Lop', ''))
    if not lop:
        st.error("❌ TÀI KHOẢN CỦA BẠN CHƯA ĐƯỢC GÁN LỚP. Vui lòng liên hệ Admin để thêm Lớp vào tài khoản.")
        return

    st.success(f"Đang quản lý lớp: **{lop}**")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Học Sinh", "1️⃣ Duyệt Đầu Kỳ", "2️⃣ Đánh Giá Cuối Kỳ", "🗑️ Yêu Cầu Xóa", "🖨️ Xuất Word"
    ])

    df_users = load_data('Users')
    # Filter chính xác theo string
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == lop)]
    
    df_okr = load_data('OKRs')
    # Đảm bảo OKR cũng lọc theo lớp string
    df_okr_class = df_okr[df_okr['Lop'] == lop]
    
    df_rev = load_data('Reviews')
    curr_dot = get_current_dot()

    # TAB 1: HS
    with tab1:
        st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
        with st.expander("Thêm/Import Học Sinh"):
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                uploaded = st.file_uploader("Import Excel (Email, HoTen, EmailPH)", type=['xlsx'])
                if uploaded and st.button("Import HS"):
                    try:
                        d = pd.read_excel(uploaded)
                        rows = []
                        for _, r in d.iterrows():
                            if str(r['Email']) not in df_users['Email'].values:
                                # Users Schema: Email, Password, Role, HoTen, Lop, EmailPH, SiSo
                                rows.append([
                                    str(r['Email']), "123", "HocSinh", str(r['HoTen']), lop, str(r['EmailPH']), 0
                                ])
                        if batch_append_data('Users', rows):
                            st.success(f"Đã thêm {len(rows)} HS!")
                            st.rerun()
                    except Exception as ex:
                        st.error(f"Lỗi: {ex}")
            with col_u2:
                hs_act = st.selectbox("Chọn HS tác vụ", df_hs['Email'])
                if st.button("Reset Pass (về 123)"):
                    idx = df_users[df_users['Email'] == hs_act].index[0]
                    df_users.at[idx, 'Password'] = "123"
                    save_dataframe('Users', df_users)
                    st.success("Đã reset pass.")

    # TAB 2: DUYỆT OKR
    with tab2:
        # Lọc các OKR cần duyệt: Status là MoiTao hoặc ChoDuyet hoặc CanSua
        pending = df_okr_class[(df_okr_class['Dot'] == curr_dot) & (df_okr_class['TrangThai'].isin(['MoiTao', 'ChoDuyet', 'CanSua']))]
        
        if pending.empty:
            st.info("✅ Tất cả OKR đã được duyệt.")
        else:
            for i, row in pending.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    with c1:
                        st.write(f"**{row['Email']}** - {row['MucTieu']}")
                        st.caption(f"KR: {row['KetQuaThenChot']} | Target: {row['TargetValue']} {row['Unit']}")
                    with c2:
                        cmt = st.text_input("Góp ý:", value=str(row['NhanXet_GV_L1']), key=f"c_{row['ID']}")
                    with c3:
                        if st.button("Duyệt", key=f"ok_{row['ID']}"):
                            # Cập nhật trực tiếp vào DF toàn cục rồi lưu
                            idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                            df_okr.at[idx, 'TrangThai'] = 'DangThucHien'
                            df_okr.at[idx, 'NhanXet_GV_L1'] = cmt
                            save_dataframe('OKRs', df_okr)
                            st.rerun()
                        if st.button("Sửa", key=f"fix_{row['ID']}"):
                            idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                            df_okr.at[idx, 'TrangThai'] = 'CanSua'
                            df_okr.at[idx, 'NhanXet_GV_L1'] = cmt
                            save_dataframe('OKRs', df_okr)
                            st.rerun()

    # TAB 3: ĐÁNH GIÁ
    with tab3:
        hs_sel = st.selectbox("Chọn HS đánh giá", df_hs['Email'])
        hs_okrs = df_okr_class[(df_okr_class['Email'] == hs_sel) & (df_okr_class['Dot'] == curr_dot)]
        
        st.table(hs_okrs[['MucTieu', 'TargetValue', 'ActualValue', 'TienDo', 'TrangThai']])
        
        # Review Data
        r_row = df_rev[(df_rev['Email'] == hs_sel) & (df_rev['Dot'] == curr_dot)]
        old_g = r_row.iloc[0]['GV_General_Comment'] if not r_row.empty else ""
        old_p = r_row.iloc[0]['PH_Comment'] if not r_row.empty else ""
        
        st.info(f"PH Comment: {old_p}")
        
        with st.form("eval_form"):
            gv_cmt = st.text_area("Nhận xét tổng kết:", value=old_g)
            fin_all = st.checkbox("Đánh dấu tất cả OKR là HOÀN THÀNH?")
            if st.form_submit_button("Lưu Đánh Giá"):
                # Save Review
                if r_row.empty:
                    append_data_safe('Reviews', [hs_sel, curr_dot, gv_cmt, ""])
                else:
                    ridx = r_row.index[0]
                    df_rev.at[ridx, 'GV_General_Comment'] = gv_cmt
                    save_dataframe('Reviews', df_rev)
                
                # Update OKR Status
                if fin_all and not hs_okrs.empty:
                    for oid in hs_okrs.index:
                        # Tìm index trong df gốc
                        orig_idx = df_okr.index[df_okr['ID'] == hs_okrs.at[oid, 'ID']][0]
                        df_okr.at[orig_idx, 'TrangThai'] = 'HoanThanh'
                    save_dataframe('OKRs', df_okr)
                
                st.success("Đã lưu!")
                st.rerun()

    # TAB 4: XÓA
    with tab4:
        # Lọc yêu cầu xóa của lớp
        reqs = df_okr_class[df_okr_class['DeleteRequest'].astype(str) == 'TRUE']
        if reqs.empty:
            st.info("Không có yêu cầu xóa.")
        else:
            for i, row in reqs.iterrows():
                col1, col2 = st.columns([4, 1])
                col1.warning(f"{row['Email']} muốn xóa: {row['MucTieu']}")
                if col2.button("Xóa ngay", key=f"d_{row['ID']}"):
                    df_okr = df_okr[df_okr['ID'] != row['ID']]
                    save_dataframe('OKRs', df_okr)
                    st.rerun()

    # TAB 5: BÁO CÁO
    with tab5:
        c1, c2 = st.columns(2)
        with c1:
            one_hs = st.selectbox("Chọn 1 HS", df_hs['Email'], key="w1")
            if st.button("Tải Word 1 HS"):
                h_obj = df_hs[df_hs['Email'] == one_hs].iloc[0].to_dict()
                bio = create_docx_report([h_obj], df_okr, df_rev, curr_dot)
                st.download_button("Download .docx", bio, f"OKR_{one_hs}.docx")
        with c2:
            st.write("Tải cả lớp")
            if st.button("Tải Word Cả Lớp"):
                h_list = df_hs.to_dict('records')
                bio = create_docx_report(h_list, df_okr, df_rev, curr_dot)
                st.download_button("Download All", bio, f"OKR_Lop_{lop}.docx")

# --- C. HỌC SINH ---
def student_dashboard():
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    # --- CHECK LỚP QUAN TRỌNG ---
    my_class = str(user.get('Lop', ''))
    if not my_class:
        st.error("⛔ TÀI KHOẢN CỦA EM BỊ LỖI (CHƯA CÓ LỚP). VUI LÒNG BÁO GVCN/ADMIN.")
        return

    curr_dot = get_current_dot()
    is_active = is_dot_active()
    
    st.info(f"Đợt: {curr_dot} | Lớp: {my_class}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == curr_dot)]
    
    # 1. TẠO OKR
    with st.expander("➕ Đăng ký OKR Mới", expanded=is_active):
        if is_active:
            with st.form("new_okr"):
                obj = st.text_input("Mục tiêu (Objective)")
                kr = st.text_area("Kết quả then chốt (Key Result)")
                c1, c2 = st.columns(2)
                target = c1.number_input("Mục tiêu số (Target)", min_value=0.0, step=0.1)
                unit = c2.text_input("Đơn vị (VD: Điểm)")
                
                if st.form_submit_button("Gửi Duyệt"):
                    if not obj or not kr:
                        st.error("Vui lòng nhập đủ thông tin!")
                    else:
                        new_id = str(uuid.uuid4())[:8]
                        # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai, DelReq, GVL1, GVL2
                        row_data = [
                            new_id, 
                            user['Email'], 
                            my_class, # Lớp phải lấy từ user session
                            curr_dot, 
                            obj, 
                            kr, 
                            float(target), # Cast float
                            0.0, # Actual
                            unit, 
                            0.0, # Progress
                            'ChoDuyet', 
                            'FALSE', 
                            '', ''
                        ]
                        
                        if append_data_safe('OKRs', row_data):
                            st.success("✅ Đã gửi OKR thành công! Đang chờ GV duyệt.")
                            time.sleep(1)
                            st.rerun()
        else:
            st.warning("Đợt đánh giá đã đóng.")

    # 2. DANH SÁCH
    st.subheader("Tiến độ của em")
    if my_okrs.empty:
        st.info("Em chưa có OKR nào.")
    else:
        for i, row in my_okrs.iterrows():
            with st.container(border=True):
                stt = row['TrangThai']
                color = "orange" if stt=='ChoDuyet' else "blue" if stt=='DangThucHien' else "green"
                
                st.markdown(f"**{row['MucTieu']}** <span style='color:{color}'>({stt})</span>", unsafe_allow_html=True)
                st.caption(f"KR: {row['KetQuaThenChot']}")
                
                if stt == 'CanSua':
                    st.error(f"⚠️ GV yêu cầu sửa: {row['NhanXet_GV_L1']}")
                    if st.button("Xóa để tạo lại", key=f"del_{row['ID']}"):
                        df_okr = df_okr[df_okr['ID'] != row['ID']]
                        save_dataframe('OKRs', df_okr)
                        st.rerun()

                elif stt in ['DangThucHien', 'HoanThanh']:
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        # Progress Logic
                        current_act = float(row['ActualValue'])
                        target_val = float(row['TargetValue'])
                        new_act = st.number_input(f"Đã đạt ({row['Unit']})", value=current_act, key=f"val_{row['ID']}")
                        
                        new_prog = calculate_progress(new_act, target_val)
                        st.progress(int(new_prog))
                        st.caption(f"{new_prog:.1f}%")
                    
                    with c2:
                        st.write("")
                        if st.button("Cập nhật", key=f"up_{row['ID']}"):
                            # Tìm index trong df gốc để update
                            real_idx = df_okr.index[df_okr['ID'] == row['ID']].tolist()[0]
                            df_okr.at[real_idx, 'ActualValue'] = float(new_act)
                            df_okr.at[real_idx, 'TienDo'] = float(new_prog)
                            if save_dataframe('OKRs', df_okr):
                                st.success("Đã lưu!")
                                st.rerun()

                # Nút xin xóa
                if row['DeleteRequest'] == 'FALSE' and stt != 'CanSua':
                    if st.button("Xin xóa", key=f"req_{row['ID']}"):
                        real_idx = df_okr.index[df_okr['ID'] == row['ID']].tolist()[0]
                        df_okr.at[real_idx, 'DeleteRequest'] = 'TRUE'
                        save_dataframe('OKRs', df_okr)
                        st.rerun()
                elif row['DeleteRequest'] == 'TRUE':
                    st.warning("Đã gửi yêu cầu xóa.")

# --- D. PHỤ HUYNH ---
def parent_dashboard():
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 PHHS em: {user['ChildName']}")
    
    child_email = user['ChildEmail']
    curr_dot = get_current_dot()
    
    df_okr = load_data('OKRs')
    child_okrs = df_okr[(df_okr['Email'] == child_email) & (df_okr['Dot'] == curr_dot)]
    
    st.subheader("Kết quả học tập")
    if not child_okrs.empty:
        # View Only
        view_df = child_okrs[['MucTieu', 'KetQuaThenChot', 'TargetValue', 'ActualValue', 'TienDo', 'TrangThai']].copy()
        view_df['TienDo'] = view_df['TienDo'].apply(lambda x: f"{float(x):.1f}%")
        st.table(view_df)
    else:
        st.info("Chưa có dữ liệu OKR.")
    
    st.divider()
    df_rev = load_data('Reviews')
    r_row = df_rev[(df_rev['Email'] == child_email) & (df_rev['Dot'] == curr_dot)]
    
    gv_cmt = r_row.iloc[0]['GV_General_Comment'] if not r_row.empty else "Chưa có."
    st.info(f"Nhận xét GVCN: {gv_cmt}")
    
    ph_old = r_row.iloc[0]['PH_Comment'] if not r_row.empty else ""
    with st.form("ph_f"):
        txt = st.text_area("Ý kiến gia đình:", value=ph_old)
        if st.form_submit_button("Gửi"):
            if r_row.empty:
                append_data_safe('Reviews', [child_email, curr_dot, "", txt])
            else:
                idx = r_row.index[0]
                df_rev.at[idx, 'PH_Comment'] = txt
                save_dataframe('Reviews', df_rev)
            st.success("Đã gửi!")
            st.rerun()

# =============================================================================
# MAIN
# =============================================================================

def main():
    if st.session_state.user is None:
        login_screen()
    else:
        sidebar_info()
        role = st.session_state.user['Role']
        
        try:
            if role == 'Admin':
                admin_dashboard()
            elif role == 'GiaoVien':
                teacher_dashboard()
            elif role == 'HocSinh':
                student_dashboard()
            elif role == 'PhuHuynh':
                parent_dashboard()
        except Exception as e:
            st.error(f"Lỗi hệ thống: {e}")

if __name__ == "__main__":
    main()
