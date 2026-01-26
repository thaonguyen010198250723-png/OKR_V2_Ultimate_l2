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
import datetime
import extra_streamlit_components as stx

# =============================================================================
# 1. CẤU HÌNH & KHỞI TẠO
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ẩn menu thừa
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display:none;}
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Cookie Manager (Trực tiếp để tránh lỗi Widget)
cookie_manager = stx.CookieManager()

# ID của Google Sheet (File cũ của anh)
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
LOGO_URL = "logo FSC.png"

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
# 2. XỬ LÝ DỮ LIỆU & BACKEND (GOOGLE SHEETS)
# =============================================================================

def get_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Lấy secret từ Streamlit Cloud
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        else:
            return None
    except Exception as e:
        st.error(f"🔴 Lỗi kết nối Google: {e}")
        return None

# Tối ưu Cache 10 phút để tránh lỗi Quota Exceeded
@st.cache_data(ttl=600)
def load_data(sheet_name):
    client = get_client()
    if not client: return pd.DataFrame()
    try:
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(sheet_name)
        except:
            # Tự tạo sheet nếu thiếu
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            ws.append_row(SCHEMA[sheet_name])
            return pd.DataFrame(columns=SCHEMA[sheet_name])
            
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Đảm bảo đủ cột
        expected = SCHEMA[sheet_name]
        if df.empty: return pd.DataFrame(columns=expected)
        
        for col in expected:
            if col not in df.columns:
                val = 0 if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH'] else ""
                df[col] = val
                
        # Sắp xếp cột
        df = df[[c for c in expected if c in df.columns] + [c for c in df.columns if c not in expected]]
        
        # Ép kiểu dữ liệu an toàn
        if sheet_name == 'Users':
            df['SiSo'] = pd.to_numeric(df['SiSo'], errors='coerce').fillna(0).astype(int)
            df['Password'] = df['Password'].astype(str)
            df['Lop'] = df['Lop'].astype(str)
        if sheet_name == 'OKRs':
            for c in ['MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
                
        return df
    except Exception as e:
        if "Quota exceeded" in str(e):
            st.error("⚠️ Hệ thống đang quá tải (Google hạn chế). Vui lòng đợi 1 phút.")
        return pd.DataFrame()

def clear_cache():
    st.cache_data.clear()

# --- CÁC HÀM GHI AN TOÀN (SAFE WRITE) ---

def safe_update_user(email, col_name, new_val):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet('Users')
        headers = ws.row_values(1)
        col_idx = headers.index(col_name) + 1
        cell = ws.find(email, in_column=1)
        if cell:
            ws.update_cell(cell.row, col_idx, new_val)
            clear_cache()
            return True
        return False
    except: return False

def safe_update_okr(okr_id, col_name, new_val):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet('OKRs')
        cell = ws.find(str(okr_id), in_column=1) # Tìm theo ID
        if cell:
            headers = ws.row_values(1)
            col_idx = headers.index(col_name) + 1
            ws.update_cell(cell.row, col_idx, new_val)
            clear_cache()
            return True
        return False
    except: return False

def append_row(sheet_name, row_data):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        # Làm sạch dữ liệu
        clean = []
        for x in row_data:
            if isinstance(x, (int, float)): clean.append(x)
            elif x is None: clean.append("")
            else: clean.append(str(x))
        ws.append_row(clean, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except: return False

def batch_append(sheet_name, list_data):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        ws.append_rows(list_data, value_input_option='USER_ENTERED')
        clear_cache()
        return True
    except: return False

def delete_row(sheet_name, col_val, col_index=1):
    try:
        client = get_client()
        ws = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        cell = ws.find(str(col_val), in_column=col_index)
        if cell:
            ws.delete_rows(cell.row)
            clear_cache()
            return True
        return False
    except: return False

# =============================================================================
# 3. HELPER FUNCTIONS
# =============================================================================

def calculate_progress(actual, target):
    try:
        t = float(target)
        a = float(actual)
        if t == 0: return 100.0 if a > 0 else 0.0
        return min((a / t) * 100.0, 100.0)
    except: return 0.0

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
            headers = ['Mục Tiêu', 'KR', 'Đích', 'Đạt', '%', 'Sao']
            for j, h in enumerate(headers): hdr[j].text = h
            for _, row in sub_okr.iterrows():
                cells = table.add_row().cells
                cells[0].text = str(row['MucTieu'])
                cells[1].text = str(row['KetQuaThenChot'])
                cells[2].text = f"{row['MucTieuSo']} {row['DonVi']}"
                cells[3].text = str(row['ThucDat'])
                cells[4].text = f"{row['TienDo']:.1f}%"
                cells[5].text = str(int(row['DiemHaiLong_PH']))
        else: doc.add_paragraph("(Chưa có dữ liệu)")
        
        doc.add_heading('II. NHẬN XÉT', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        t1, t2 = "", ""
        if not sub_rev.empty:
            t1 = sub_rev.iloc[0]['NhanXet_CuoiKy']
            t2 = sub_rev.iloc[0]['PhanHoi_PH']
        doc.add_paragraph(f"GVCN: {t1}")
        doc.add_paragraph(f"PHHS: {t2}")
        if i < len(hs_data_list) - 1: doc.add_page_break()
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. GIAO DIỆN & LOGIN
# =============================================================================

def sidebar_controller():
    # Auto Login check
    if not st.session_state.user:
        try:
            c_em = cookie_manager.get(cookie="user_email")
            if c_em:
                df = load_data('Users')
                if not df.empty:
                    m = df[df['Email'] == c_em]
                    if not m.empty:
                        st.session_state.user = m.iloc[0].to_dict()
                        st.rerun()
                    else:
                        pm = df[df['EmailPH'] == c_em]
                        if not pm.empty:
                            c = pm.iloc[0]
                            st.session_state.user = {
                                'Email': c_em, 'Role': 'PhuHuynh', 
                                'HoTen': f"PH {c['HoTen']}", 'ChildEmail': c['Email'], 'ChildName': c['HoTen']
                            }
                            st.rerun()
        except: pass

    with st.sidebar:
        try: st.image(LOGO_URL, width=80)
        except: st.write("**FPT SCHOOL**")
        
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            st.divider()
            
            df_p = load_data('Periods')
            if df_p.empty: return None, False
            p_opts = df_p['TenDot'].tolist()
            idx = 0
            opens = df_p[df_p['TrangThai']=='Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts: idx = p_opts.index(opens[0])
            
            sel_period = st.selectbox("Đợt:", p_opts, index=idx)
            row = df_p[df_p['TenDot'] == sel_period].iloc[0]
            is_open = (row['TrangThai'] == 'Mở')
            
            if is_open: st.success("Trạng thái: Mở 🟢")
            else: st.error("Trạng thái: Khóa 🔒")
            
            with st.expander("Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        tgt = u['Email'] if u['Role'] != 'PhuHuynh' else u['ChildEmail'] # Logic đơn giản
                        if safe_update_user(tgt, 'Password', np):
                            st.success("OK")
            
            st.divider()
            if st.button("Đăng xuất"):
                cookie_manager.delete("user_email")
                st.session_state.user = None
                st.rerun()
            return sel_period, is_open
    return None, False

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏫 ĐĂNG NHẬP</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("li"):
            e = st.text_input("Email")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng nhập"):
                if e == "admin@school.com" and p == "123":
                    st.session_state.user = {'Email': e, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                df = load_data('Users')
                if df.empty:
                    st.error("Chưa có dữ liệu.")
                    return
                
                # Check User
                m = df[(df['Email'] == e) & (df['Password'] == p)]
                if not m.empty:
                    st.session_state.user = m.iloc[0].to_dict()
                    cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                # Check Parent
                pm = df[(df['EmailPH'] == e) & (df['Password'] == p)]
                if not pm.empty:
                    c = pm.iloc[0]
                    st.session_state.user = {
                        'Email': e, 'Role': 'PhuHuynh', 
                        'HoTen': f"PH {c['HoTen']}", 'ChildEmail': c['Email'], 'ChildName': c['HoTen']
                    }
                    cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                st.error("Sai thông tin.")

# =============================================================================
# 5. MODULES CHỨC NĂNG
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["Đợt", "Thống kê", "Giáo Viên"])
    with t1:
        with st.form("np"):
            n = st.text_input("Tên đợt mới")
            if st.form_submit_button("Tạo"):
                if append_row('Periods', [n, 'Mở']):
                    st.success("Tạo xong")
                    st.rerun()
        df = load_data('Periods')
        for i, r in df.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"{r['TenDot']} ({r['TrangThai']})")
            nstt = "Khóa" if r['TrangThai'] == "Mở" else "Mở"
            if c2.button(f"Đổi sang {nstt}", key=f"p_{i}"):
                # Update cell trạng thái. Logic tìm dòng hơi thủ công với gspread
                # Để đơn giản, ta dùng safe_update logic giả định Period là unique
                # Thực tế với gspread, tìm row theo TenDot
                try:
                    client = get_client()
                    ws = client.open_by_key(SHEET_ID).worksheet('Periods')
                    cell = ws.find(r['TenDot'], in_column=1)
                    ws.update_cell(cell.row, 2, nstt)
                    clear_cache()
                    st.rerun()
                except: st.error("Lỗi cập nhật")

    with t2:
        df_u = load_data('Users')
        df_o = load_data('OKRs')
        if not df_o.empty: df_o = df_o[df_o['Dot'] == period]
        df_gv = df_u[df_u['Role'] == 'GiaoVien']
        res = []
        for _, g in df_gv.iterrows():
            l = str(g['Lop'])
            sub = df_o[df_o['Lop'] == l]['Email'].nunique()
            app = df_o[(df_o['Lop'] == l) & (df_o['TrangThai'] == 'Đã duyệt')]['Email'].nunique()
            res.append({"Lớp": l, "GV": g['HoTen'], "Nộp": sub, "Duyệt": app})
        st.dataframe(pd.DataFrame(res), use_container_width=True)

    with t3:
        with st.form("ngv"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Tên")
            l = c1.text_input("Lớp")
            s = c2.number_input("Sĩ số", 0)
            if st.form_submit_button("Lưu"):
                if append_row('Users', [e, '123', 'GiaoVien', n, l, '', s]):
                    st.success("OK")
                    st.rerun()
        with st.expander("Import Excel"):
            f = st.file_uploader("File", type=['xlsx'])
            if f and st.button("Import"):
                d = pd.read_excel(f)
                rows = []
                # Simple mapper
                for _, r in d.iterrows():
                    rows.append([str(r['Email']), '123', 'GiaoVien', str(r['HoTen']), str(r['Lop']), '', int(r['SiSo'])])
                batch_append('Users', rows)
                st.success("Import xong")

def teacher_view(period, is_open):
    u = st.session_state.user
    lop = str(u['Lop'])
    st.title(f"Lớp {lop}")
    
    df_u = load_data('Users')
    df_hs = df_u[(df_u['Role'] == 'HocSinh') & (df_u['Lop'] == lop)]
    
    df_o = load_data('OKRs')
    if not df_o.empty: df_o = df_o[(df_o['Lop'] == lop) & (df_o['Dot'] == period)]
    
    df_r = load_data('FinalReviews')
    if not df_r.empty: df_r = df_r[(df_r['Dot'] == period)]
    
    t1, t2 = st.tabs(["Duyệt bài", "Quản lý"])
    with t1:
        if df_hs.empty: st.info("Chưa có HS")
        else:
            for _, hs in df_hs.iterrows():
                em = hs['Email']
                nm = hs['HoTen']
                sub_o = df_o[df_o['Email'] == em]
                sub_r = df_r[df_r['Email'] == em]
                
                ic = "🔴"
                stt = "Chưa nộp"
                if not sub_o.empty:
                    ap = len(sub_o[sub_o['TrangThai']=='Đã duyệt'])
                    if ap == len(sub_o): ic, stt = "🟢", "Đã duyệt"
                    else: ic, stt = "🟡", "Chờ duyệt"
                
                is_fin = False
                if not sub_r.empty and sub_r.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
                    ic, stt = "✅", "Đã chốt"
                    is_fin = True
                
                with st.expander(f"{ic} {nm} ({stt})"):
                    if sub_o.empty: st.write("Trống")
                    else:
                        for _, r in sub_o.iterrows():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            c1.write(f"**{r['MucTieu']}** - {r['KetQuaThenChot']} ({r['ThucDat']}/{r['MucTieuSo']})")
                            c2.caption(r['TrangThai'])
                            if is_open:
                                if r['YeuCauXoa'] == 'TRUE':
                                    c3.error("Xin xóa")
                                    if c3.button("Xóa", key=f"d_{r['ID']}"):
                                        delete_row('OKRs', r['ID'], col_index=1)
                                        st.rerun()
                                else:
                                    if r['TrangThai'] != 'Đã duyệt' and c3.button("Duyệt", key=f"ok_{r['ID']}"):
                                        safe_update_okr(r['ID'], 'TrangThai', 'Đã duyệt')
                                        st.rerun()
                                    if r['TrangThai'] != 'Cần sửa' and c3.button("Sửa", key=f"no_{r['ID']}"):
                                        safe_update_okr(r['ID'], 'TrangThai', 'Cần sửa')
                                        st.rerun()
                            st.divider()
                    
                    # Review
                    cur_rv = sub_r.iloc[0]['NhanXet_CuoiKy'] if not sub_r.empty else ""
                    ph_rv = sub_r.iloc[0]['PhanHoi_PH'] if not sub_r.empty else ""
                    st.info(f"PH: {ph_rv}")
                    with st.form(f"f_{em}"):
                        txt = st.text_area("Nhận xét", value=cur_rv, disabled=not is_open)
                        fin = st.checkbox("Chốt sổ", value=is_fin, disabled=not is_open)
                        if st.form_submit_button("Lưu"):
                            stt_val = "Đã chốt" if fin else "Chưa chốt"
                            if sub_r.empty:
                                append_row('FinalReviews', [em, period, txt, "", stt_val])
                            else:
                                # Update row logic manually using gspread find
                                try:
                                    client = get_client()
                                    ws = client.open_by_key(SHEET_ID).worksheet('FinalReviews')
                                    # Find cell by Email AND Dot is hard in raw gspread without filtering
                                    # Workaround: Just append if simple, or use Dataframe save.
                                    # To be safe and simple for user: Use Delete then Append logic or find by Email (assuming 1 period active mostly)
                                    # Let's use simple find by Email first match in this period
                                    # (Advanced logic omitted for brevity/stability)
                                    cell = ws.find(em, in_column=1) 
                                    # This is risky if multiple periods exist. 
                                    # Better:
                                    df_all = load_data('FinalReviews')
                                    idx = df_all[(df_all['Email']==em) & (df_all['Dot']==period)].index
                                    if len(idx) > 0:
                                        # Row number in sheet = index + 2 (header + 0-base)
                                        r_num = idx[0] + 2
                                        ws.update_cell(r_num, 3, txt) # Col 3: NhanXet
                                        ws.update_cell(r_num, 5, stt_val) # Col 5: TrangThai
                                        clear_cache()
                                except: pass
                            st.success("Lưu")
                            st.rerun()

    with t2:
        with st.form("new_hs"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Tên")
            p = st.text_input("Email PH")
            if st.form_submit_button("Lưu"):
                if append_row('Users', [e, '123', 'HocSinh', n, lop, p, 0]):
                    st.success("OK")
                    st.rerun()
        with st.expander("Import Excel"):
            f = st.file_uploader("File", type=['xlsx'])
            if f and st.button("Import"):
                d = pd.read_excel(f)
                rows = []
                for _, r in d.iterrows():
                    rows.append([str(r['Email']), '123', 'HocSinh', str(r['HoTen']), lop, str(r['EmailPH']), 0])
                batch_append('Users', rows)
                st.success("Xong")

def student_view(period, is_open):
    u = st.session_state.user
    st.title(f"🎓 {u['HoTen']}")
    
    df_o = load_data('OKRs')
    if not df_o.empty: df_o = df_o[(df_o['Email'] == u['Email']) & (df_o['Dot'] == period)]
    
    df_r = load_data('FinalReviews')
    if not df_r.empty: df_r = df_r[(df_r['Email'] == u['Email']) & (df_r['Dot'] == period)]
    
    gv_txt = df_r.iloc[0]['NhanXet_CuoiKy'] if not df_r.empty else "..."
    st.info(f"GV: {gv_txt}")
    
    if is_open:
        with st.expander("Thêm OKR"):
            with st.form("add"):
                m = st.text_input("Mục tiêu")
                k = st.text_input("KR")
                t = st.number_input("Đích", 0.0)
                d = st.text_input("Đơn vị")
                if st.form_submit_button("Lưu"):
                    uid = str(uuid.uuid4())
                    append_row('OKRs', [uid, u['Email'], u['Lop'], period, m, k, t, 0, d, 0, "Chờ duyệt", "FALSE", "", 0, ""])
                    st.success("OK")
                    st.rerun()
    
    if not df_o.empty:
        for obj in df_o['MucTieu'].unique():
            with st.container(border=True):
                st.write(f"**{obj}**")
                for _, r in df_o[df_o['MucTieu'] == obj].iterrows():
                    st.caption(f"{r['KetQuaThenChot']} ({r['TrangThai']})")
                    c1, c2, c3 = st.columns([1, 2, 1])
                    cur = float(r['ThucDat'])
                    
                    if is_open and r['TrangThai'] == 'Đã duyệt':
                        nv = c2.number_input("Đạt", value=cur, key=f"n_{r['ID']}")
                        pg = calculate_progress(nv, r['MucTieuSo'])
                        c2.progress(int(pg))
                        if c3.button("Lưu", key=f"s_{r['ID']}"):
                            # Update 2 cột ThucDat, TienDo
                            # Vì safe_update_okr chỉ update 1 cột, ta gọi 2 lần hoặc tối ưu sau
                            # Gọi tạm 2 lần cho an toàn logic
                            safe_update_okr(r['ID'], 'ThucDat', nv)
                            safe_update_okr(r['ID'], 'TienDo', pg)
                            st.success("Saved")
                            st.rerun()
                    else:
                        c2.progress(int(float(r['TienDo'])))
                    
                    if is_open and r['YeuCauXoa'] == 'FALSE':
                        if c3.button("Xóa", key=f"d_{r['ID']}"):
                            safe_update_okr(r['ID'], 'YeuCauXoa', 'TRUE')
                            st.rerun()

def parent_view(period, is_open):
    u = st.session_state.user
    st.title(f"PH: {u['ChildName']}")
    
    df_o = load_data('OKRs')
    if not df_o.empty: df_o = df_o[(df_o['Email'] == u['ChildEmail']) & (df_o['Dot'] == period)]
    
    if not df_o.empty:
        for _, r in df_o.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"{r['KetQuaThenChot']} ({r['TienDo']}%)")
                s = int(float(r['DiemHaiLong_PH']))
                ns = c2.slider("Sao", 1, 5, s if s > 0 else 5, key=f"sl_{r['ID']}")
                if c2.button("Lưu", key=f"b_{r['ID']}"):
                    safe_update_okr(r['ID'], 'DiemHaiLong_PH', ns)
                    st.success("OK")

# =============================================================================
# 6. MAIN
# =============================================================================

def main():
    if not st.session_state.user:
        login_ui()
    else:
        period, is_open = sidebar_controller()
        if not period:
            st.warning("Vui lòng liên hệ Admin tạo đợt.")
            return
        
        r = st.session_state.user['Role']
        if r == 'Admin': admin_view(period, is_open)
        elif r == 'GiaoVien': teacher_view(period, is_open)
        elif r == 'HocSinh': student_view(period, is_open)
        elif r == 'PhuHuynh': parent_view(period, is_open)

if __name__ == "__main__":
    main()
