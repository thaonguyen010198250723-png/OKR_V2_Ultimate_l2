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
# 1. CẤU HÌNH & KHỞI TẠO (CONFIG & INIT)
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường Học",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Hằng số hệ thống
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
MASTER_ADMIN = {"email": "admin@school.com", "pass": "123"}
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/3209/3209265.png"

# Cấu trúc dữ liệu chuẩn (Schema Definition) - Tự động migration
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH'],
    'Periods': ['TenDot', 'TrangThai'], # TrangThai: "Mở" / "Khóa"
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV'],
    'Reviews': ['Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH']
}

if 'user' not in st.session_state:
    st.session_state.user = None

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU & CACHE (DATA LAYER)
# =============================================================================

def get_client():
    """Kết nối Google API với Error Handling"""
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
    """Load data với cơ chế tự động sửa Schema"""
    client = get_client()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # Init sheet mới nếu chưa có
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA[sheet_name])
            return pd.DataFrame(columns=SCHEMA[sheet_name])

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # --- AUTO MIGRATION: Thêm cột thiếu ---
        expected = SCHEMA[sheet_name]
        changed = False
        if not df.empty:
            for col in expected:
                if col not in df.columns:
                    df[col] = "" if col not in ['MucTieuSo', 'ThucDat', 'TienDo'] else 0.0
                    changed = True
            
            # Reorder columns
            df = df[[c for c in expected if c in df.columns] + [c for c in df.columns if c not in expected]]
        else:
            # Nếu DF rỗng nhưng header trong sheet có thể sai, force trả về đúng schema
            return pd.DataFrame(columns=expected)

        # --- TYPE CASTING ---
        if sheet_name == 'OKRs':
            for c in ['MucTieuSo', 'ThucDat', 'TienDo']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            df['Lop'] = df['Lop'].astype(str)
        
        if sheet_name == 'Users':
            df['Password'] = df['Password'].astype(str)
            df['Lop'] = df['Lop'].astype(str)

        return df
    except Exception as e:
        st.error(f"Lỗi tải {sheet_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

def save_df(sheet_name, df):
    """Ghi đè Sheet (Dùng cho Sửa/Xóa)"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu {sheet_name}: {e}")
        return False

def append_row(sheet_name, row_list):
    """Thêm dòng mới an toàn"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        # Convert all to string to avoid JSON errors, except numbers
        safe_row = [str(x) if x is not None and not isinstance(x, (int, float)) else x for x in row_list]
        ws.append_row(safe_row, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi thêm dữ liệu: {e}")
        return False

def batch_append(sheet_name, list_of_lists):
    """Import hàng loạt"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi import: {e}")
        return False

# =============================================================================
# 3. UTILITIES & REPORTING
# =============================================================================

def calculate_progress(actual, target):
    try:
        a, t = float(actual), float(target)
        if t == 0: return 100.0 if a > 0 else 0.0
        return min((a / t) * 100.0, 100.0)
    except:
        return 0.0

def generate_word(hs_data_list, df_okr, df_rev, period):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    for i, hs in enumerate(hs_data_list):
        doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {period}", 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Học sinh: {hs['HoTen']} - Lớp: {hs['Lop']}")
        doc.add_paragraph("-" * 50)
        
        # Table OKR
        doc.add_heading('I. KẾT QUẢ OKR', level=1)
        sub_okr = df_okr[(df_okr['Email'] == hs['Email']) & (df_okr['Dot'] == period)]
        
        if not sub_okr.empty:
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            hdr[0].text = 'Mục Tiêu'
            hdr[1].text = 'KR'
            hdr[2].text = 'Đích'
            hdr[3].text = 'Đạt'
            hdr[4].text = '%'
            hdr[5].text = 'Kết quả'
            
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
            
        if i < len(hs_data_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. GIAO DIỆN CHUNG & SIDEBAR (CORE UI)
# =============================================================================

def sidebar_controller():
    """Điều khiển Sidebar: Hiển thị User Info và Global Period Filter"""
    with st.sidebar:
        st.image(LOGO_URL, width=80)
        st.markdown("### TRƯỜNG HỌC OKR")
        st.divider()
        
        user = st.session_state.user
        st.markdown(f"👤 **{user['HoTen']}**")
        st.caption(f"Vai trò: {user['Role']}")
        
        # --- GLOBAL FILTER: CHỌN ĐỢT ---
        st.divider()
        st.markdown("📅 **CHỌN ĐỢT ĐÁNH GIÁ**")
        
        df_periods = load_data('Periods')
        period_list = df_periods['TenDot'].tolist() if not df_periods.empty else []
        
        # Logic chọn đợt mặc định: Lấy đợt "Mở" đầu tiên hoặc đợt mới nhất
        default_idx = 0
        if not df_periods.empty:
            open_periods = df_periods[df_periods['TrangThai'] == 'Mở']
            if not open_periods.empty:
                default_period = open_periods.iloc[0]['TenDot']
                if default_period in period_list:
                    default_idx = period_list.index(default_period)

        if not period_list:
            st.warning("Chưa có Đợt nào được tạo.")
            selected_period = "Chưa có"
            is_open = False
        else:
            selected_period = st.selectbox("Đợt:", period_list, index=default_idx, label_visibility="collapsed")
            
            # Check trạng thái đợt
            status_row = df_periods[df_periods['TenDot'] == selected_period]
            status_val = status_row.iloc[0]['TrangThai'] if not status_row.empty else "Khóa"
            is_open = (status_val == "Mở")
            
            if is_open:
                st.success(f"Trạng thái: {status_val} 🟢")
            else:
                st.error(f"Trạng thái: {status_val} 🔒")

        st.divider()
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.user = None
            st.rerun()
            
        return selected_period, is_open

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏫 CỔNG QUẢN LÝ OKR</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container(border=True):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.button("Đăng nhập", use_container_width=True)
            
            if submit:
                # 1. Master Login
                if email == MASTER_ADMIN['email'] and password == MASTER_ADMIN['pass']:
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Quản trị viên'}
                    st.rerun()
                
                # 2. DB Login
                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu người dùng.")
                    return

                # Check Normal User (Admin/GV/HS)
                user_match = df[(df['Email'] == email) & (df['Password'] == password)]
                
                if not user_match.empty:
                    st.session_state.user = user_match.iloc[0].to_dict()
                    st.rerun()
                
                # Check Parent (Login by PH Email, Check if linked to any student)
                # PH không có pass riêng, tạm thời dùng pass của con hoặc fix logic khác.
                # Theo yêu cầu: PH đăng nhập bằng EmailPH.
                # Logic: Tìm xem EmailPH này có tồn tại ko, check pass khớp với pass của con ko.
                
                ph_match = df[(df['EmailPH'] == email) & (df['Password'] == password)]
                if not ph_match.empty:
                    child = ph_match.iloc[0]
                    st.session_state.user = {
                        'Email': email, # Email PH
                        'Role': 'PhuHuynh',
                        'HoTen': f"PH em {child['HoTen']}",
                        'ChildEmail': child['Email'],
                        'ChildName': child['HoTen']
                    }
                    st.rerun()
                
                st.error("Sai Email hoặc Mật khẩu.")

# =============================================================================
# 5. CÁC MODULE CHỨC NĂNG (FEATURE MODULES)
# =============================================================================

# --- ADMIN MODULE ---
def admin_module(selected_period, is_open):
    st.title("🛡️ Admin Dashboard")
    tab1, tab2, tab3 = st.tabs(["⚙️ Quản Lý Đợt", "👨‍🏫 Quản Lý Giáo Viên", "📊 Thống Kê"])
    
    # 1. Quản Lý Đợt
    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("Tạo Đợt Mới")
            with st.form("new_period"):
                new_p = st.text_input("Tên đợt (VD: HK1_2024)")
                submit_p = st.form_submit_button("Tạo")
                if submit_p and new_p:
                    df_p = load_data('Periods')
                    if new_p not in df_p['TenDot'].values:
                        append_row('Periods', [new_p, "Mở"])
                        st.success("Đã tạo!")
                        st.rerun()
                    else:
                        st.error("Tên đợt trùng!")
        
        with c2:
            st.subheader("Danh sách Đợt")
            df_p = load_data('Periods')
            if not df_p.empty:
                # Cho phép đổi trạng thái
                for i, row in df_p.iterrows():
                    col_name, col_status, col_act = st.columns([2, 1, 1])
                    col_name.write(f"**{row['TenDot']}**")
                    col_status.write(f"`{row['TrangThai']}`")
                    
                    btn_label = "Khóa" if row['TrangThai'] == "Mở" else "Mở"
                    if col_act.button(f"Đổi sang {btn_label}", key=f"p_{i}"):
                        df_p.at[i, 'TrangThai'] = btn_label
                        save_df('Periods', df_p)
                        st.rerun()

    # 2. Quản Lý Giáo Viên
    with tab2:
        df_users = load_data('Users')
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        
        col_list, col_add = st.columns([2, 1])
        with col_list:
            st.subheader("Danh sách GV")
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop']])
            
            with st.expander("🗑️ Xóa Giáo Viên"):
                del_gv = st.selectbox("Chọn GV xóa", df_gv['Email'])
                if st.button("Xác nhận xóa GV"):
                    df_users = df_users[df_users['Email'] != del_gv]
                    save_df('Users', df_users)
                    st.success("Đã xóa!")
                    st.rerun()

        with col_add:
            st.subheader("Thêm Giáo Viên")
            tab_man, tab_excel = st.tabs(["Thủ công", "Excel"])
            with tab_man:
                with st.form("add_gv"):
                    e = st.text_input("Email")
                    n = st.text_input("Họ tên")
                    l = st.text_input("Lớp CN")
                    if st.form_submit_button("Lưu"):
                        if e not in df_users['Email'].values:
                            append_row('Users', [e, "123", "GiaoVien", n, l, ""])
                            st.success("Đã thêm!")
                            st.rerun()
                        else:
                            st.error("Email trùng!")
            with tab_excel:
                f = st.file_uploader("Upload Excel", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f) # Cols: Email, HoTen, Lop
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            rows.append([str(r['Email']), "123", "GiaoVien", str(r['HoTen']), str(r['Lop']), ""])
                    batch_append('Users', rows)
                    st.success(f"Thêm {len(rows)} GV.")
                    st.rerun()

    # 3. Thống Kê
    with tab3:
        st.info(f"Đang xem số liệu đợt: **{selected_period}**")
        df_okr = load_data('OKRs')
        df_okr_period = df_okr[df_okr['Dot'] == selected_period]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng OKR", len(df_okr_period))
        m2.metric("Đã Duyệt", len(df_okr_period[df_okr_period['TrangThai'] == 'Đã duyệt']))
        m3.metric("Hoàn thành", len(df_okr_period[df_okr_period['TienDo'] == 100.0]))

# --- TEACHER MODULE ---
def teacher_module(selected_period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    
    st.title(f"👩‍🏫 GVCN: {user['HoTen']}")
    if not my_class:
        st.error("Tài khoản chưa có Lớp. Liên hệ Admin.")
        return
    st.info(f"Lớp: **{my_class}** | Đợt đang chọn: **{selected_period}**")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Quản Lý HS", "✅ Duyệt OKR", "📝 Đánh Giá Cuối Kỳ", "🖨️ Báo Cáo"])
    
    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    
    df_okr = load_data('OKRs')
    # Filter by Class AND Period
    df_okr_view = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == selected_period)]
    
    df_rev = load_data('Reviews')

    # 1. Quản lý HS
    with tab1:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
        with c2:
            with st.expander("Thêm HS"):
                f = st.file_uploader("Excel HS", type=['xlsx'])
                if f and st.button("Import HS"):
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            rows.append([str(r['Email']), "123", "HocSinh", str(r['HoTen']), my_class, str(r['EmailPH'])])
                    batch_append('Users', rows)
                    st.success("Xong!")
                    st.rerun()
            
            with st.expander("Xóa / Reset Pass"):
                act_hs = st.selectbox("Chọn HS", df_hs['Email'])
                if st.button("Reset Pass (123)"):
                    idx = df_users[df_users['Email'] == act_hs].index[0]
                    df_users.at[idx, 'Password'] = "123"
                    save_df('Users', df_users)
                    st.success("Đã reset!")
                
                if st.button("Xóa HS", type="primary"):
                    df_users = df_users[df_users['Email'] != act_hs]
                    save_df('Users', df_users)
                    st.success("Đã xóa!")
                    st.rerun()

    # 2. Duyệt OKR
    with tab2:
        # Xử lý yêu cầu xóa
        del_reqs = df_okr_view[df_okr_view['YeuCauXoa'].astype(str) == 'TRUE']
        if not del_reqs.empty:
            st.warning(f"Có {len(del_reqs)} yêu cầu xóa OKR")
            for i, row in del_reqs.iterrows():
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f"HS: {row['Email']} - {row['MucTieu']}")
                if cc2.button("Đồng ý xóa", key=f"del_{row['ID']}"):
                    df_okr = df_okr[df_okr['ID'] != row['ID']]
                    save_df('OKRs', df_okr)
                    st.rerun()
            st.divider()

        # Duyệt danh sách
        hs_list = df_hs['Email'].unique()
        sel_hs = st.selectbox("Chọn Học Sinh để duyệt:", hs_list)
        
        okr_hs = df_okr_view[df_okr_view['Email'] == sel_hs]
        if okr_hs.empty:
            st.caption("HS này chưa có OKR.")
        else:
            for i, row in okr_hs.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    c1.markdown(f"**{row['MucTieu']}**")
                    c1.caption(f"Target: {row['MucTieuSo']} {row['DonVi']} | Đạt: {row['ThucDat']}")
                    
                    # Edit Fields
                    cmt = c2.text_input("Nhận xét GV", value=str(row['NhanXet_GV']), key=f"c_{row['ID']}", disabled=not is_open)
                    status = c3.selectbox("Trạng thái", ["Chờ duyệt", "Đã duyệt", "Cần sửa"], 
                                          index=["Chờ duyệt", "Đã duyệt", "Cần sửa"].index(row['TrangThai']) if row['TrangThai'] in ["Chờ duyệt", "Đã duyệt", "Cần sửa"] else 0,
                                          key=f"s_{row['ID']}", disabled=not is_open)
                    
                    if is_open and st.button("Lưu thay đổi", key=f"sv_{row['ID']}"):
                        # Update main DF
                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                        df_okr.at[idx, 'NhanXet_GV'] = cmt
                        df_okr.at[idx, 'TrangThai'] = status
                        save_df('OKRs', df_okr)
                        st.success("Đã lưu!")
                        time.sleep(0.5)
                        st.rerun()

    # 3. Đánh Giá Cuối Kỳ
    with tab3:
        sel_hs_rev = st.selectbox("Chọn HS đánh giá", hs_list, key="rev_sel")
        
        # Load OKR Stats
        hs_okr_stats = df_okr_view[df_okr_view['Email'] == sel_hs_rev]
        if not hs_okr_stats.empty:
            avg = hs_okr_stats['TienDo'].mean()
            st.progress(int(avg))
            st.caption(f"Tiến độ trung bình: {avg:.1f}%")
        
        # Review Form
        rev_row = df_rev[(df_rev['Email'] == sel_hs_rev) & (df_rev['Dot'] == selected_period)]
        old_val = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else ""
        ph_val = rev_row.iloc[0]['PhanHoi_PH'] if not rev_row.empty else "(Chưa có)"
        
        st.info(f"Phản hồi PH: {ph_val}")
        
        with st.form("teacher_rev"):
            txt = st.text_area("Nhận xét tổng kết:", value=old_val, disabled=not is_open)
            if st.form_submit_button("Lưu Đánh Giá"):
                if is_open:
                    if rev_row.empty:
                        append_row('Reviews', [sel_hs_rev, selected_period, txt, ""])
                    else:
                        ridx = rev_row.index[0]
                        df_rev.at[ridx, 'NhanXet_CuoiKy'] = txt
                        save_df('Reviews', df_rev)
                    st.success("Đã lưu!")
                    st.rerun()
                else:
                    st.error("Đợt đã khóa!")

    # 4. Xuất Báo Cáo
    with tab4:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Tải phiếu cá nhân (HS đang chọn)"):
                hs_obj = df_hs[df_hs['Email'] == sel_hs].iloc[0].to_dict()
                bio = generate_word([hs_obj], df_okr, df_rev, selected_period)
                st.download_button("Download Docx", bio, f"OKR_{sel_hs}.docx")
        with c2:
            if st.button(f"Tải phiếu CẢ LỚP ({len(df_hs)} HS)"):
                hs_full = df_hs.to_dict('records')
                bio = generate_word(hs_full, df_okr, df_rev, selected_period)
                st.download_button("Download Class Docx", bio, f"OKR_Lop_{my_class}.docx")

# --- STUDENT MODULE ---
def student_module(selected_period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    st.caption(f"Đợt: {selected_period} | Trạng thái: {'Mở' if is_open else 'Khóa'}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == selected_period)]
    
    # 1. Tạo Mới
    if is_open:
        with st.expander("➕ Đăng ký Mục Tiêu Mới"):
            with st.form("new_okr_hs"):
                obj = st.text_input("Mục tiêu")
                kr = st.text_area("Kết quả then chốt")
                c1, c2 = st.columns(2)
                tgt = c1.number_input("Mục tiêu số", min_value=0.0)
                unit = c2.text_input("Đơn vị (VD: Điểm)")
                
                if st.form_submit_button("Lưu"):
                    new_id = uuid.uuid4().hex[:8]
                    # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai, DelReq, GVL1
                    row = [new_id, user['Email'], user['Lop'], selected_period, obj, kr, tgt, 0.0, unit, 0.0, "Chờ duyệt", "FALSE", ""]
                    append_row('OKRs', row)
                    st.success("Đã thêm!")
                    st.rerun()
    
    # 2. Danh sách & Cập nhật
    st.subheader("Tiến độ của em")
    if my_okrs.empty:
        st.info("Chưa có OKR nào trong đợt này.")
    else:
        for i, row in my_okrs.iterrows():
            with st.container(border=True):
                # Header
                stt_color = "orange" if row['TrangThai'] == "Chờ duyệt" else "green" if row['TrangThai'] == "Đã duyệt" else "red"
                st.markdown(f"#### {row['MucTieu']} <span style='color:{stt_color}'>({row['TrangThai']})</span>", unsafe_allow_html=True)
                st.text(f"KR: {row['KetQuaThenChot']}")
                
                if row['NhanXet_GV']:
                    st.info(f"💡 GV: {row['NhanXet_GV']}")
                
                # Update Progress (Only if Open and Approved)
                cols = st.columns([3, 1])
                with cols[0]:
                    cur_act = float(row['ThucDat'])
                    cur_tgt = float(row['MucTieuSo'])
                    
                    if is_open and row['TrangThai'] == "Đã duyệt":
                        new_act = st.number_input(f"Thực đạt ({row['DonVi']})", value=cur_act, key=f"act_{row['ID']}")
                        if new_act != cur_act:
                            # Auto save logic via button to avoid reruns on typing
                            pass
                    else:
                        st.write(f"Đạt: **{cur_act} / {cur_tgt} {row['DonVi']}**")
                        new_act = cur_act
                        
                    progress = calculate_progress(new_act, cur_tgt)
                    st.progress(int(progress))
                    st.caption(f"{progress:.1f}%")

                with cols[1]:
                    if is_open:
                        if row['TrangThai'] == "Đã duyệt":
                            if st.button("Cập nhật", key=f"up_{row['ID']}"):
                                idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                df_okr.at[idx, 'ThucDat'] = new_act
                                df_okr.at[idx, 'TienDo'] = progress
                                save_df('OKRs', df_okr)
                                st.success("Lưu!")
                                st.rerun()
                                
                        if row['YeuCauXoa'] == 'FALSE':
                            if st.button("Xin xóa", key=f"req_{row['ID']}"):
                                idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                df_okr.at[idx, 'YeuCauXoa'] = 'TRUE'
                                save_df('OKRs', df_okr)
                                st.rerun()
                        else:
                            st.warning("Đã xin xóa")

# --- PARENT MODULE ---
def parent_module(selected_period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 Phụ huynh em: {user['ChildName']}")
    st.info(f"Đang xem kết quả đợt: **{selected_period}**")
    
    child_email = user['ChildEmail']
    df_okr = load_data('OKRs')
    child_okrs = df_okr[(df_okr['Email'] == child_email) & (df_okr['Dot'] == selected_period)]
    
    # View OKRs
    st.subheader("Kết quả học tập")
    if child_okrs.empty:
        st.write("Chưa có dữ liệu.")
    else:
        # Simple Table View
        display_df = child_okrs[['MucTieu', 'KetQuaThenChot', 'ThucDat', 'MucTieuSo', 'DonVi', 'TienDo', 'TrangThai']].copy()
        display_df['TienDo'] = display_df['TienDo'].apply(lambda x: f"{x:.1f}%")
        st.table(display_df)
    
    st.divider()
    
    # Reviews
    st.subheader("Trao đổi")
    df_rev = load_data('Reviews')
    rev_row = df_rev[(df_rev['Email'] == child_email) & (df_rev['Dot'] == selected_period)]
    
    gv_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else "Chưa có nhận xét."
    st.write(f"🧑‍🏫 **GVCN:** {gv_txt}")
    
    ph_old = rev_row.iloc[0]['PhanHoi_PH'] if not rev_row.empty else ""
    with st.form("ph_fb"):
        fb = st.text_area("Ý kiến gia đình:", value=ph_old)
        if st.form_submit_button("Gửi phản hồi"):
            if rev_row.empty:
                append_row('Reviews', [child_email, selected_period, "", fb])
            else:
                idx = rev_row.index[0]
                df_rev.at[idx, 'PhanHoi_PH'] = fb
                save_df('Reviews', df_rev)
            st.success("Đã gửi!")
            st.rerun()

# =============================================================================
# 6. MAIN APP FLOW
# =============================================================================

def main():
    if not st.session_state.user:
        login_ui()
    else:
        # Sidebar Controls
        period, is_open = sidebar_controller()
        role = st.session_state.user['Role']
        
        # Routing
        if role == 'Admin':
            admin_module(period, is_open)
        elif role == 'GiaoVien':
            teacher_module(period, is_open)
        elif role == 'HocSinh':
            student_module(period, is_open)
        elif role == 'PhuHuynh':
            parent_module(period, is_open)
        else:
            st.error("Quyền truy cập không hợp lệ.")

if __name__ == "__main__":
    main()
