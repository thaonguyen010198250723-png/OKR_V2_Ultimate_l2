import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import time
import uuid

# =============================================================================
# CẤU HÌNH HỆ THỐNG (SYSTEM CONFIG)
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường Học",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ID Google Sheet Cố Định (Theo yêu cầu)
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"

# Master Key (Dự phòng)
MASTER_EMAIL = "admin@school.com"
MASTER_PASS = "123"

# Định nghĩa cấu trúc chuẩn của các bảng (Để tự động update nếu thiếu cột)
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

# =============================================================================
# XỬ LÝ DỮ LIỆU & CACHE (DATA HANDLING)
# =============================================================================

def get_gspread_client():
    """Kết nối Google Sheets"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Lấy credentials từ secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Lỗi kết nối Google API: {str(e)}")
        return None

@st.cache_data(ttl=60)
def load_data(sheet_name):
    """
    Đọc dữ liệu từ Sheet với Cache TTL 60s.
    Tự động thêm cột nếu thiếu (Schema Migration).
    """
    try:
        client = get_gspread_client()
        if not client: return pd.DataFrame()
        
        sh = client.open_by_key(SHEET_ID)
        
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # Tạo mới nếu chưa có
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA.get(sheet_name, []))
            return pd.DataFrame(columns=SCHEMA.get(sheet_name, []))

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- LOGIC TỰ ĐỘNG SỬA SCHEMA ---
        # Nếu sheet cũ thiếu cột mới quy định, tự động thêm vào DF (để code không lỗi)
        # Lưu ý: Việc này chỉ thêm vào DF đọc lên, lần sau save đè sẽ cập nhật vào Sheet
        expected_cols = SCHEMA.get(sheet_name, [])
        if expected_cols:
            is_changed = False
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = "" if col not in ['TargetValue', 'ActualValue', 'TienDo', 'SiSo'] else 0
                    is_changed = True
            
            # Sắp xếp lại cột cho đúng chuẩn
            # Chỉ lấy các cột có trong schema + các cột dư (nếu có)
            cols_order = [c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]
            df = df[cols_order]

        # Convert Types
        if sheet_name == 'Users' and not df.empty:
            df['Password'] = df['Password'].astype(str)
        if sheet_name == 'OKRs' and not df.empty:
            df['TargetValue'] = pd.to_numeric(df['TargetValue'], errors='coerce').fillna(0)
            df['ActualValue'] = pd.to_numeric(df['ActualValue'], errors='coerce').fillna(0)
            df['TienDo'] = pd.to_numeric(df['TienDo'], errors='coerce').fillna(0)

        return df
    except Exception as e:
        st.error(f"Không thể tải dữ liệu {sheet_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def save_dataframe(sheet_name, df):
    """Ghi đè toàn bộ sheet (Dùng cho Update/Delete)"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")
        return False

def append_data(sheet_name, row_data):
    """Thêm 1 dòng (Append)"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.append_row(row_data)
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi thêm dữ liệu: {e}")
        return False

def batch_append_data(sheet_name, data_list):
    """Import hàng loạt (Tối ưu hiệu suất)"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.append_rows(data_list)
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi import dữ liệu: {e}")
        return False

# =============================================================================
# LOGIC NGHIỆP VỤ (BUSINESS LOGIC)
# =============================================================================

def get_current_dot():
    df = load_data('Settings')
    if df.empty: return "HocKy1"
    row = df[df['Key'] == 'CurrentDot']
    return row.iloc[0]['Value'] if not row.empty else "HocKy1"

def is_dot_active():
    df = load_data('Settings')
    if df.empty: return True
    row = df[df['Key'] == 'IsActive']
    return str(row.iloc[0]['Value']).lower() == 'true' if not row.empty else True

def calculate_progress(actual, target):
    try:
        t = float(target)
        a = float(actual)
        if t == 0: return 100.0 if a > 0 else 0.0
        return (a / t) * 100.0
    except:
        return 0.0

# =============================================================================
# WORD REPORT GENERATOR
# =============================================================================

def create_docx_report(hs_list, df_okr, df_rev, current_dot):
    doc = Document()
    
    # Định dạng chung
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    for index, hs in enumerate(hs_list):
        email_hs = hs['Email']
        
        # Header
        p = doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {current_dot}", 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph(f"Họ tên: {hs['HoTen']}")
        doc.add_paragraph(f"Lớp: {hs['Lop']} | Email: {email_hs}")
        doc.add_paragraph("-" * 60)

        # 1. Bảng OKR
        doc.add_heading('I. KẾT QUẢ THỰC HIỆN MỤC TIÊU', level=1)
        
        hs_okrs = df_okr[df_okr['Email'] == email_hs]
        
        if not hs_okrs.empty:
            # Tạo bảng: MucTieu, KR, Target, Actual, Unit, %, TrangThai
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

        # 2. Nhận xét
        doc.add_heading('II. NHẬN XÉT & ĐÁNH GIÁ', level=1)
        hs_rev = df_rev[(df_rev['Email'] == email_hs) & (df_rev['Dot'] == current_dot)]
        
        gv_l1_cmt = ""
        gv_l2_cmt = ""
        ph_cmt = ""
        gv_gen = ""
        
        # Lấy comment từ bảng OKR (cho từng OKR) hoặc bảng Review (chung)
        # Theo yêu cầu, bảng Review chứa Comment chung
        if not hs_rev.empty:
            r = hs_rev.iloc[0]
            gv_gen = r['GV_General_Comment']
            ph_cmt = r['PH_Comment']
        
        # Lấy comment chi tiết từ bảng OKR (nếu có cột comment từng OKR)
        # Ở đây lấy mẫu chung
        doc.add_paragraph(f"1. Nhận xét chung của GVCN:")
        doc.add_paragraph(str(gv_gen) if gv_gen else "...")
        
        doc.add_paragraph(f"2. Ý kiến của Phụ Huynh:")
        doc.add_paragraph(str(ph_cmt) if ph_cmt else "...")
        
        # Ngắt trang nếu không phải HS cuối cùng
        if index < len(hs_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# AUTH & SIDEBAR
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
                user_row = df_users[df_users['Email'] == user_email]
                
                if not user_row.empty:
                    current_db_pass = str(user_row.iloc[0]['Password'])
                    if old_pass != current_db_pass:
                        st.error("Mật khẩu cũ không đúng.")
                    elif new_pass != confirm_pass:
                        st.error("Mật khẩu mới không khớp.")
                    else:
                        df_users.loc[df_users['Email'] == user_email, 'Password'] = new_pass
                        save_dataframe('Users', df_users)
                        st.success("Đổi mật khẩu thành công!")
                else:
                    st.error("Không tìm thấy user.")

def sidebar_info():
    with st.sidebar:
        # Logo Trường (Placeholder)
        st.logo("https://cdn-icons-png.flaticon.com/512/3209/3209265.png")
        st.image("https://cdn-icons-png.flaticon.com/512/3209/3209265.png", width=100)
        
        st.write("---")
        st.write(f"Xin chào: **{st.session_state.user['HoTen']}**")
        st.write(f"Vai trò: `{st.session_state.user['Role']}`")
        if 'Lop' in st.session_state.user and st.session_state.user['Lop']:
            st.write(f"Lớp: **{st.session_state.user['Lop']}**")
        
        change_password_ui()
        
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.user = None
            st.rerun()

def login_screen():
    st.title("🏫 CỔNG QUẢN LÝ OKR TRƯỜNG HỌC")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("frm_login"):
            email = st.text_input("Email đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            is_parent = st.checkbox("Đăng nhập với tư cách Phụ Huynh")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                # Bypass Admin
                if email == MASTER_EMAIL and password == MASTER_PASS:
                    st.session_state.user = {'Email': MASTER_EMAIL, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()

                df_users = load_data('Users')
                if df_users.empty:
                    st.error("Chưa có dữ liệu người dùng.")
                    return

                if is_parent:
                    # Logic PH: Check EmailPH matches Input Email -> Password check on User row?
                    # Yêu cầu: Đăng nhập bằng Email phụ huynh (liên kết qua cột EmailPH).
                    # Giả định: PH dùng chung Pass của con hoặc PH có tài khoản riêng?
                    # Theo prompt: "Đăng nhập bằng Email phụ huynh (liên kết qua cột EmailPH của bảng Users)."
                    # -> Tìm xem Email nhập vào có nằm trong cột EmailPH không.
                    # Mật khẩu: Tạm thời lấy mật khẩu của HS tương ứng (hoặc mặc định). 
                    # Để đơn giản và an toàn: Check EmailPH và Password nhập vào phải khớp với Password của HS đó.
                    
                    user_match = df_users[(df_users['EmailPH'] == email) & (df_users['Password'] == password)]
                    if not user_match.empty:
                        # Login thành công -> Role PH
                        hs_info = user_match.iloc[0]
                        st.session_state.user = {
                            'Email': email, # Email PH
                            'Role': 'PhuHuynh',
                            'HoTen': f"PH em {hs_info['HoTen']}",
                            'ChildEmail': hs_info['Email'], # Lưu email con để query
                            'ChildName': hs_info['HoTen']
                        }
                        st.rerun()
                    else:
                        st.error("Sai Email Phụ huynh hoặc Mật khẩu (dùng mật khẩu của con).")
                
                else:
                    # Logic Normal User
                    user_match = df_users[(df_users['Email'] == email) & (df_users['Password'] == password)]
                    if not user_match.empty:
                        st.session_state.user = user_match.iloc[0].to_dict()
                        st.rerun()
                    else:
                        st.error("Sai Email hoặc Mật khẩu.")

# =============================================================================
# DASHBOARD: ADMIN
# =============================================================================

def admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    tab1, tab2, tab3 = st.tabs(["👨‍🏫 Quản lý Giáo Viên", "⚙️ Quản lý Đợt", "📊 Thống kê"])
    
    # --- TAB 1: GIÁO VIÊN ---
    with tab1:
        st.subheader("Danh sách Giáo Viên")
        df_users = load_data('Users')
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        
        # Hiển thị
        st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
        
        col_add, col_del = st.columns([2, 1])
        
        with col_add:
            st.markdown("##### Thêm Giáo Viên")
            mode = st.radio("Chế độ:", ["Thủ công", "Import Excel"])
            
            if mode == "Thủ công":
                with st.form("add_gv_manual"):
                    e = st.text_input("Email")
                    n = st.text_input("Họ Tên")
                    l = st.text_input("Lớp Chủ Nhiệm")
                    s = st.number_input("Sĩ số", min_value=0)
                    if st.form_submit_button("Thêm"):
                        if e not in df_users['Email'].values:
                            # Users Schema: Email, Password, Role, HoTen, Lop, EmailPH, SiSo
                            append_data('Users', [e, "123", "GiaoVien", n, l, "", s])
                            st.success("Đã thêm!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Email đã tồn tại.")
            else:
                f = st.file_uploader("Upload Excel (Email, HoTen, Lop, SiSo)", type=['xlsx'])
                if f and st.button("Import"):
                    try:
                        d = pd.read_excel(f)
                        rows = []
                        for _, r in d.iterrows():
                            if str(r['Email']) not in df_users['Email'].values:
                                rows.append([str(r['Email']), "123", "GiaoVien", str(r['HoTen']), str(r['Lop']), "", int(r['SiSo'])])
                        if rows:
                            batch_append_data('Users', rows)
                            st.success(f"Đã import {len(rows)} GV.")
                            time.sleep(1)
                            st.rerun()
                    except Exception as ex:
                        st.error(f"Lỗi: {ex}")
        
        with col_del:
            st.markdown("##### ❌ Xóa Giáo Viên")
            gv_to_del = st.selectbox("Chọn GV xóa", df_gv['Email'])
            if st.button("Xác nhận xóa GV"):
                df_users = df_users[df_users['Email'] != gv_to_del]
                save_dataframe('Users', df_users)
                st.success("Đã xóa!")
                st.rerun()

    # --- TAB 2: ĐỢT ---
    with tab2:
        curr = get_current_dot()
        act = is_dot_active()
        st.write(f"Đợt hiện tại: **{curr}** | Trạng thái: **{'MỞ' if act else 'KHÓA'}**")
        
        with st.form("set_dot"):
            n_dot = st.text_input("Tên đợt mới", value=curr)
            n_act = st.selectbox("Trạng thái", ["True", "False"], index=0 if act else 1)
            if st.form_submit_button("Lưu cài đặt"):
                df_set = pd.DataFrame([['CurrentDot', n_dot], ['IsActive', n_act]], columns=['Key', 'Value'])
                save_dataframe('Settings', df_set)
                st.success("Đã lưu!")
                st.rerun()

    # --- TAB 3: THỐNG KÊ ---
    with tab3:
        df_okr = load_data('OKRs')
        c1, c2 = st.columns(2)
        c1.metric("Tổng OKR", len(df_okr))
        c2.metric("Hoàn thành", len(df_okr[df_okr['TrangThai'] == 'HoanThanh']))

# =============================================================================
# DASHBOARD: GIÁO VIÊN
# =============================================================================

def teacher_dashboard():
    user = st.session_state.user
    st.title(f"👩‍🏫 Dashboard GVCN - {user['HoTen']}")
    
    lop = user.get('Lop', '')
    if not lop:
        st.warning("Tài khoản giáo viên này chưa được gán Lớp.")
        return

    st.info(f"Lớp quản lý: **{lop}**")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Quản lý HS", "1️⃣ Duyệt Đầu Kỳ", "2️⃣ Đánh Giá Cuối Kỳ", "🗑️ Yêu Cầu Xóa", "🖨️ Báo Cáo"
    ])

    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == lop)]
    df_okr = load_data('OKRs')
    df_rev = load_data('Reviews')
    curr_dot = get_current_dot()

    # --- TAB 1: QUẢN LÝ HS ---
    with tab1:
        st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Thêm/Import HS**")
            up = st.file_uploader("Excel (Email, HoTen, EmailPH)", type=['xlsx'])
            if up and st.button("Import HS"):
                d = pd.read_excel(up)
                rows = []
                for _, r in d.iterrows():
                    if str(r['Email']) not in df_users['Email'].values:
                        rows.append([str(r['Email']), "123", "HocSinh", str(r['HoTen']), lop, str(r['EmailPH']), 0])
                batch_append_data('Users', rows)
                st.success("Xong!")
                st.rerun()
        
        with c2:
            st.write("**Tác vụ tài khoản**")
            hs_act = st.selectbox("Chọn HS", df_hs['Email'])
            if st.button("Reset Mật Khẩu (Về 123)"):
                df_users.loc[df_users['Email'] == hs_act, 'Password'] = "123"
                save_dataframe('Users', df_users)
                st.success(f"Đã reset pass cho {hs_act}")
            
            if st.button("Xóa Tài Khoản HS", type="primary"):
                df_users = df_users[df_users['Email'] != hs_act]
                save_dataframe('Users', df_users)
                st.success("Đã xóa HS!")
                st.rerun()

    # --- TAB 2: DUYỆT ĐẦU KỲ ---
    with tab2:
        st.subheader("Duyệt OKR Mới (Trạng thái: ChoDuyet)")
        # Lọc OKR của lớp, đợt này, status = MoiTao/ChoDuyet
        pending_okrs = df_okr[(df_okr['Lop'] == lop) & (df_okr['Dot'] == curr_dot) & (df_okr['TrangThai'].isin(['MoiTao', 'ChoDuyet', 'CanSua']))]
        
        if pending_okrs.empty:
            st.info("Không có OKR cần duyệt.")
        else:
            for i, row in pending_okrs.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        st.write(f"**HS:** {row['Email']}")
                        st.write(f"**Mục tiêu:** {row['MucTieu']}")
                        st.caption(f"KR: {row['KetQuaThenChot']} (Target: {row['TargetValue']} {row['Unit']})")
                    with c2:
                        comment = st.text_input(f"Góp ý ##{row['ID']}", value=str(row['NhanXet_GV_L1']), key=f"cmt1_{row['ID']}")
                    with c3:
                        if st.button("✅ Duyệt", key=f"app_{row['ID']}"):
                            df_okr.loc[df_okr['ID'] == row['ID'], 'TrangThai'] = 'DangThucHien'
                            df_okr.loc[df_okr['ID'] == row['ID'], 'NhanXet_GV_L1'] = comment
                            save_dataframe('OKRs', df_okr)
                            st.rerun()
                        if st.button("⚠️ Yêu cầu sửa", key=f"fix_{row['ID']}"):
                            df_okr.loc[df_okr['ID'] == row['ID'], 'TrangThai'] = 'CanSua'
                            df_okr.loc[df_okr['ID'] == row['ID'], 'NhanXet_GV_L1'] = comment
                            save_dataframe('OKRs', df_okr)
                            st.rerun()

    # --- TAB 3: ĐÁNH GIÁ CUỐI KỲ ---
    with tab3:
        st.subheader("Nhận xét & Tổng kết")
        hs_select = st.selectbox("Chọn HS đánh giá", df_hs['Email'], key="hs_eval")
        
        # Hiện OKR của HS đó
        hs_okrs = df_okr[(df_okr['Email'] == hs_select) & (df_okr['Dot'] == curr_dot)]
        st.dataframe(hs_okrs[['MucTieu', 'TargetValue', 'ActualValue', 'TienDo', 'TrangThai']])
        
        # Load Comment cũ
        rev_row = df_rev[(df_rev['Email'] == hs_select) & (df_rev['Dot'] == curr_dot)]
        old_cmt = rev_row.iloc[0]['GV_General_Comment'] if not rev_row.empty else ""
        ph_cmt = rev_row.iloc[0]['PH_Comment'] if not rev_row.empty else "(Chưa có ý kiến)"
        
        st.info(f"🗨️ Ý kiến PH: {ph_cmt}")
        
        with st.form("final_eval"):
            gen_cmt = st.text_area("Nhận xét chung của GVCN", value=old_cmt)
            # Tùy chọn: Duyệt hoàn thành tất cả OKR?
            mark_finished = st.checkbox("Đánh dấu tất cả OKR là 'HoanThanh'?")
            
            if st.form_submit_button("Lưu Đánh Giá"):
                # Save Reviews
                if rev_row.empty:
                    append_data('Reviews', [hs_select, curr_dot, gen_cmt, ""])
                else:
                    df_rev.loc[rev_row.index, 'GV_General_Comment'] = gen_cmt
                    save_dataframe('Reviews', df_rev)
                
                # Update OKR Status if checked
                if mark_finished and not hs_okrs.empty:
                    df_okr.loc[hs_okrs.index, 'TrangThai'] = 'HoanThanh'
                    save_dataframe('OKRs', df_okr)
                
                st.success("Đã lưu!")
                st.rerun()

    # --- TAB 4: YÊU CẦU XÓA ---
    with tab4:
        del_reqs = df_okr[(df_okr['Lop'] == lop) & (df_okr['DeleteRequest'].astype(str) == 'TRUE')]
        if del_reqs.empty:
            st.info("Không có yêu cầu xóa.")
        else:
            for i, row in del_reqs.iterrows():
                c1, c2 = st.columns([4, 1])
                c1.warning(f"HS: {row['Email']} muốn xóa OKR: {row['MucTieu']}")
                if c2.button("Đồng ý xóa", key=f"del_{row['ID']}"):
                    df_okr = df_okr[df_okr['ID'] != row['ID']]
                    save_dataframe('OKRs', df_okr)
                    st.rerun()

    # --- TAB 5: BÁO CÁO ---
    with tab5:
        st.subheader("Xuất Phiếu Kết Quả (Word)")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("Tải phiếu 1 Học sinh")
            h = st.selectbox("Chọn HS", df_hs['Email'], key="rp_one")
            if st.button("Tải file .docx"):
                # Lấy dict hs
                hs_obj = df_hs[df_hs['Email'] == h].iloc[0].to_dict()
                bio = create_docx_report([hs_obj], df_okr, df_rev, curr_dot)
                st.download_button("Download", bio, f"OKR_{h}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        
        with c2:
            st.write("Tải phiếu CẢ LỚP (Gộp)")
            if st.button("Tải file .docx (All)"):
                hs_list = df_hs.to_dict('records')
                bio = create_docx_report(hs_list, df_okr, df_rev, curr_dot)
                st.download_button("Download All", bio, f"OKR_Lop_{lop}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# =============================================================================
# DASHBOARD: HỌC SINH
# =============================================================================

def student_dashboard():
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']} - Dashboard")
    
    curr_dot = get_current_dot()
    is_active = is_dot_active()
    
    st.write(f"Đợt: **{curr_dot}**")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == curr_dot)]
    
    # 1. Tạo OKR
    with st.expander("➕ Đăng ký OKR Mới", expanded=is_active):
        if is_active:
            with st.form("create_okr"):
                obj = st.text_input("Mục tiêu (Objective)")
                kr = st.text_area("Kết quả then chốt (KR)")
                c1, c2 = st.columns(2)
                target = c1.number_input("Mục tiêu số (Target)", min_value=0.0, step=1.0)
                unit = c2.text_input("Đơn vị (VD: Điểm, Quyển...)")
                
                if st.form_submit_button("Gửi Duyệt"):
                    new_id = str(uuid.uuid4())[:8]
                    # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai, DelReq, GVL1, GVL2
                    row = [new_id, user['Email'], user['Lop'], curr_dot, obj, kr, target, 0, unit, 0, 'ChoDuyet', 'FALSE', '', '']
                    append_data('OKRs', row)
                    st.success("Đã gửi!")
                    st.rerun()
        else:
            st.warning("Đợt đánh giá đã đóng.")

    # 2. Danh sách OKR & Cập nhật
    st.subheader("Tiến độ của tôi")
    if my_okrs.empty:
        st.info("Chưa có OKR nào.")
    else:
        for i, row in my_okrs.iterrows():
            with st.container(border=True):
                # Header Status
                stt = row['TrangThai']
                color = "orange" if stt=='ChoDuyet' else "blue" if stt=='DangThucHien' else "green" if stt=='HoanThanh' else "red"
                st.markdown(f"#### {row['MucTieu']} <span style='color:{color}; font-size:0.6em'>({stt})</span>", unsafe_allow_html=True)
                st.text(f"KR: {row['KetQuaThenChot']}")
                
                if stt in ['DangThucHien', 'HoanThanh']:
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        # Input số thực đạt
                        new_actual = st.number_input(f"Đã đạt ({row['Unit']})", value=float(row['ActualValue']), key=f"act_{row['ID']}")
                        target_val = float(row['TargetValue'])
                        prog = calculate_progress(new_actual, target_val)
                        st.progress(min(int(prog), 100))
                        st.caption(f"{prog:.1f}% (Đích: {target_val})")
                    
                    with c2:
                        st.write("") # Spacer
                        if st.button("Cập nhật tiến độ", key=f"up_{row['ID']}"):
                            df_okr.loc[df_okr['ID'] == row['ID'], 'ActualValue'] = new_actual
                            df_okr.loc[df_okr['ID'] == row['ID'], 'TienDo'] = prog
                            save_dataframe('OKRs', df_okr)
                            st.success("Đã lưu!")
                            st.rerun()
                
                elif stt == 'CanSua':
                    st.error(f"GV yêu cầu sửa: {row['NhanXet_GV_L1']}")
                    # Logic sửa OKR (Simplified: Xóa đi tạo lại hoặc Form update - Ở đây gợi ý HS xóa tạo lại cho nhanh hoặc làm tính năng edit sau)
                    st.info("Vui lòng xóa OKR này và tạo lại theo góp ý.")

                # Nút xóa
                if row['DeleteRequest'] == 'FALSE':
                    if st.button("Xin xóa", key=f"req_del_{row['ID']}"):
                        df_okr.loc[df_okr['ID'] == row['ID'], 'DeleteRequest'] = 'TRUE'
                        save_dataframe('OKRs', df_okr)
                        st.rerun()
                else:
                    st.caption("Đã gửi yêu cầu xóa.")

# =============================================================================
# DASHBOARD: PHỤ HUYNH
# =============================================================================

def parent_dashboard():
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 Phụ huynh HS: {user['ChildName']}")
    
    child_email = user['ChildEmail']
    curr_dot = get_current_dot()
    
    # Load data
    df_okr = load_data('OKRs')
    df_rev = load_data('Reviews')
    
    child_okrs = df_okr[(df_okr['Email'] == child_email) & (df_okr['Dot'] == curr_dot)]
    
    st.subheader("Kết quả học tập (OKR)")
    if not child_okrs.empty:
        # Show table clean
        view_df = child_okrs[['MucTieu', 'KetQuaThenChot', 'TargetValue', 'ActualValue', 'Unit', 'TienDo', 'TrangThai']].copy()
        view_df['TienDo'] = view_df['TienDo'].apply(lambda x: f"{x:.1f}%")
        st.table(view_df)
    else:
        st.info("Học sinh chưa có dữ liệu OKR đợt này.")
        
    st.write("---")
    st.subheader("Trao đổi với Nhà trường")
    
    rev_row = df_rev[(df_rev['Email'] == child_email) & (df_rev['Dot'] == curr_dot)]
    
    # Hiển thị nhận xét GV
    gv_cmt = rev_row.iloc[0]['GV_General_Comment'] if not rev_row.empty else "Chưa có nhận xét."
    st.info(f"🧑‍🏫 Giáo viên chủ nhiệm: {gv_cmt}")
    
    # Form PH Comment
    ph_old = rev_row.iloc[0]['PH_Comment'] if not rev_row.empty else ""
    with st.form("ph_cmt"):
        txt = st.text_area("Ý kiến của Gia đình:", value=str(ph_old))
        if st.form_submit_button("Gửi ý kiến"):
            if rev_row.empty:
                append_data('Reviews', [child_email, curr_dot, "", txt])
            else:
                df_rev.loc[rev_row.index, 'PH_Comment'] = txt
                save_dataframe('Reviews', df_rev)
            st.success("Đã gửi ý kiến!")
            st.rerun()

# =============================================================================
# MAIN RUN
# =============================================================================

def main():
    if st.session_state.user is None:
        login_screen()
    else:
        sidebar_info()
        role = st.session_state.user['Role']
        
        if role == 'Admin':
            admin_dashboard()
        elif role == 'GiaoVien':
            teacher_dashboard()
        elif role == 'HocSinh':
            student_dashboard()
        elif role == 'PhuHuynh':
            parent_dashboard()
        else:
            st.error("Lỗi quyền truy cập")

if __name__ == "__main__":
    main()
