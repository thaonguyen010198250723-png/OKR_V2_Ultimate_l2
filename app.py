import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import time
import uuid

# =============================================================================
# 1. CẤU HÌNH & SCHEMA
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/3209/3209265.png"

# Schema chuẩn (Để tự động map và fix lỗi thiếu cột)
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'Periods': ['TenDot', 'TrangThai'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV', 'DiemHaiLong_PH'],
    'FinalReviews': ['Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH', 'TrangThai_CuoiKy']
}

if 'user' not in st.session_state:
    st.session_state.user = None

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU (BACKEND)
# =============================================================================

def get_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"🔴 Lỗi kết nối Google API: {e}")
        return None

@st.cache_data(ttl=10)
def load_data(sheet_name):
    """
    Load data và tự động Schema Migration (Thêm cột thiếu).
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
        
        # --- AUTO MIGRATION ---
        expected_cols = SCHEMA[sheet_name]
        
        # Nếu sheet trống
        if df.empty:
            return pd.DataFrame(columns=expected_cols)

        # Fill cột thiếu
        for col in expected_cols:
            if col not in df.columns:
                # Default values
                val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH'] else ""
                df[col] = val
        
        # Reorder columns & Drop extra columns (clean data)
        df = df[[c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]]

        # --- TYPE CASTING ---
        if sheet_name == 'Users':
            df['SiSo'] = pd.to_numeric(df['SiSo'], errors='coerce').fillna(0).astype(int)
            df['Password'] = df['Password'].astype(str)
            df['Lop'] = df['Lop'].astype(str)
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
    """Lưu toàn bộ DataFrame (Dùng cho Edit/Delete)"""
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
    """Thêm dòng mới (Dùng cho Create)"""
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        clean_row = []
        for x in row_data:
            if isinstance(x, (int, float)): clean_row.append(x)
            elif x is None: clean_row.append("")
            else: clean_row.append(str(x))
        
        ws.append_row(clean_row, value_input_option='USER_ENTERED')
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
# 3. UTILITIES & REPORTING
# =============================================================================

def calculate_progress(actual, target):
    try:
        t = float(target)
        a = float(actual)
        if t == 0: return 100.0 if a > 0 else 0.0
        return min((a / t) * 100.0, 100.0)
    except:
        return 0.0

def generate_word_report(hs_data_list, df_okr, df_rev, period):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)

    for i, hs in enumerate(hs_data_list):
        # Header
        p = doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {period}", 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph(f"Học sinh: {hs['HoTen']}")
        doc.add_paragraph(f"Lớp: {hs['Lop']} | Email: {hs['Email']}")
        doc.add_paragraph("-" * 60)
        
        # OKR Table
        doc.add_heading('I. KẾT QUẢ THỰC HIỆN MỤC TIÊU', level=1)
        sub_okr = df_okr[(df_okr['Email'] == hs['Email']) & (df_okr['Dot'] == period)]
        
        if not sub_okr.empty:
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            headers = ['Mục Tiêu', 'KR', 'Đích', 'Đạt', '%', 'PH chấm']
            for j, h in enumerate(headers):
                hdr[j].text = h
            
            for _, row in sub_okr.iterrows():
                cells = table.add_row().cells
                cells[0].text = str(row['MucTieu'])
                cells[1].text = str(row['KetQuaThenChot'])
                cells[2].text = f"{row['MucTieuSo']} {row['DonVi']}"
                cells[3].text = str(row['ThucDat'])
                cells[4].text = f"{row['TienDo']:.1f}%"
                
                stars = int(row['DiemHaiLong_PH'])
                cells[5].text = "★" * stars if stars > 0 else "-"
        else:
            doc.add_paragraph("(Chưa có dữ liệu OKR)")

        # Review Section
        doc.add_heading('II. TỔNG KẾT & PHẢN HỒI', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        
        gv_cmt = ""
        ph_cmt = ""
        status = "Chưa chốt"
        
        if not sub_rev.empty:
            r = sub_rev.iloc[0]
            gv_cmt = r['NhanXet_CuoiKy']
            ph_cmt = r['PhanHoi_PH']
            status = r['TrangThai_CuoiKy']

        doc.add_paragraph(f"1. Nhận xét của GVCN ({status}):")
        doc.add_paragraph(gv_cmt if gv_cmt else "...")
        
        doc.add_paragraph(f"2. Ý kiến của Gia đình:")
        doc.add_paragraph(ph_cmt if ph_cmt else "...")
        
        # Page break if not last student
        if i < len(hs_data_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. AUTH & SIDEBAR
# =============================================================================

def sidebar_controller():
    with st.sidebar:
        st.image(LOGO_URL, width=80)
        st.markdown("### SCHOOL OKR")
        
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            
            # Global Filter
            st.divider()
            st.markdown("📅 **ĐỢT ĐÁNH GIÁ**")
            df_p = load_data('Periods')
            
            p_opts = df_p['TenDot'].tolist() if not df_p.empty else []
            if not p_opts: return None, False
            
            # Select Default
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts:
                idx = p_opts.index(opens[0])
            
            sel_period = st.selectbox("Chọn đợt:", p_opts, index=idx, label_visibility="collapsed")
            status = df_p[df_p['TenDot'] == sel_period].iloc[0]['TrangThai']
            is_open = (status == 'Mở')
            
            if is_open: st.success(f"Trạng thái: {status} 🟢")
            else: st.error(f"Trạng thái: {status} 🔒")
            
            # Change Pass
            with st.expander("🔑 Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        df_u = load_data('Users')
                        target = u['ChildEmail'] if u['Role'] == 'PhuHuynh' else u['Email']
                        mask = df_u['Email'] == target
                        if mask.any():
                            df_u.loc[mask, 'Password'] = np
                            save_df('Users', df_u)
                            st.success("Đổi thành công!")
                        else: st.error("Lỗi user")
            
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
                # Master
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()
                
                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu.")
                    return

                # Normal User
                match = df[(df['Email'] == email) & (df['Password'] == password)]
                if not match.empty:
                    st.session_state.user = match.iloc[0].to_dict()
                    st.rerun()
                
                # Parent User
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
# 5. MODULES (ROLES)
# =============================================================================

# --- ADMIN ---
def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2 = st.tabs(["👨‍🏫 Quản lý GV", "⚙️ Quản lý Đợt"])
    
    with t1:
        df_users = load_data('Users')
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        
        c1, c2 = st.columns([3, 1])
        with c1:
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
        with c2:
            st.markdown("**Thêm GV**")
            with st.form("add_gv"):
                e = st.text_input("Email")
                n = st.text_input("Tên")
                l = st.text_input("Lớp")
                s = st.number_input("Sĩ số", min_value=0)
                if st.form_submit_button("Thêm"):
                    if e not in df_users['Email'].values:
                        append_row('Users', [e, "123", "GiaoVien", n, l, "", s])
                        st.success("OK")
                        st.rerun()
                    else: st.error("Trùng Email")
            
            st.divider()
            st.markdown("**Xóa GV**")
            if not df_gv.empty:
                del_gv = st.selectbox("Chọn GV xóa", df_gv['Email'])
                if st.button("Xác nhận xóa"):
                    df_users = df_users[df_users['Email'] != del_gv]
                    save_df('Users', df_users)
                    st.success("Đã xóa!")
                    st.rerun()
    
    with t2:
        df_p = load_data('Periods')
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("np"):
                new_p = st.text_input("Tên đợt mới")
                if st.form_submit_button("Tạo"):
                    if new_p not in df_p['TenDot'].values:
                        append_row('Periods', [new_p, "Mở"])
                        st.success("OK")
                        st.rerun()
        with c2:
            st.dataframe(df_p)

# --- TEACHER (REFACTORED) ---
def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    st.title(f"👩‍🏫 GVCN Lớp {my_class}")
    
    if not my_class:
        st.error("Tài khoản chưa có Lớp.")
        return

    # Load Context Data
    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    df_okr = load_data('OKRs')
    df_rev = load_data('FinalReviews')
    
    # Filter by Period
    df_okr_p = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    df_rev_p = df_rev[(df_rev['Dot'] == period)]

    t1, t2, t3 = st.tabs(["📋 Quản Lý Học Sinh", "✅ Duyệt & Đánh Giá", "🖨️ Báo Cáo"])

    # --- TAB 1: QUẢN LÝ HS ---
    with t1:
        st.caption(f"Tổng số tài khoản HS: {len(df_hs)}")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
            
            st.markdown("#### Thao tác tài khoản")
            sel_hs_act = st.selectbox("Chọn HS để thao tác", df_hs['Email'] if not df_hs.empty else [])
            
            if sel_hs_act:
                ca1, ca2, ca3 = st.columns(3)
                with ca1:
                    new_email = st.text_input("Đổi Email thành:", placeholder="Email mới...")
                    if st.button("Lưu Email"):
                        idx = df_users[df_users['Email'] == sel_hs_act].index[0]
                        df_users.at[idx, 'Email'] = new_email
                        save_df('Users', df_users)
                        st.success("Đã đổi Email!")
                        st.rerun()
                with ca2:
                    if st.button("Reset Pass (123)"):
                        idx = df_users[df_users['Email'] == sel_hs_act].index[0]
                        df_users.at[idx, 'Password'] = "123"
                        save_df('Users', df_users)
                        st.success("Đã reset!")
                with ca3:
                    if st.button("Xóa Tài Khoản", type="primary"):
                        df_users = df_users[df_users['Email'] != sel_hs_act]
                        save_df('Users', df_users)
                        st.success("Đã xóa!")
                        st.rerun()

        with c2:
            st.markdown("#### Thêm Học Sinh")
            with st.form("add_hs"):
                e = st.text_input("Email")
                n = st.text_input("Họ tên")
                p = st.text_input("Email PH")
                if st.form_submit_button("Thêm"):
                    if e not in df_users['Email'].values:
                        append_row('Users', [e, "123", "HocSinh", n, my_class, p, 0])
                        st.success("Đã thêm!")
                        st.rerun()
                    else: st.error("Trùng Email")
            
            with st.expander("Import Excel"):
                f = st.file_uploader("File XLSX", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users['Email'].values:
                            rows.append([str(r['Email']), "123", "HocSinh", str(r['HoTen']), my_class, str(r['EmailPH']), 0])
                    batch_append('Users', rows)
                    st.success("Xong!")
                    st.rerun()

    # --- TAB 2: DUYỆT OKR (COMMAND CENTER) ---
    with t2:
        st.markdown("### 🚦 Trạng thái lớp học")
        
        for _, hs in df_hs.iterrows():
            email = hs['Email']
            name = hs['HoTen']
            
            # Data Context
            okrs = df_okr_p[df_okr_p['Email'] == email]
            rev = df_rev_p[df_rev_p['Email'] == email]
            
            # Logic Nút 1: OKR Status
            total_okr = len(okrs)
            approved_okr = len(okrs[okrs['TrangThai'] == 'Đã duyệt'])
            
            if total_okr == 0:
                badge_okr = "🔴 Chưa có OKR"
            elif approved_okr == total_okr:
                badge_okr = f"🟢 Đã duyệt ({approved_okr}/{total_okr})"
            else:
                badge_okr = f"🟡 Chờ duyệt ({approved_okr}/{total_okr})"
            
            # Logic Nút 2: Final Review Status
            rev_stt = "⏳ Chưa chốt"
            if not rev.empty and rev.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
                rev_stt = "✅ Đã chốt"
            
            # UI Render
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 0.5])
                c1.markdown(f"**{name}**")
                c2.write(badge_okr)
                c3.write(rev_stt)
                
                # Detail Expander
                with st.expander(f"Chi tiết: {name}"):
                    # 1. OKR DETAIL
                    st.markdown("**Kết quả OKR & Đánh giá PH**")
                    if okrs.empty:
                        st.info("Chưa có dữ liệu.")
                    else:
                        for _, row in okrs.iterrows():
                            kc1, kc2, kc3 = st.columns([3, 1, 1])
                            kc1.markdown(f"- **{row['MucTieu']}** / {row['KetQuaThenChot']}")
                            kc1.caption(f"Đạt: {row['ThucDat']} / {row['MucTieuSo']} {row['DonVi']}")
                            
                            # Status Badge
                            stt_color = "green" if row['TrangThai'] == 'Đã duyệt' else "orange"
                            kc2.markdown(f":{stt_color}[{row['TrangThai']}]")
                            
                            # Parent Rating
                            stars = int(row['DiemHaiLong_PH'])
                            star_str = "★" * stars if stars > 0 else "Chưa chấm"
                            kc3.markdown(f"PH: {star_str}")
                        
                        # Bulk Action
                        st.divider()
                        with st.form(f"act_{email}"):
                            cmt = st.text_input("Nhận xét OKR:", value=str(okrs.iloc[0]['NhanXet_GV']), disabled=not is_open)
                            act = st.selectbox("Hành động:", ["Duyệt tất cả", "Yêu cầu sửa", "Giữ nguyên"], disabled=not is_open)
                            if st.form_submit_button("Lưu OKR"):
                                idxs = df_okr[df_okr['ID'].isin(okrs['ID'])].index
                                if act == "Duyệt tất cả": df_okr.loc[idxs, 'TrangThai'] = 'Đã duyệt'
                                elif act == "Yêu cầu sửa": df_okr.loc[idxs, 'TrangThai'] = 'Cần sửa'
                                df_okr.loc[idxs, 'NhanXet_GV'] = cmt
                                save_df('OKRs', df_okr)
                                st.success("Đã lưu!")
                                st.rerun()

                    st.divider()
                    
                    # 2. FINAL REVIEW
                    st.markdown("**Đánh giá Cuối Kỳ**")
                    cur_rev = rev.iloc[0]['NhanXet_CuoiKy'] if not rev.empty else ""
                    ph_fb = rev.iloc[0]['PhanHoi_PH'] if not rev.empty else "Chưa phản hồi"
                    st.caption(f"Gia đình phản hồi: {ph_fb}")
                    
                    with st.form(f"rev_{email}"):
                        txt = st.text_area("Nhận xét tổng kết:", value=cur_rev, disabled=not is_open)
                        fin = st.checkbox("Chốt kết quả?", value=(rev_stt == "✅ Đã chốt"), disabled=not is_open)
                        if st.form_submit_button("Lưu Đánh Giá"):
                            stt_val = "Đã chốt" if fin else "Chưa chốt"
                            if rev.empty:
                                append_row('FinalReviews', [email, period, txt, "", stt_val])
                            else:
                                ridx = df_rev[df_rev['Email'] == email].index[0] # Filtered by Period scope implicitly via rev logic if needed, but here simple email match in loop context
                                # Correct index finding:
                                ridx = df_rev[(df_rev['Email'] == email) & (df_rev['Dot'] == period)].index[0]
                                df_rev.at[ridx, 'NhanXet_CuoiKy'] = txt
                                df_rev.at[ridx, 'TrangThai_CuoiKy'] = stt_val
                                save_df('FinalReviews', df_rev)
                            st.success("Saved!")
                            st.rerun()

    # --- TAB 3: BÁO CÁO ---
    with t3:
        st.subheader("Xuất phiếu kết quả")
        
        c1, c2 = st.columns(2)
        with c1:
            sel_exp_hs = st.selectbox("Chọn HS xuất lẻ:", df_hs['Email'])
            if st.button("Tải Word (1 HS)"):
                hs_obj = df_hs[df_hs['Email'] == sel_exp_hs].iloc[0].to_dict()
                bio = generate_word_report([hs_obj], df_okr, df_rev, period)
                st.download_button("Download .docx", bio, f"OKR_{sel_exp_hs}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        
        with c2:
            st.write("Xuất toàn bộ lớp")
            if st.button("Tải Word (Cả lớp)"):
                hs_full = df_hs.to_dict('records')
                bio = generate_word_report(hs_full, df_okr, df_rev, period)
                st.download_button("Download All .docx", bio, f"OKR_Lop_{my_class}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# --- STUDENT ---
def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    
    # Review info
    df_rev = load_data('FinalReviews')
    rev = df_rev[(df_rev['Email'] == user['Email']) & (df_rev['Dot'] == period)]
    
    if is_open:
        with st.expander("➕ Thêm OKR mới"):
            with st.form("new_okr"):
                o = st.text_input("Mục tiêu")
                k = st.text_input("Key Result")
                t = st.number_input("Mục tiêu số", min_value=0.0)
                u = st.text_input("Đơn vị")
                if st.form_submit_button("Thêm"):
                    uid = uuid.uuid4().hex[:8]
                    # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, Actual, Unit, TienDo, TrangThai...
                    append_row('OKRs', [uid, user['Email'], user['Lop'], period, o, k, t, 0.0, u, 0.0, "Chờ duyệt", "FALSE", "", 0])
                    st.success("OK")
                    st.rerun()
    
    st.subheader("Tiến độ")
    if my_okrs.empty: st.info("Chưa có OKR")
    else:
        for _, row in my_okrs.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['MucTieu']}** - {row['KetQuaThenChot']}")
                
                c1, c2, c3 = st.columns([2, 2, 2])
                c1.info(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                
                # Logic: Update Actual -> Auto calc %
                cur_act = float(row['ThucDat'])
                if is_open and row['TrangThai'] == 'Đã duyệt':
                    new_act = c2.number_input(f"Thực đạt ({row['DonVi']})", value=cur_act, key=f"act_{row['ID']}")
                    
                    # Calc Progress
                    prog = 0.0
                    if row['MucTieuSo'] > 0:
                        prog = min((new_act / row['MucTieuSo']) * 100, 100.0)
                    
                    c2.progress(int(prog))
                    c2.caption(f"{prog:.1f}%")

                    if c3.button("Cập nhật", key=f"up_{row['ID']}"):
                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                        df_okr.at[idx, 'ThucDat'] = new_act
                        df_okr.at[idx, 'TienDo'] = prog
                        save_df('OKRs', df_okr)
                        st.success("Đã lưu!")
                        st.rerun()
                else:
                    c2.write(f"Đạt: {cur_act}")
                    c2.progress(int(row['TienDo']))
                    c3.write(f"Trạng thái: {row['TrangThai']}")

                # Feedback Display
                if row['NhanXet_GV']: st.caption(f"💡 GV: {row['NhanXet_GV']}")
                if not rev.empty: st.caption(f"👨‍👩‍👧‍👦 PH phản hồi chung: {rev.iloc[0]['PhanHoi_PH']}")

# --- PARENT ---
def parent_view(period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 PHHS: {user['ChildName']}")
    
    df_okr = load_data('OKRs')
    child_okrs = df_okr[(df_okr['Email'] == user['ChildEmail']) & (df_okr['Dot'] == period)]
    
    st.subheader("Đánh giá từng KR")
    if child_okrs.empty: st.info("Chưa có OKR")
    else:
        for _, row in child_okrs.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**KR:** {row['KetQuaThenChot']}")
                c1.caption(f"Tiến độ: {row['TienDo']}%")
                
                # Rating Slider
                cur_star = int(row['DiemHaiLong_PH']) if row['DiemHaiLong_PH'] > 0 else 3
                new_star = c2.slider(f"Sao ({row['ID']})", 1, 5, cur_star)
                
                if c2.button("Lưu sao", key=f"star_{row['ID']}"):
                    idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                    df_okr.at[idx, 'DiemHaiLong_PH'] = new_star
                    save_df('OKRs', df_okr)
                    st.success("Đã lưu!")

    st.divider()
    st.subheader("Phản hồi chung")
    df_rev = load_data('FinalReviews')
    rev_row = df_rev[(df_rev['Email'] == user['ChildEmail']) & (df_rev['Dot'] == period)]
    
    # Show GV Comment
    gv_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else "Chưa có."
    st.info(f"🧑‍🏫 GV Nhận xét: {gv_txt}")
    
    # Parent Feedback Input
    ph_old = rev_row.iloc[0]['PhanHoi_PH'] if not rev_row.empty else ""
    with st.form("ph_fb"):
        txt = st.text_area("Ý kiến gia đình:", value=ph_old)
        if st.form_submit_button("Gửi phản hồi"):
            if rev_row.empty:
                append_row('FinalReviews', [user['ChildEmail'], period, "", txt, "Chưa chốt"])
            else:
                idx = rev_row.index[0]
                df_rev.at[idx, 'PhanHoi_PH'] = txt
                save_df('FinalReviews', df_rev)
            st.success("Đã gửi!")
            st.rerun()

# =============================================================================
# MAIN
# =============================================================================

def main():
    if not st.session_state.user:
        login_ui()
    else:
        period, is_open = sidebar_controller()
        if not period:
            st.warning("Vui lòng liên hệ Admin tạo đợt.")
            return
            
        role = st.session_state.user['Role']
        if role == 'Admin': admin_view(period, is_open)
        elif role == 'GiaoVien': teacher_view(period, is_open)
        elif role == 'HocSinh': student_view(period, is_open)
        elif role == 'PhuHuynh': parent_view(period, is_open)

if __name__ == "__main__":
    main()
