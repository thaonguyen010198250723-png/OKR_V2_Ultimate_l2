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
# 1. CẤU HÌNH & SCHEMA
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "logoFSC.png"

# Schema chuẩn
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
    """Load data & Auto-Schema Migration"""
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
        
        # --- AUTO MIGRATION: Fill missing columns ---
        expected_cols = SCHEMA[sheet_name]
        if df.empty: return pd.DataFrame(columns=expected_cols)

        for col in expected_cols:
            if col not in df.columns:
                val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH'] else ""
                df[col] = val
        
        # Reorder & Clean
        df = df[[c for c in expected_cols if c in df.columns] + [c for c in df.columns if c not in expected_cols]]

        # Type Casting
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
    """
    ⚠️ DANGER: Hàm này ghi đè toàn bộ Sheet. 
    Chỉ dùng khi đã load TOÀN BỘ dữ liệu và chỉ sửa 1 vài dòng cụ thể.
    """
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
    """
    ✅ SAFE: Hàm này chỉ thêm vào cuối Sheet, không ảnh hưởng dữ liệu cũ.
    """
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
# 3. UTILITIES & SIDEBAR
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
        else: doc.add_paragraph("(Trống)")

        doc.add_heading('II. PHẢN HỒI', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        gv_cmt, ph_cmt = "", ""
        if not sub_rev.empty:
            gv_cmt = sub_rev.iloc[0]['NhanXet_CuoiKy']
            ph_cmt = sub_rev.iloc[0]['PhanHoi_PH']
        doc.add_paragraph(f"GVCN: {gv_cmt}")
        doc.add_paragraph(f"Gia đình: {ph_cmt}")
        if i < len(hs_data_list) - 1: doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

def sidebar_controller():
    with st.sidebar:
        st.image(LOGO_URL, width=80)
        st.markdown("### FPT SCHOOL OKR")
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
                        df_u = load_data('Users')
                        target = u['ChildEmail'] if u['Role'] == 'PhuHuynh' else u['Email']
                        mask = df_u['Email'] == target
                        if mask.any():
                            df_u.loc[mask, 'Password'] = np
                            save_df('Users', df_u)
                            st.success("Đổi thành công!")
            st.divider()
            if st.button("Đăng xuất"):
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
# 4. ADMIN MODULE
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["⚙️ Quản lý Đợt", "📊 Thống kê", "👨‍🏫 Giáo Viên"])
    
    with t1:
        st.subheader("Danh sách Đợt")
        with st.form("new_p"):
            c1, c2 = st.columns([3, 1])
            np = c1.text_input("Tên đợt mới (VD: HocKy1)", label_visibility="collapsed")
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
                    if c3.button("Khóa" if stt=="Mở" else "Mở lại", key=f"tg_{i}"):
                        df_periods.at[i, 'TrangThai'] = "Khóa" if stt=="Mở" else "Mở"
                        save_df('Periods', df_periods)
                        st.rerun()

    with t2:
        st.subheader(f"Tiến độ - {period}")
        df_u = load_data('Users')
        df_o = load_data('OKRs')
        df_o_p = df_o[df_o['Dot'] == period]
        df_gv = df_u[df_u['Role'] == 'GiaoVien']
        
        stats = []
        for _, gv in df_gv.iterrows():
            lop = str(gv['Lop'])
            siso = int(gv['SiSo'])
            okrs_cls = df_o_p[df_o_p['Lop'] == lop]
            
            submitted = okrs_cls['Email'].nunique()
            approved = okrs_cls[okrs_cls['TrangThai']=='Đã duyệt']['Email'].nunique()
            
            stt_cls = "🔴 Chưa nộp"
            if siso > 0 and approved >= siso: stt_cls = "✅ Hoàn thành"
            elif submitted > 0: stt_cls = "⚠️ Đang xử lý"
            
            stats.append({
                "Lớp": lop, "GVCN": gv['HoTen'], "Sĩ số": siso,
                "Đã nộp": f"{submitted}", "Đã duyệt": f"{approved}", "Trạng thái": stt_cls
            })
        st.dataframe(pd.DataFrame(stats), use_container_width=True, hide_index=True)

    with t3:
        df_gv = load_data('Users')
        df_gv = df_gv[df_gv['Role'] == 'GiaoVien']
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_gv[['Email', 'HoTen', 'Lop', 'SiSo']])
            if not df_gv.empty:
                del_gv = st.selectbox("Chọn GV xóa", df_gv['Email'])
                if st.button("Xóa GV", type="primary"):
                    df_all = load_data('Users')
                    df_all = df_all[df_all['Email'] != del_gv]
                    save_df('Users', df_all)
                    st.success("Đã xóa!")
                    st.rerun()
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
# 5. TEACHER MODULE (SAFE SAVE IMPLEMENTED)
# =============================================================================

def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    st.title(f"👩‍🏫 GVCN Lớp {my_class}")
    if not my_class:
        st.error("Tài khoản chưa có Lớp.")
        return

    # Load Data Scope
    df_users_all = load_data('Users') # Load ALL users for safe editing
    df_hs_class = df_users_all[(df_users_all['Role'] == 'HocSinh') & (df_users_all['Lop'] == my_class)]
    
    df_okr = load_data('OKRs')
    df_okr_class = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    df_rev = load_data('FinalReviews')

    t1, t2, t3 = st.tabs(["📋 Học Sinh (An Toàn)", "✅ Duyệt OKR (Group)", "📝 Đánh Giá CK"])

    # --- TAB 1: QUẢN LÝ HS (SAFE LOGIC) ---
    with t1:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(df_hs_class[['Email', 'HoTen', 'EmailPH']])
            
            st.markdown("#### 🛠️ Sửa thông tin HS")
            hs_select = st.selectbox("Chọn HS:", df_hs_class['Email'] if not df_hs_class.empty else [])
            
            if hs_select:
                with st.form("edit_hs_form"):
                    col_e1, col_e2 = st.columns(2)
                    new_email_hs = col_e1.text_input("Email HS mới", placeholder="Giữ nguyên nếu không đổi")
                    new_email_ph = col_e2.text_input("Email PH mới", placeholder="Giữ nguyên nếu không đổi")
                    
                    c_act1, c_act2 = st.columns(2)
                    req_reset = c_act1.checkbox("Reset Mật khẩu (về 123)")
                    req_delete = c_act2.checkbox("❌ Xóa Tài khoản này")
                    
                    if st.form_submit_button("Thực hiện thay đổi"):
                        # ⚠️ CRITICAL: Find index in the GLOBAL DATAFRAME
                        idx = df_users_all[df_users_all['Email'] == hs_select].index
                        
                        if not idx.empty:
                            real_idx = idx[0]
                            
                            if req_delete:
                                df_users_all = df_users_all.drop(real_idx)
                                save_df('Users', df_users_all)
                                st.success("Đã xóa tài khoản!")
                                st.rerun()
                            else:
                                if new_email_hs:
                                    df_users_all.at[real_idx, 'Email'] = new_email_hs
                                if new_email_ph:
                                    df_users_all.at[real_idx, 'EmailPH'] = new_email_ph
                                if req_reset:
                                    df_users_all.at[real_idx, 'Password'] = "123"
                                
                                save_df('Users', df_users_all)
                                st.success("Cập nhật thành công!")
                                st.rerun()
                        else:
                            st.error("Không tìm thấy HS trong CSDL tổng.")

        with c2:
            st.markdown("#### ➕ Thêm HS (Append Mode)")
            with st.form("add_hs"):
                e = st.text_input("Email")
                n = st.text_input("Họ tên")
                p = st.text_input("Email PH")
                if st.form_submit_button("Thêm"):
                    if e not in df_users_all['Email'].values:
                        # Append Row is safe
                        append_row('Users', [e, "123", "HocSinh", n, my_class, p, 0])
                        st.success("Đã thêm!")
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
                    st.success("Xong!")
                    st.rerun()

    # --- TAB 2: DUYỆT OKR (GROUP VIEW) ---
    with t2:
        sel_hs = st.selectbox("Chọn Học Sinh:", df_hs_class['Email'] if not df_hs_class.empty else [])
        if sel_hs:
            hs_okrs = df_okr_class[df_okr_class['Email'] == sel_hs]
            if hs_okrs.empty:
                st.info("HS này chưa tạo OKR.")
            else:
                # Group by Objective
                objectives = hs_okrs['MucTieu'].unique()
                
                for obj in objectives:
                    with st.container(border=True):
                        st.markdown(f"**Mục tiêu: {obj}**")
                        krs = hs_okrs[hs_okrs['MucTieu'] == obj]
                        
                        for _, row in krs.iterrows():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            c1.text(f"- KR: {row['KetQuaThenChot']} ({row['MucTieuSo']} {row['DonVi']})")
                            c1.caption(f"Đạt: {row['ThucDat']} ({row['TienDo']}%)")
                            
                            # Status Badge
                            stt = row['TrangThai']
                            color = "green" if stt == "Đã duyệt" else "orange" if stt == "Chờ duyệt" else "red"
                            c2.markdown(f":{color}[**{stt}**]")
                            
                            # Action Buttons (Per KR)
                            if is_open:
                                if row['YeuCauXoa'] == 'TRUE':
                                    c3.warning("Xin xóa!")
                                    if c3.button("🗑️ Đồng ý", key=f"del_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr = df_okr.drop(idx)
                                        save_df('OKRs', df_okr)
                                        st.rerun()
                                else:
                                    if stt != "Đã duyệt" and c3.button("✅ Duyệt", key=f"app_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr.at[idx, 'TrangThai'] = "Đã duyệt"
                                        save_df('OKRs', df_okr)
                                        st.rerun()
                                    if stt != "Cần sửa" and c3.button("⚠️ Sửa", key=f"rej_{row['ID']}"):
                                        idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                        df_okr.at[idx, 'TrangThai'] = "Cần sửa"
                                        save_df('OKRs', df_okr)
                                        st.rerun()

    # --- TAB 3: ĐÁNH GIÁ CK ---
    with t3:
        sel_hs_rv = st.selectbox("Chọn HS đánh giá:", df_hs_class['Email'] if not df_hs_class.empty else [], key="rv_s")
        if sel_hs_rv:
            rev_row = df_rev[(df_rev['Email'] == sel_hs_rv) & (df_rev['Dot'] == period)]
            cur_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else ""
            
            with st.form("rv_form"):
                txt = st.text_area("Nhận xét tổng kết:", value=cur_txt, disabled=not is_open)
                if st.form_submit_button("Lưu Đánh Giá"):
                    if is_open:
                        if rev_row.empty:
                            append_row('FinalReviews', [sel_hs_rv, period, txt, "", "Chưa chốt"])
                        else:
                            idx = df_rev[(df_rev['Email'] == sel_hs_rv) & (df_rev['Dot'] == period)].index[0]
                            df_rev.at[idx, 'NhanXet_CuoiKy'] = txt
                            save_df('FinalReviews', df_rev)
                        st.success("Đã lưu!")
                        st.rerun()

# =============================================================================
# 6. STUDENT MODULE (DUPLICATE CHECK & 1-N GROUPING)
# =============================================================================

def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    
    # --- 1. CREATE OKR (Duplicate Check) ---
    if is_open:
        with st.expander("➕ Thêm Mục Tiêu & KR mới", expanded=True):
            with st.form("new_okr_hs"):
                # Suggest existing objectives to allow grouping
                existing_objs = my_okrs['MucTieu'].unique().tolist()
                
                c_obj1, c_obj2 = st.columns([1, 1])
                obj_input = c_obj1.text_input("Mục tiêu (Mới hoặc copy tên cũ)", placeholder="VD: Học tập tốt")
                if existing_objs:
                    c_obj2.info(f"Mục tiêu đã có: {', '.join(existing_objs)}")
                
                kr_input = st.text_input("Kết quả then chốt (KR)")
                c1, c2 = st.columns(2)
                tgt = c1.number_input("Mục tiêu số", min_value=0.0)
                unit = c2.text_input("Đơn vị")
                
                if st.form_submit_button("Lưu OKR"):
                    if obj_input and kr_input:
                        # DUPLICATE CHECK
                        is_dup = not my_okrs[(my_okrs['MucTieu'] == obj_input) & (my_okrs['KetQuaThenChot'] == kr_input)].empty
                        
                        if is_dup:
                            st.error("❌ OKR này (Mục tiêu + KR) đã tồn tại! Vui lòng kiểm tra lại.")
                        else:
                            uid = uuid.uuid4().hex[:8]
                            append_row('OKRs', [uid, user['Email'], user['Lop'], period, obj_input, kr_input, tgt, 0.0, unit, 0.0, "Chờ duyệt", "FALSE", "", 0, ""])
                            st.success("✅ Đã thêm thành công!")
                            time.sleep(0.5)
                            st.rerun()
                    else:
                        st.warning("Vui lòng nhập đủ thông tin.")

    # --- 2. LIST OKR (Grouped by Objective) ---
    st.subheader("Tiến độ của em")
    if my_okrs.empty:
        st.info("Chưa có OKR nào.")
    else:
        objs = my_okrs['MucTieu'].unique()
        for obj in objs:
            with st.container(border=True):
                st.markdown(f"### 🎯 {obj}")
                krs = my_okrs[my_okrs['MucTieu'] == obj]
                
                for _, row in krs.iterrows():
                    st.divider()
                    stt_color = "green" if row['TrangThai'] == 'Đã duyệt' else "orange"
                    st.markdown(f"**KR: {row['KetQuaThenChot']}** <span style='color:{stt_color}'>({row['TrangThai']})</span>", unsafe_allow_html=True)
                    
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.caption(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                    
                    cur_act = float(row['ThucDat'])
                    
                    # Update Progress logic
                    if is_open and row['TrangThai'] == 'Đã duyệt':
                        new_act = c2.number_input(f"Thực đạt ##{row['ID']}", value=cur_act, label_visibility="collapsed")
                        prog = calculate_progress(new_act, row['MucTieuSo'])
                        
                        c2.progress(int(prog))
                        c2.caption(f"{prog:.1f}%")
                        
                        if c3.button("Lưu", key=f"up_{row['ID']}"):
                            idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                            df_okr.at[idx, 'ThucDat'] = new_act
                            df_okr.at[idx, 'TienDo'] = prog
                            save_df('OKRs', df_okr)
                            st.success("Saved!")
                            st.rerun()
                    else:
                        c2.progress(int(row['TienDo']))
                        c2.write(f"Đạt: {cur_act}")
                    
                    # Delete Request logic
                    if is_open:
                        if row['YeuCauXoa'] == 'FALSE':
                            if c3.button("Xin xóa", key=f"req_{row['ID']}"):
                                idx = df_okr[df_okr['ID'] == row['ID']].index[0]
                                df_okr.at[idx, 'YeuCauXoa'] = 'TRUE'
                                save_df('OKRs', df_okr)
                                st.rerun()
                        else:
                            c3.warning("Đã xin xóa")

# =============================================================================
# 7. PARENT MODULE
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
    df_rev = load_data('FinalReviews')
    rev_row = df_rev[(df_rev['Email'] == user['ChildEmail']) & (df_rev['Dot'] == period)]
    
    gv_txt = rev_row.iloc[0]['NhanXet_CuoiKy'] if not rev_row.empty else "Chưa có."
    st.info(f"🧑‍🏫 GV Nhận xét: {gv_txt}")
    
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
