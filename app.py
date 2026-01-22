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
# 1. CẤU HÌNH & SCHEMA (GIỮ NGUYÊN)
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR",
    layout="wide",
    initial_sidebar_state="expanded"
)

SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "logo FSC.png"

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
# 2. XỬ LÝ DỮ LIỆU & BACKEND (GIỮ NGUYÊN CŨ + THÊM HÀM MỚI)
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
        expected_cols = SCHEMA[sheet_name]
        if df.empty: return pd.DataFrame(columns=expected_cols)
        for col in expected_cols:
            if col not in df.columns:
                val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH'] else ""
                df[col] = val
        df = df[[c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]]
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

# --- SAFE FUNCTIONS FOR USERS (GIỮ NGUYÊN TỪ PHIÊN BẢN TRƯỚC) ---

def safe_delete_user(email):
    try:
        client = get_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet('Users')
        cell = ws.find(email, in_column=1)
        if cell:
            ws.delete_rows(cell.row)
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"Lỗi xóa user: {e}")
        return False

def safe_update_user(email, col_name, new_val):
    try:
        client = get_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet('Users')
        headers = SCHEMA['Users']
        try: col_idx = headers.index(col_name) + 1
        except ValueError: return False
        cell = ws.find(email, in_column=1)
        if cell:
            ws.update_cell(cell.row, col_idx, new_val)
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"Lỗi cập nhật user: {e}")
        return False

# --- 🔥 NEW: SAFE UPDATE FOR OKR PROGRESS (NHIỆM VỤ 1) ---

def safe_update_okr_progress(okr_id, new_actual, new_progress):
    """
    Cập nhật tiến độ OKR an toàn bằng cách tìm chính xác ID trên Sheet.
    Không dùng save_df để tránh ghi đè dữ liệu.
    """
    try:
        client = get_client()
        sh = client.open_by_key(SHEET_ID)
        ws = sh.worksheet('OKRs')
        
        # Tìm ô chứa ID (Cột 1)
        cell = ws.find(okr_id, in_column=1)
        
        if cell:
            # Cột 8: ThucDat, Cột 10: TienDo (Theo Schema 1-based index)
            # Schema: ID, Email, Lop, Dot, MucTieu, KR, Target, ThucDat(8), Unit, TienDo(10)...
            
            # Cập nhật ThucDat
            ws.update_cell(cell.row, 8, new_actual)
            # Cập nhật TienDo
            ws.update_cell(cell.row, 10, new_progress)
            
            clear_cache()
            return True
        return False
    except Exception as e:
        st.error(f"Lỗi cập nhật tiến độ: {e}")
        return False

# --- LEGACY HELPERS ---

def save_df(sheet_name, df):
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
# 3. UTILITIES & SIDEBAR (GIỮ NGUYÊN)
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
        p = doc.add_heading(f"PHIẾU ĐÁNH GIÁ OKR - {period}", 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Học sinh: {hs['HoTen']} - Lớp: {hs['Lop']}")
        doc.add_paragraph("-" * 60)
        doc.add_heading('I. KẾT QUẢ OKR', level=1)
        sub_okr = df_okr[(df_okr['Email'] == hs['Email']) & (df_okr['Dot'] == period)]
        if not sub_okr.empty:
            table = doc.add_table(rows=1, cols=6)
            table.style = 'Table Grid'
            hdr = table.rows[0].cells
            headers = ['Mục Tiêu', 'KR', 'Đích', 'Đạt', '%', 'PH chấm']
            for j, h in enumerate(headers): hdr[j].text = h
            for _, row in sub_okr.iterrows():
                cells = table.add_row().cells
                cells[0].text = str(row['MucTieu'])
                cells[1].text = str(row['KetQuaThenChot'])
                cells[2].text = f"{row['MucTieuSo']} {row['DonVi']}"
                cells[3].text = str(row['ThucDat'])
                cells[4].text = f"{row['TienDo']:.1f}%"
                stars = int(row['DiemHaiLong_PH'])
                cells[5].text = "★" * stars if stars > 0 else "-"
        else: doc.add_paragraph("(Chưa có dữ liệu OKR)")
        doc.add_heading('II. TỔNG KẾT & PHẢN HỒI', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        gv_cmt, ph_cmt = "", ""
        if not sub_rev.empty:
            r = sub_rev.iloc[0]
            gv_cmt = r['NhanXet_CuoiKy']
            ph_cmt = r['PhanHoi_PH']
        doc.add_paragraph(f"1. Nhận xét của GVCN:")
        doc.add_paragraph(gv_cmt if gv_cmt else "...")
        doc.add_paragraph(f"2. Ý kiến của Gia đình:")
        doc.add_paragraph(ph_cmt if ph_cmt else "...")
        if i < len(hs_data_list) - 1: doc.add_page_break()
    bio = BytesIO()
    doc.save(bio)
    return bio

def sidebar_controller():
    with st.sidebar:
        try: st.image(LOGO_URL, width=80)
        except: st.write("**FPT SCHOOL OKR**")
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            st.divider()
            st.markdown("📅 **ĐỢT ĐÁNH GIÁ**")
            df_p = load_data('Periods')
            p_opts = df_p['TenDot'].tolist() if not df_p.empty else []
            if not p_opts: return None, False
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts: idx = p_opts.index(opens[0])
            sel_period = st.selectbox("Chọn đợt:", p_opts, index=idx, label_visibility="collapsed")
            status = df_p[df_p['TenDot'] == sel_period].iloc[0]['TrangThai']
            is_open = (status == 'Mở')
            if is_open: st.success(f"Trạng thái: {status} 🟢")
            else: st.error(f"Trạng thái: {status} 🔒")
            with st.expander("🔑 Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        target = u['ChildEmail'] if u['Role'] == 'PhuHuynh' else u['Email']
                        if safe_update_user(target, 'Password', np):
                            st.success("Đổi thành công!")
                        else: st.error("Lỗi cập nhật.")
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
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    st.rerun()
                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu.")
                    return
                match = df[(df['Email'] == email) & (df['Password'] == password)]
                if not match.empty:
                    st.session_state.user = match.iloc[0].to_dict()
                    st.rerun()
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
# 4. ADMIN MODULE (GIỮ NGUYÊN)
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["⚙️ Quản lý Đợt", "📊 Thống kê Lớp", "👨‍🏫 Giáo Viên"])
    with t1:
        st.subheader("Danh sách Đợt")
        with st.form("new_p"):
            c1, c2 = st.columns([3, 1])
            np = c1.text_input("Tên đợt mới (VD: HocKy1_2024)", label_visibility="collapsed")
            if c2.form_submit_button("➕ Tạo đợt", use_container_width=True):
                df_p = load_data('Periods')
                if np and np not in df_p['TenDot'].values:
                    append_row('Periods', [np, "Mở"])
                    st.success("Tạo thành công!")
                    st.rerun()
        df_periods = load_data('Periods')
        if not df_periods.empty:
            for i, r in df_periods.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1.5, 1.5])
                    c1.write(f"**{r['TenDot']}**")
                    stt = r['TrangThai']
                    c2.markdown(f":green[**Mở**]" if stt=="Mở" else f":red[**Khóa**]")
                    if c3.button("Đổi trạng thái", key=f"tg_{i}"):
                        df_periods.at[i, 'TrangThai'] = "Khóa" if stt=="Mở" else "Mở"
                        save_df('Periods', df_periods)
                        st.rerun()
    with t2:
        st.subheader(f"Bảng Thống Kê Tiến Độ - {period}")
        df_users = load_data('Users')
        df_okr = load_data('OKRs')
        df_okr_period = df_okr[df_okr['Dot'] == period]
        df_gv = df_users[df_users['Role'] == 'GiaoVien']
        if df_gv.empty: st.warning("Chưa có dữ liệu Giáo viên.")
        else:
            stats_data = []
            for _, gv in df_gv.iterrows():
                lop = str(gv['Lop'])
                gv_name = gv['HoTen']
                try: siso = int(gv['SiSo'])
                except: siso = 0
                okrs_of_class = df_okr_period[df_okr_period['Lop'] == lop]
                hs_submitted_count = okrs_of_class['Email'].nunique()
                hs_approved_emails = okrs_of_class[okrs_of_class['TrangThai'] == 'Đã duyệt']['Email'].unique()
                hs_approved_count = len(hs_approved_emails)
                pct_submit = (hs_submitted_count / siso * 100) if siso > 0 else 0
                pct_approve = (hs_approved_count / siso * 100) if siso > 0 else 0
                stats_data.append({
                    "Lớp": lop, "GVCN": gv_name, "Sĩ Số": siso,
                    "Đã Nộp": f"{hs_submitted_count} ({pct_submit:.0f}%)",
                    "Đã Duyệt": f"{hs_approved_count} ({pct_approve:.0f}%)"
                })
            st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)
    with t3:
        df_gv = load_data('Users')
        df_gv = df_gv[df_gv['Role'] == 'GiaoVien']
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
            if not df_gv.empty:
                del_gv = st.selectbox("Chọn GV xóa", df_gv['Email'])
                if st.button("Xóa GV", type="primary"):
                    if safe_delete_user(del_gv):
                        st.success("Đã xóa!")
                        st.rerun()
                    else: st.error("Lỗi xóa.")
        with c2:
            st.write("Thêm GV")
            with st.form("add_gv"):
                e = st.text_input("Email")
                n = st.text_input("Tên")
                l = st.text_input("Lớp")
                s = st.number_input("Sĩ số", 0)
                if st.form_submit_button("Thêm"):
                    df_check = load_data('Users')
                    if e not in df_check['Email'].values:
                        append_row('Users', [e, "123", "GiaoVien", n, l, "", s])
                        st.success("OK")
                        st.rerun()
            with st.expander("Import Excel"):
                f = st.file_uploader("XLSX", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f)
                    rows = []
                    df_check = load_data('Users')
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_check['Email'].values:
                            s_val = int(r['SiSo']) if 'SiSo' in r and pd.notnull(r['SiSo']) else 0
                            rows.append([str(r['Email']), "123", "GiaoVien", str(r['HoTen']), str(r['Lop']), "", s_val])
                    batch_append('Users', rows)
                    st.success("OK")
                    st.rerun()

# =============================================================================
# 5. TEACHER MODULE (GIỮ NGUYÊN)
# =============================================================================

def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    st.title(f"👩‍🏫 COMMAND CENTER: LỚP {my_class}")
    if not my_class:
        st.error("Tài khoản chưa có Lớp.")
        return
    df_users_all = load_data('Users')
    df_hs = df_users_all[(df_users_all['Role'] == 'HocSinh') & (df_users_all['Lop'] == my_class)]
    df_okr = load_data('OKRs')
    df_okr_class = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    df_rev = load_data('FinalReviews')
    df_rev_class = df_rev[(df_rev['Dot'] == period)]
    t_main, t_hs, t_report = st.tabs(["🚀 Duyệt & Đánh Giá (All-in-One)", "👥 Quản Lý Học Sinh", "🖨️ Báo Cáo"])

    with t_main:
        if df_hs.empty: st.info("Lớp chưa có học sinh.")
        else:
            st.markdown(f"**Danh sách học sinh ({len(df_hs)}) - Đợt: {period}**")
            for idx, hs in df_hs.iterrows():
                email_hs = hs['Email']
                name_hs = hs['HoTen']
                hs_okrs = df_okr_class[df_okr_class['Email'] == email_hs]
                hs_rev = df_rev_class[df_rev_class['Email'] == email_hs]
                icon = "🔴"
                status_text = "Chưa nộp"
                if not hs_okrs.empty:
                    total_okr = len(hs_okrs)
                    approved = len(hs_okrs[hs_okrs['TrangThai'] == 'Đã duyệt'])
                    if approved == total_okr:
                        icon = "🟢"
                        status_text = "Đã duyệt OKR"
                    else:
                        icon = "🟡"
                        status_text = "Chờ duyệt OKR"
                is_finalized = False
                if not hs_rev.empty and hs_rev.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
                    icon = "✅"
                    status_text = "Đã chốt sổ"
                    is_finalized = True
                elif not hs_rev.empty:
                    icon = "⏳"
                    status_text = "Đang đánh giá"
                with st.expander(f"{icon} {name_hs} ({status_text})"):
                    st.markdown("##### 1. Duyệt Mục Tiêu (OKR)")
                    if hs_okrs.empty: st.warning("Học sinh chưa tạo OKR.")
                    else:
                        for _, row in hs_okrs.iterrows():
                            c1, c2, c3 = st.columns([3, 1.5, 1.5])
                            c1.markdown(f"**{row['MucTieu']}** - {row['KetQuaThenChot']}")
                            c1.caption(f"Target: {row['MucTieuSo']} {row['DonVi']} | Actual: {row['ThucDat']}")
                            stt = row['TrangThai']
                            color = "green" if stt == "Đã duyệt" else "orange" if stt == "Chờ duyệt" else "red"
                            c2.markdown(f":{color}[**{stt}**]")
                            if is_open:
                                if row['YeuCauXoa'] == 'TRUE':
                                    c3.error("❗ Xin xóa")
                                    if c3.button("Đồng ý xóa", key=f"del_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr = df_okr.drop(idx)
                                        save_df('OKRs', df_okr)
                                        st.rerun()
                                else:
                                    if stt != "Đã duyệt" and c3.button("✅ Phê duyệt", key=f"app_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr.at[idx, 'TrangThai'] = "Đã duyệt"
                                        save_df('OKRs', df_okr)
                                        st.rerun()
                                    if stt != "Cần sửa" and c3.button("⚠️ Yêu cầu sửa", key=f"rej_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr.at[idx, 'TrangThai'] = "Cần sửa"
                                        save_df('OKRs', df_okr)
                                        st.rerun()
                        st.divider()
                    st.markdown("##### 2. Đánh Giá & Chốt Sổ")
                    curr_txt = hs_rev.iloc[0]['NhanXet_CuoiKy'] if not hs_rev.empty else ""
                    ph_fb = hs_rev.iloc[0]['PhanHoi_PH'] if not hs_rev.empty else "Chưa có phản hồi."
                    st.info(f"👪 Phụ huynh phản hồi: {ph_fb}")
                    with st.form(key=f"rev_form_{email_hs}"):
                        txt_input = st.text_area("Nhận xét của GV:", value=curr_txt, disabled=not is_open)
                        check_final = st.checkbox("Chốt sổ (Hoàn thành đánh giá)", value=is_finalized, disabled=not is_open)
                        if st.form_submit_button("💾 Lưu Nhận Xét"):
                            if is_open:
                                stt_val = "Đã chốt" if check_final else "Chưa chốt"
                                if hs_rev.empty:
                                    append_row('FinalReviews', [email_hs, period, txt_input, "", stt_val])
                                else:
                                    ridx = df_rev[(df_rev['Email'] == email_hs) & (df_rev['Dot'] == period)].index[0]
                                    df_rev.at[ridx, 'NhanXet_CuoiKy'] = txt_input
                                    df_rev.at[ridx, 'TrangThai_CuoiKy'] = stt_val
                                    save_df('FinalReviews', df_rev)
                                st.success("Đã lưu thành công!")
                                st.rerun()

    with t_hs:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])
            st.markdown("#### 🛠️ Sửa HS")
            sel_hs = st.selectbox("Chọn HS:", df_hs['Email'] if not df_hs.empty else [])
            if sel_hs:
                with st.form("edit_hs"):
                    ne = st.text_input("Email HS mới")
                    np = st.text_input("Email PH mới")
                    rst = st.checkbox("Reset Pass (123)")
                    dele = st.checkbox("Xóa Tài khoản")
                    if st.form_submit_button("Thực hiện"):
                        if dele:
                            if safe_delete_user(sel_hs):
                                st.success("Đã xóa!")
                                st.rerun()
                            else: st.error("Lỗi xóa.")
                        else:
                            success = True
                            if ne: 
                                if not safe_update_user(sel_hs, 'Email', ne): success = False
                            if np: 
                                if not safe_update_user(sel_hs, 'EmailPH', np): success = False
                            if rst: 
                                if not safe_update_user(sel_hs, 'Password', '123'): success = False
                            
                            if success:
                                st.success("Cập nhật thành công!")
                                st.rerun()
                            else: st.error("Lỗi cập nhật.")
        with c2:
            st.markdown("#### ➕ Thêm HS")
            with st.form("add_hs_manual"):
                e = st.text_input("Email")
                n = st.text_input("Họ tên")
                ph = st.text_input("Email PH")
                if st.form_submit_button("Thêm"):
                    if e not in df_users_all['Email'].values:
                        append_row('Users', [e, "123", "HocSinh", n, my_class, ph, 0])
                        st.success("Thêm thành công!")
                        st.rerun()
                    else: st.error("Email trùng.")
            with st.expander("Import Excel"):
                f = st.file_uploader("XLSX", type=['xlsx'])
                if f and st.button("Import"):
                    d = pd.read_excel(f)
                    rows = []
                    for _, r in d.iterrows():
                        if str(r['Email']) not in df_users_all['Email'].values:
                            rows.append([str(r['Email']), "123", "HocSinh", str(r['HoTen']), my_class, str(r['EmailPH']), 0])
                    batch_append('Users', rows)
                    st.success("OK")
                    st.rerun()

    with t_report:
        c1, c2 = st.columns(2)
        with c1:
            sel_exp = st.selectbox("HS lẻ:", df_hs['Email'] if not df_hs.empty else [])
            if st.button("Word (1 HS)"):
                hs_obj = df_hs[df_hs['Email'] == sel_exp].iloc[0].to_dict()
                bio = generate_word_report([hs_obj], df_okr, df_rev, period)
                st.download_button("Download", bio, f"OKR_{sel_exp}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with c2:
            st.write("Cả lớp")
            if st.button("Word (All)"):
                hs_full = df_hs.to_dict('records')
                bio = generate_word_report(hs_full, df_okr, df_rev, period)
                st.download_button("Download Class", bio, f"OKR_{my_class}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# =============================================================================
# 6. STUDENT MODULE (FIXED & SAFE UPDATE)
# =============================================================================

def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    df_rev = load_data('FinalReviews')
    rev = df_rev[(df_rev['Email'] == user['Email']) & (df_rev['Dot'] == period)]

    # 1. REVIEW & FEEDBACK
    st.markdown("### 📝 Tổng kết & Đánh giá")
    gv_txt = "Chưa có nhận xét."
    status_txt = "Chưa chốt"
    if not rev.empty:
        if rev.iloc[0]['NhanXet_CuoiKy']: gv_txt = rev.iloc[0]['NhanXet_CuoiKy']
        status_txt = rev.iloc[0]['TrangThai_CuoiKy']
    
    st.info(f"**🧑‍🏫 Nhận xét của Giáo viên ({status_txt}):**\n\n{gv_txt}")
    
    ph_txt = "Chưa có phản hồi."
    if not rev.empty and rev.iloc[0]['PhanHoi_PH']: ph_txt = rev.iloc[0]['PhanHoi_PH']
    st.warning(f"**👨‍👩‍👧‍👦 Phản hồi của Phụ huynh:**\n\n{ph_txt}")
    st.divider()

    # 2. CREATE OKR (USE UUID)
    if is_open:
        with st.expander("➕ Thêm Mục Tiêu & KR mới", expanded=True):
            with st.form("new_okr_hs"):
                existing_objs = my_okrs['MucTieu'].unique().tolist()
                c_obj1, c_obj2 = st.columns([1, 1])
                obj_input = c_obj1.text_input("Mục tiêu (Mới hoặc copy tên cũ)", placeholder="VD: Học tập tốt")
                if existing_objs: c_obj2.info(f"Mục tiêu đã có: {', '.join(existing_objs)}")
                
                kr_input = st.text_input("Kết quả then chốt (KR)")
                c1, c2 = st.columns(2)
                tgt = c1.number_input("Mục tiêu số", min_value=0.0)
                unit = c2.text_input("Đơn vị")
                
                if st.form_submit_button("Lưu OKR"):
                    if obj_input and kr_input:
                        is_dup = not my_okrs[(my_okrs['MucTieu'] == obj_input) & (my_okrs['KetQuaThenChot'] == kr_input)].empty
                        if is_dup: st.error("❌ OKR này đã tồn tại!")
                        else:
                            uid = str(uuid.uuid4())
                            append_row('OKRs', [uid, user['Email'], user['Lop'], period, obj_input, kr_input, tgt, 0.0, unit, 0.0, "Chờ duyệt", "FALSE", "", 0, ""])
                            st.success("✅ Đã thêm thành công!")
                            time.sleep(0.5)
                            st.rerun()
                    else: st.warning("Vui lòng nhập đủ thông tin.")

    # 3. LIST & UPDATE (USE SAFE UPDATE)
    st.subheader("Tiến độ của em")
    if my_okrs.empty: st.info("Chưa có OKR nào.")
    else:
        objectives = my_okrs['MucTieu'].unique()
        for obj in objectives:
            with st.container(border=True):
                st.markdown(f"### 🎯 {obj}")
                krs = my_okrs[my_okrs['MucTieu'] == obj]
                
                for _, row in krs.iterrows():
                    st.divider()
                    stt_color = "green" if row['TrangThai'] == 'Đã duyệt' else "orange"
                    st.markdown(f"**KR: {row['KetQuaThenChot']}** <span style='color:{stt_color}'>({row['TrangThai']})</span>", unsafe_allow_html=True)
                    
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.caption(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                    
                    current_act = float(row['ThucDat'])
                    
                    if is_open and row['TrangThai'] == 'Đã duyệt':
                        new_act = c2.number_input(
                            label=f"Thực đạt ({row['DonVi']})",
                            min_value=0.0,
                            value=current_act,
                            step=0.01,
                            format="%.2f",
                            key=f"act_{row['ID']}",
                            label_visibility="collapsed"
                        )
                        prog_display = calculate_progress(new_act, row['MucTieuSo'])
                        c2.progress(int(prog_display))
                        c2.caption(f"{prog_display:.1f}%")

                        if c3.button("Cập nhật", key=f"btn_up_{row['ID']}"):
                            # SAFE UPDATE CALL
                            if safe_update_okr_progress(row['ID'], new_act, prog_display):
                                st.success("✅ Đã lưu!")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("Lỗi cập nhật. Vui lòng thử lại.")
                    else:
                        c2.progress(int(row['TienDo']))
                        c2.write(f"Đạt: {current_act}")
                        if row['TrangThai'] != 'Đã duyệt': c3.info("Chờ duyệt")

                    if is_open:
                        if row['YeuCauXoa'] == 'FALSE':
                            if c3.button("Xin xóa", key=f"req_{row['ID']}"):
                                idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                df_okr.at[idx, 'YeuCauXoa'] = 'TRUE'
                                save_df('OKRs', df_okr)
                                st.rerun()
                        else: c3.warning("Đã xin xóa")
                    
                    if row['NhanXet_GV']: st.caption(f"💡 GV: {row['NhanXet_GV']}")
                    if row['DiemHaiLong_PH'] > 0: st.caption(f"⭐ PH chấm: {int(row['DiemHaiLong_PH'])} sao")

# =============================================================================
# 7. MODULE: PARENT (GIỮ NGUYÊN)
# =============================================================================

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
    gv_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else "Chưa có."
    st.info(f"🧑‍🏫 GV Nhận xét: {gv_txt}")
    ph_old = rev_row.iloc[0]['PhanHoi_PH'] if not rev_row.empty else ""
    with st.form("ph_fb"):
        txt = st.text_area("Ý kiến gia đình:", value=ph_old)
        if st.form_submit_button("Gửi phản hồi"):
            if rev_row.empty: append_row('FinalReviews', [user['ChildEmail'], period, "", txt, "Chưa chốt"])
            else:
                idx = rev_row.index[0]
                df_rev.at[idx, 'PhanHoi_PH'] = txt
                save_df('FinalReviews', df_rev)
            st.success("Đã gửi!")
            st.rerun()

# =============================================================================
# 8. MAIN EXECUTION
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
