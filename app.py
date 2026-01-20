import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import time
import uuid

# =============================================================================
# 1. CẤU HÌNH HỆ THỐNG & SCHEMA
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ID Google Sheet Cố Định
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/3209/3209265.png"

# Định nghĩa cấu trúc chuẩn (Schema) để tự động sửa lỗi
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'Periods': ['TenDot', 'TrangThai'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV'],
    'Reviews': ['Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH']
}

if 'user' not in st.session_state:
    st.session_state.user = None

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU & CACHE (BACKEND)
# =============================================================================

def get_client():
    """Kết nối Google API"""
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
    Load dữ liệu và tự động kiểm tra cột (Schema Migration).
    Nếu thiếu cột (ví dụ: SiSo) sẽ tự động thêm vào DataFrame để không bị lỗi.
    """
    client = get_client()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA[sheet_name])
            return pd.DataFrame(columns=SCHEMA[sheet_name])

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- QUAN TRỌNG: TỰ ĐỘNG THÊM CỘT THIẾU ---
        expected_cols = SCHEMA[sheet_name]
        
        # 1. Nếu DF rỗng (chỉ có header trong sheet hoặc sheet trắng)
        if df.empty:
            return pd.DataFrame(columns=expected_cols)

        # 2. Kiểm tra từng cột trong Schema, nếu thiếu thì thêm default
        for col in expected_cols:
            if col not in df.columns:
                # Default value: 0 cho số, "" cho chuỗi
                default_val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo'] else ""
                df[col] = default_val
        
        # 3. Sắp xếp lại cột cho đúng chuẩn
        # Giữ lại các cột extra nếu có, nhưng ưu tiên thứ tự Schema
        final_cols = [c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]
        df = df[final_cols]

        # --- TYPE CASTING (Ép kiểu dữ liệu) ---
        if sheet_name == 'Users':
            df['Password'] = df['Password'].astype(str)
            df['SiSo'] = pd.to_numeric(df['SiSo'], errors='coerce').fillna(0).astype(int)
            df['Lop'] = df['Lop'].astype(str)
        
        if sheet_name == 'OKRs':
            for c in ['MucTieuSo', 'ThucDat', 'TienDo']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

        return df
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu {sheet_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def append_row(sheet_name, row_data):
    """Thêm dòng mới vào Google Sheet"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        
        # Convert numpy types to native python types để tránh lỗi JSON
        clean_row = []
        for item in row_data:
            if isinstance(item, (int, float)):
                clean_row.append(item)
            elif item is None:
                clean_row.append("")
            else:
                clean_row.append(str(item))
                
        ws.append_row(clean_row, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")
        return False

def save_df(sheet_name, df):
    """Lưu toàn bộ DataFrame (Dùng cho Update/Delete)"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi cập nhật bảng: {e}")
        return False

def batch_append(sheet_name, data_list):
    """Import hàng loạt"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.append_rows(data_list, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi import: {e}")
        return False

# =============================================================================
# 3. UTILITIES (HỖ TRỢ)
# =============================================================================

def calculate_progress(actual, target):
    try:
        t = float(target)
        a = float(actual)
        if t == 0: return 100.0 if a > 0 else 0.0
        return min((a / t) * 100.0, 100.0)
    except:
        return 0.0

def generate_word_report(hs_list, df_okr, df_rev, period):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    for i, hs in enumerate(hs_list):
        doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {period}", 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Học sinh: {hs['HoTen']} - Lớp: {hs['Lop']}")
        doc.add_paragraph("-" * 60)
        
        # OKR Table
        doc.add_heading('I. KẾT QUẢ OKR', level=1)
        sub_okr = df_okr[(df_okr['Email'] == hs['Email']) & (df_okr['Dot'] == period)]
        
        if not sub_okr.empty:
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text = 'Mục Tiêu', 'KR'
            hdr[2].text, hdr[3].text = 'Đích', 'Đạt'
            hdr[4].text, hdr[5].text = '%', 'Trạng thái'
            
            for _, row in sub_okr.iterrows():
                cells = table.add_row().cells
                cells[0].text = str(row['MucTieu'])
                cells[1].text = str(row['KetQuaThenChot'])
                cells[2].text = f"{row['MucTieuSo']} {row['DonVi']}"
                cells[3].text = str(row['ThucDat'])
                cells[4].text = f"{row['TienDo']:.1f}%"
                cells[5].text = str(row['TrangThai'])
        else:
            doc.add_paragraph("Chưa có dữ liệu OKR.")

        # Reviews
        doc.add_heading('II. NHẬN XÉT', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        if not sub_rev.empty:
            r = sub_rev.iloc[0]
            doc.add_paragraph(f"GVCN: {r['NhanXet_CuoiKy']}")
            doc.add_paragraph(f"Phụ huynh: {r['PhanHoi_PH']}")
        else:
            doc.add_paragraph("Chưa có đánh giá.")
            
        if i < len(hs_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. GIAO DIỆN: SIDEBAR & LOGIN
# =============================================================================

def sidebar_controller():
    with st.sidebar:
        st.image(LOGO_URL, width=80)
        st.markdown("### SCHOOL OKR")
        
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            
            # --- GLOBAL PERIOD SELECTOR ---
            st.divider()
            st.markdown("📅 **CHỌN ĐỢT**")
            df_p = load_data('Periods')
            
            p_options = df_p['TenDot'].tolist() if not df_p.empty else []
            if not p_options:
                return "Chưa có đợt", False
            
            # Logic chọn đợt mặc định: Đợt đang Mở
            idx = 0
            open_dots = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if open_dots:
                try: idx = p_options.index(open_dots[0])
                except: pass
            
            sel_period = st.selectbox("Đợt đánh giá:", p_options, index=idx)
            
            # Check status
            status = df_p[df_p['TenDot'] == sel_period].iloc[0]['TrangThai']
            is_open = (status == 'Mở')
            
            if is_open:
                st.success(f"Trạng thái: {status} 🟢")
            else:
                st.error(f"Trạng thái: {status} 🔒")
            
            st.divider()
            if st.button("Đăng xuất", use_container_width=True):
                st.session_state.user = None
                st.rerun()
                
            return sel_period, is_open
    return None, False

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏫 HỆ THỐNG OKR</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                # Master Admin
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()
                
                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu.")
                    return

                # Check Normal User
                match = df[(df['Email'] == email) & (df['Password'] == password)]
                if not match.empty:
                    st.session_state.user = match.iloc[0].to_dict()
                    st.rerun()
                
                # Check Parent (via EmailPH)
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
# 5. MODULE CHỨC NĂNG (ADMIN, TEACHER, STUDENT, PARENT)
# =============================================================================

# --- A. ADMIN (SỬA LỖI & BỔ SUNG SĨ SỐ) ---
def admin_module(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["👨‍🏫 Quản lý Giáo Viên", "⚙️ Quản lý Đợt", "📊 Thống kê"])
    
    # 1. Quản lý Giáo Viên
    with t1:
        df_users = load_data('Users')
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        
        c_list, c_act = st.columns([2, 1])
        
        with c_list:
            st.subheader("Danh sách Giáo Viên")
            # Hiển thị cả cột SiSo
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
            
            with st.expander("🗑️ Xóa tài khoản Giáo viên"):
                del_gv = st.selectbox("Chọn GV cần xóa", df_gv['Email'])
                if st.button("Xác nhận xóa"):
                    df_users = df_users[df_users['Email'] != del_gv]
                    save_df('Users', df_users)
                    st.success("Đã xóa!")
                    st.rerun()

        with c_act:
            st.subheader("Thêm Giáo Viên")
            mode = st.radio("Chế độ:", ["Thêm Thủ Công", "Import Excel"])
            
            if mode == "Thêm Thủ Công":
                with st.form("add_gv_manual"):
                    # Các trường bắt buộc
                    new_email = st.text_input("Email")
                    new_name = st.text_input("Họ Tên")
                    new_class = st.text_input("Lớp Chủ Nhiệm")
                    # --- BỔ SUNG: Nhập Sĩ Số ---
                    new_siso = st.number_input("Sĩ Số Lớp", min_value=0, step=1, value=0)
                    
                    if st.form_submit_button("Tạo Tài Khoản"):
                        if new_email and new_name and new_class:
                            if new_email in df_users['Email'].values:
                                st.error("Email đã tồn tại!")
                            else:
                                # Schema: Email, Password, Role, HoTen, Lop, EmailPH, SiSo
                                # EmailPH để trống, SiSo lấy từ input
                                row = [new_email, "123", "GiaoVien", new_name, new_class, "", int(new_siso)]
                                if append_row('Users', row):
                                    st.success(f"Đã thêm GV {new_name} - Sĩ số: {new_siso}")
                                    time.sleep(1)
                                    st.rerun()
                        else:
                            st.warning("Vui lòng nhập đủ thông tin.")
            
            else: # Import Excel
                f = st.file_uploader("File Excel (Email, HoTen, Lop, SiSo)", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            # Handle SiSo from excel, default 0 if missing
                            siso_val = int(r['SiSo']) if 'SiSo' in r and pd.notnull(r['SiSo']) else 0
                            rows.append([
                                str(r['Email']), "123", "GiaoVien", 
                                str(r['HoTen']), str(r['Lop']), "", siso_val
                            ])
                    if batch_append('Users', rows):
                        st.success(f"Đã import {len(rows)} giáo viên.")
                        st.rerun()

    # 2. Quản lý Đợt
    with t2:
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("add_period"):
                np = st.text_input("Tên đợt mới (VD: HK1)")
                if st.form_submit_button("Tạo Đợt"):
                    df_p = load_data('Periods')
                    if np not in df_p['TenDot'].values:
                        append_row('Periods', [np, "Mở"])
                        st.success("Đã tạo!")
                        st.rerun()
                    else: st.error("Trùng tên!")
        with c2:
            df_p = load_data('Periods')
            for i, r in df_p.iterrows():
                col1, col2 = st.columns([3, 1])
                col1.write(f"**{r['TenDot']}** - `{r['TrangThai']}`")
                new_stt = "Khóa" if r['TrangThai'] == "Mở" else "Mở"
                if col2.button(f"Đổi sang {new_stt}", key=f"p_{i}"):
                    df_p.at[i, 'TrangThai'] = new_stt
                    save_df('Periods', df_p)
                    st.rerun()

    # 3. Thống kê
    with t3:
        st.info(f"Số liệu đợt: {period}")
        df_okr = load_data('OKRs')
        df_sub = df_okr[df_okr['Dot'] == period]
        m1, m2 = st.columns(2)
        m1.metric("Tổng OKR", len(df_sub))
        m2.metric("Hoàn thành", len(df_sub[df_sub['TienDo'] == 100]))

# --- B. TEACHER ---
def teacher_module(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    
    st.title(f"👩‍🏫 GVCN Lớp: {my_class}")
    if not my_class:
        st.error("Tài khoản chưa có Lớp.")
        return

    t1, t2, t3, t4 = st.tabs(["DS Học Sinh", "Duyệt OKR", "Đánh giá CK", "Báo Cáo"])
    
    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    df_okr = load_data('OKRs')
    # Filter OKR by Class and Period
    df_okr_class = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    df_rev = load_data('Reviews')

    with t1: # Quản lý HS
        c1, c2 = st.columns([2, 1])
        with c1: st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
        with c2: 
            st.caption("Import HS vào Lớp này")
            f = st.file_uploader("Excel HS", type=['xlsx'])
            if f and st.button("Import HS"):
                d = pd.read_excel(f)
                rows = []
                for _, r in d.iterrows():
                    if str(r['Email']) not in df_users['Email'].values:
                        rows.append([str(r['Email']), "123", "HocSinh", str(r['HoTen']), my_class, str(r['EmailPH']), 0])
                batch_append('Users', rows)
                st.success("Xong!")
                st.rerun()

    with t2: # Duyệt OKR
        # Xử lý yêu cầu xóa
        del_reqs = df_okr_class[df_okr_class['YeuCauXoa'].astype(str) == 'TRUE']
        if not del_reqs.empty:
            st.warning("Có yêu cầu xóa OKR:")
            for i, r in del_reqs.iterrows():
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f"{r['Email']}: {r['MucTieu']}")
                if cc2.button("Xóa", key=f"d_{r['ID']}"):
                    df_okr = df_okr[df_okr['ID'] != r['ID']]
                    save_df('OKRs', df_okr)
                    st.rerun()
            st.divider()

        # Duyệt từng HS
        sel_hs = st.selectbox("Chọn HS duyệt bài:", df_hs['Email'])
        hs_okrs = df_okr_class[df_okr_class['Email'] == sel_hs]
        
        if hs_okrs.empty: st.info("Chưa có OKR.")
        else:
            for i, r in hs_okrs.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"**{r['MucTieu']}**")
                    c1.caption(f"Target: {r['MucTieuSo']} {r['DonVi']} | Đạt: {r['ThucDat']}")
                    
                    new_cmt = c1.text_input("Nhận xét:", value=str(r['NhanXet_GV']), key=f"c_{r['ID']}", disabled=not is_open)
                    new_stt = c2.selectbox("Trạng thái", ["Chờ duyệt", "Đã duyệt", "Cần sửa"], 
                                           index=["Chờ duyệt", "Đã duyệt", "Cần sửa"].index(r['TrangThai']) if r['TrangThai'] in ["Chờ duyệt", "Đã duyệt", "Cần sửa"] else 0,
                                           key=f"s_{r['ID']}", disabled=not is_open)
                    
                    if is_open and c2.button("Lưu", key=f"sv_{r['ID']}"):
                        idx = df_okr[df_okr['ID'] == r['ID']].index[0]
                        df_okr.at[idx, 'NhanXet_GV'] = new_cmt
                        df_okr.at[idx, 'TrangThai'] = new_stt
                        save_df('OKRs', df_okr)
                        st.success("Đã lưu!")
                        st.rerun()

    with t3: # Đánh giá CK
        sel_hs_rv = st.selectbox("Chọn HS đánh giá:", df_hs['Email'], key="rv_sel")
        rev_row = df_rev[(df_rev['Email'] == sel_hs_rv) & (df_rev['Dot'] == period)]
        old_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else ""
        
        st.write(f"Đánh giá tổng kết cho: **{sel_hs_rv}**")
        with st.form("rv_form"):
            txt = st.text_area("Nhận xét:", value=old_txt, disabled=not is_open)
            if st.form_submit_button("Lưu Đánh Giá"):
                if is_open:
                    if rev_row.empty: append_row('Reviews', [sel_hs_rv, period, txt, ""])
                    else:
                        ridx = rev_row.index[0]
                        df_rev.at[ridx, 'NhanXet_CuoiKy'] = txt
                        save_df('Reviews', df_rev)
                    st.success("Lưu thành công")
                    st.rerun()

    with t4: # Báo cáo
        if st.button("Tải Báo Cáo Cả Lớp (.docx)"):
            hs_data = df_hs.to_dict('records')
            bio = generate_word_report(hs_data, df_okr, df_rev, period)
            st.download_button("Download", bio, f"OKR_Lop_{my_class}.docx")

# --- C. STUDENT ---
def student_module(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    st.caption(f"Đợt: {period} | Trạng thái: {'Mở' if is_open else 'Khóa'}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    
    # Tạo mới
    if is_open:
        with st.expander("➕ Đăng ký OKR mới"):
            with st.form("new_okr"):
                obj = st.text_input("Mục tiêu")
                kr = st.text_area("Kết quả then chốt (KR)")
                c1, c2 = st.columns(2)
                tgt = c1.number_input("Mục tiêu số", min_value=0.0)
                unit = c2.text_input("Đơn vị")
                if st.form_submit_button("Gửi"):
                    if obj and kr:
                        uid = uuid.uuid4().hex[:8]
                        # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai, DelReq, GVL1
                        row = [uid, user['Email'], user['Lop'], period, obj, kr, tgt, 0.0, unit, 0.0, "Chờ duyệt", "FALSE", ""]
                        append_row('OKRs', row)
                        st.success("Đã gửi!")
                        st.rerun()

    # Danh sách
    st.subheader("Tiến độ của em")
    if my_okrs.empty: st.info("Chưa có OKR.")
    else:
        for i, r in my_okrs.iterrows():
            with st.container(border=True):
                stt_col = "orange" if r['TrangThai']=="Chờ duyệt" else "green" if r['TrangThai']=="Đã duyệt" else "red"
                st.markdown(f"#### {r['MucTieu']} <span style='color:{stt_col}'>({r['TrangThai']})</span>", unsafe_allow_html=True)
                st.text(f"KR: {r['KetQuaThenChot']}")
                if r['NhanXet_GV']: st.info(f"💡 GV: {r['NhanXet_GV']}")
                
                # Update
                c1, c2 = st.columns([3, 1])
                with c1:
                    cur_act = float(r['ThucDat'])
                    if is_open and r['TrangThai'] == "Đã duyệt":
                        new_act = st.number_input(f"Đạt ({r['DonVi']})", value=cur_act, key=f"v_{r['ID']}")
                        prog = calculate_progress(new_act, r['MucTieuSo'])
                    else:
                        st.write(f"Đạt: {cur_act} {r['DonVi']}")
                        new_act = cur_act
                        prog = r['TienDo']
                    st.progress(int(prog))
                    st.caption(f"{prog:.1f}%")
                
                with c2:
                    if is_open and r['TrangThai'] == "Đã duyệt":
                        if st.button("Update", key=f"up_{r['ID']}"):
                            idx = df_okr[df_okr['ID'] == r['ID']].index[0]
                            df_okr.at[idx, 'ThucDat'] = new_act
                            df_okr.at[idx, 'TienDo'] = prog
                            save_df('OKRs', df_okr)
                            st.success("Lưu!")
                            st.rerun()
                    
                    if is_open and r['YeuCauXoa'] == 'FALSE':
                        if st.button("Xin xóa", key=f"dx_{r['ID']}"):
                            idx = df_okr[df_okr['ID'] == r['ID']].index[0]
                            df_okr.at[idx, 'YeuCauXoa'] = 'TRUE'
                            save_df('OKRs', df_okr)
                            st.rerun()

# --- D. PARENT ---
def parent_module(period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 Phụ huynh em: {user['ChildName']}")
    st.info(f"Đang xem đợt: {period}")
    
    df_okr = load_data('OKRs')
    child_okrs = df_okr[(df_okr['Email'] == user['ChildEmail']) & (df_okr['Dot'] == period)]
    
    st.subheader("Kết quả học tập")
    if child_okrs.empty: st.write("Chưa có dữ liệu.")
    else:
        df_view = child_okrs[['MucTieu', 'KetQuaThenChot', 'ThucDat', 'MucTieuSo', 'DonVi', 'TienDo', 'TrangThai']].copy()
        df_view['TienDo'] = df_view['TienDo'].apply(lambda x: f"{x:.1f}%")
        st.table(df_view)
        
    st.divider()
    df_rev = load_data('Reviews')
    rev_row = df_rev[(df_rev['Email'] == user['ChildEmail']) & (df_rev['Dot'] == period)]
    
    gv_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else "Chưa có."
    st.write(f"🧑‍🏫 GVCN: {gv_txt}")
    
    ph_old = rev_row.iloc[0]['PhanHoi_PH'] if not rev_row.empty else ""
    with st.form("ph_form"):
        fb = st.text_area("Ý kiến gia đình:", value=ph_old)
        if st.form_submit_button("Gửi phản hồi"):
            if rev_row.empty: append_row('Reviews', [user['ChildEmail'], period, "", fb])
            else:
                idx = rev_row.index[0]
                df_rev.at[idx, 'PhanHoi_PH'] = fb
                save_df('Reviews', df_rev)
            st.success("Đã gửi!")
            st.rerun()

# =============================================================================
# MAIN RUN
# =============================================================================

def main():
    if not st.session_state.user:
        login_ui()
    else:
        period, is_open = sidebar_controller()
        role = st.session_state.user['Role']
        
        if role == 'Admin':
            admin_module(period, is_open)
        elif role == 'GiaoVien':
            teacher_module(period, is_open)
        elif role == 'HocSinh':
            student_module(period, is_open)
        elif role == 'PhuHuynh':
            parent_module(period, is_open)
        else:
            st.error("Lỗi quyền truy cập.")

if __name__ == "__main__":
    main()
