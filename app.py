import streamlit as st
import pandas as pd
from supabase import create_client, Client
import extra_streamlit_components as stx
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
import time
import uuid
import datetime

# =============================================================================
# 1. CẤU HÌNH & KẾT NỐI SUPABASE
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR (Supabase)",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ẩn Branding
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display:none;}
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Cookie
cookie_manager = stx.CookieManager()

# --- THÔNG TIN SUPABASE CỦA ANH ---
SUPABASE_URL = "https://iwobcnevhvqavonbjnnw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml3b2JjbmV2aHZxYXZvbmJqbm53Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0NDI3MDMsImV4cCI6MjA4NTAxODcwM30.InEuVLSU3NBtbQg7yB0E9AI21LK73RWc8TcvPPvOvjw"

@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except:
        return None

supabase: Client = init_supabase()

SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'Periods': ['TenDot', 'TrangThai'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV', 'DiemHaiLong_PH', 'NhanXet_PH'],
    'FinalReviews': ['id', 'Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH', 'TrangThai_CuoiKy']
}

if 'user' not in st.session_state:
    st.session_state.user = None
if 'active_expander' not in st.session_state:
    st.session_state.active_expander = None

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU (FIX LỖI PYARROW - PHIÊN BẢN MẠNH NHẤT)
# =============================================================================

@st.cache_data(ttl=5)
def load_data(table_name):
    """Load dữ liệu và ép kiểu an toàn tuyệt đối"""
    if not supabase: return pd.DataFrame(columns=SCHEMA.get(table_name, []))
    
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        
        # Nếu rỗng, trả về khung xương
        if not data:
            return pd.DataFrame(columns=SCHEMA.get(table_name, []))
        
        df = pd.DataFrame(data)
        
        # --- CHIẾN THUẬT FIX LỖI PYARROW ---
        # 1. Ép toàn bộ cột KHÔNG PHẢI SỐ về dạng String (để xử lý UUID, None, Object)
        num_cols = ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH']
        
        for col in df.columns:
            if col not in num_cols:
                # Chuyển về string, thay thế None/nan bằng chuỗi rỗng
                df[col] = df[col].astype(str).replace(['None', 'nan', '<NA>'], '')
        
        # 2. Ép các cột SỐ về dạng Float/Int chuẩn
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
        return df

    except Exception as e:
        # Trả về bảng rỗng nếu lỗi, tránh sập app
        return pd.DataFrame(columns=SCHEMA.get(table_name, []))

def clear_cache():
    st.cache_data.clear()

def upsert_data(table_name, data_dict):
    try:
        supabase.table(table_name).upsert(data_dict).execute()
        clear_cache()
        return True
    except: return False

def delete_data(table_name, col, val):
    try:
        supabase.table(table_name).delete().eq(col, val).execute()
        clear_cache()
        return True
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
        doc.add_paragraph(f"HS: {hs['HoTen']} - Lớp: {hs['Lop']}")
        doc.add_paragraph("-" * 60)
        
        # OKR
        doc.add_heading('I. KẾT QUẢ', level=1)
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
                cells[2].text = str(row['MucTieuSo'])
                cells[3].text = str(row['ThucDat'])
                cells[4].text = f"{row['TienDo']:.1f}%"
                cells[5].text = str(int(row['DiemHaiLong_PH']))
        else: doc.add_paragraph("(Trống)")
        
        # Review
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
# 4. GIAO DIỆN CHÍNH
# =============================================================================

def sidebar_controller():
    with st.sidebar:
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            st.divider()
            
            df_p = load_data('Periods')
            if df_p.empty:
                if st.button("Đăng xuất"):
                    cookie_manager.delete("user_email")
                    st.session_state.user = None
                    st.rerun()
                return None, False
            
            p_opts = df_p['TenDot'].tolist()
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts: idx = p_opts.index(opens[0])
            sel_period = st.selectbox("Đợt:", p_opts, index=idx)
            
            row = df_p[df_p['TenDot'] == sel_period].iloc[0]
            is_open = (row['TrangThai'] == 'Mở')
            st.caption(f"Trạng thái: {'Mở 🟢' if is_open else 'Khóa 🔒'}")
            
            with st.expander("Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        target = u['Email']
                        if u['Role'] == 'PhuHuynh': target = u['EmailPH']
                        upsert_data('Users', {'Email': target, 'Password': np})
                        st.success("OK")
            
            st.divider()
            if st.button("Đăng xuất", use_container_width=True):
                cookie_manager.delete("user_email")
                st.session_state.user = None
                st.rerun()
            return sel_period, is_open
    return None, False

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏫 ĐĂNG NHẬP (SUPABASE)</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("li"):
            e = st.text_input("Email")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Vào"):
                if e == "admin@school.com" and p == "123":
                    st.session_state.user = {'Email': e, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                try:
                    # Check User
                    res = supabase.table('Users').select("*").eq('Email', e).eq('Password', p).execute()
                    if res.data:
                        st.session_state.user = res.data[0]
                        cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                        st.rerun()
                    
                    # Check PH
                    res_ph = supabase.table('Users').select("*").eq('EmailPH', e).eq('Password', p).execute()
                    if res_ph.data:
                        c = res_ph.data[0]
                        st.session_state.user = {'Email': e, 'Role': 'PhuHuynh', 'HoTen': f"PH {c['HoTen']}", 'ChildEmail': c['Email'], 'ChildName': c['HoTen']}
                        cookie_manager.set("user_email", e, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                        st.rerun()
                    
                    st.error("Sai thông tin")
                except: st.error("Lỗi kết nối")

# =============================================================================
# 5. MODULES
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin")
    t1, t2, t3 = st.tabs(["Đợt", "Thống kê", "GV"])
    with t1:
        with st.form("np"):
            n = st.text_input("Tên đợt")
            if st.form_submit_button("Tạo"):
                upsert_data('Periods', {'TenDot': n, 'TrangThai': 'Mở'})
                st.rerun()
        df = load_data('Periods')
        for i, r in df.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.write(f"{r['TenDot']} ({r['TrangThai']})")
            if c2.button("Đổi", key=f"p_{i}"):
                ns = "Khóa" if r['TrangThai'] == "Mở" else "Mở"
                upsert_data('Periods', {'TenDot': r['TenDot'], 'TrangThai': ns})
                st.rerun()
    with t2:
        df_u = load_data('Users')
        df_o = load_data('OKRs')
        if not df_o.empty: df_o = df_o[df_o['Dot'] == period]
        df_gv = df_u[df_u['Role']=='GiaoVien']
        res = []
        for _, g in df_gv.iterrows():
            l = g['Lop']
            sub = df_o[df_o['Lop'] == l]
            n = sub['Email'].nunique()
            d = sub[sub['TrangThai']=='Đã duyệt']['Email'].nunique()
            res.append({"Lớp": l, "GV": g['HoTen'], "Nộp": n, "Duyệt": d})
        st.dataframe(pd.DataFrame(res), use_container_width=True)
    with t3:
        with st.form("ngv"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Tên")
            l = c1.text_input("Lớp")
            s = c2.number_input("Sĩ số", 0)
            if st.form_submit_button("Lưu"):
                upsert_data('Users', {'Email': e, 'Password': '123', 'Role': 'GiaoVien', 'HoTen': n, 'Lop': l, 'SiSo': s})
                st.rerun()
        st.dataframe(load_data('Users')[lambda d: d['Role']=='GiaoVien'][['Email', 'HoTen', 'Lop']])

def teacher_view(period, is_open):
    u = st.session_state.user
    lop = u['Lop']
    st.title(f"Lớp {lop}")
    
    df_u = load_data('Users')
    df_hs = df_u[(df_u['Role'] == 'HocSinh') & (df_u['Lop'] == lop)]
    
    df_okr = load_data('OKRs')
    if not df_okr.empty: df_okr = df_okr[df_okr['Dot'] == period]
    
    df_rev = load_data('FinalReviews')
    if not df_rev.empty: df_rev = df_rev[df_rev['Dot'] == period]
    
    t1, t2 = st.tabs(["Duyệt bài", "Quản lý"])
    with t1:
        if df_hs.empty: st.info("Chưa có HS")
        else:
            for _, hs in df_hs.iterrows():
                em = hs['Email']
                nm = hs['HoTen']
                
                sub_o = df_okr[df_okr['Email'] == em] if not df_okr.empty else pd.DataFrame()
                sub_r = df_rev[df_rev['Email'] == em] if not df_rev.empty else pd.DataFrame()
                
                ic = "🔴"
                stt = "Chưa nộp"
                if not sub_o.empty:
                    d = len(sub_o[sub_o['TrangThai']=='Đã duyệt'])
                    if d == len(sub_o): ic, stt = "🟢", "Đã duyệt"
                    else: ic, stt = "🟡", "Chờ duyệt"
                
                is_fin = False
                if not sub_r.empty and sub_r.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
                    ic, stt = "✅", "Đã chốt"
                    is_fin = True
                
                open_exp = (st.session_state.active_expander == em)
                with st.expander(f"{ic} {nm} ({stt})", expanded=open_exp):
                    if sub_o.empty: st.write("Trống")
                    else:
                        for _, r in sub_o.iterrows():
                            c1, c2, c3 = st.columns([3, 1, 1])
                            c1.write(f"**{r['MucTieu']}** - {r['KetQuaThenChot']} ({r['ThucDat']}/{r['MucTieuSo']})")
                            c2.caption(r['TrangThai'])
                            if is_open:
                                if r['YeuCauXoa'] == 'TRUE':
                                    c3.error("Xin xóa")
                                    if c3.button("Xóa", key=f"del_{r['ID']}"):
                                        delete_data('OKRs', 'ID', r['ID'])
                                        st.session_state.active_expander = em
                                        st.rerun()
                                else:
                                    if r['TrangThai'] != 'Đã duyệt' and c3.button("Duyệt", key=f"ok_{r['ID']}"):
                                        upsert_data('OKRs', {'ID': r['ID'], 'TrangThai': 'Đã duyệt'})
                                        st.session_state.active_expander = em
                                        st.rerun()
                                    if r['TrangThai'] != 'Cần sửa' and c3.button("Sửa", key=f"no_{r['ID']}"):
                                        upsert_data('OKRs', {'ID': r['ID'], 'TrangThai': 'Cần sửa'})
                                        st.session_state.active_expander = em
                                        st.rerun()
                            st.divider()
                    
                    val_rv = sub_r.iloc[0]['NhanXet_CuoiKy'] if not sub_r.empty else ""
                    with st.form(f"f_{em}"):
                        txt = st.text_area("Nhận xét", value=val_rv, disabled=not is_open)
                        fin = st.checkbox("Chốt sổ", value=is_fin, disabled=not is_open)
                        if st.form_submit_button("Lưu"):
                            stv = "Đã chốt" if fin else "Chưa chốt"
                            upsert_data('FinalReviews', {'Email': em, 'Dot': period, 'NhanXet_CuoiKy': txt, 'TrangThai_CuoiKy': stv})
                            st.session_state.active_expander = em
                            st.rerun()
    with t2:
        with st.form("new_hs"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Tên")
            p = st.text_input("Email PH")
            if st.form_submit_button("Thêm"):
                upsert_data('Users', {'Email': e, 'Password': '123', 'Role': 'HocSinh', 'HoTen': n, 'Lop': lop, 'EmailPH': p})
                st.rerun()
        st.dataframe(df_hs[['Email', 'HoTen']])

def student_view(period, is_open):
    u = st.session_state.user
    st.title(f"🎓 {u['HoTen']}")
    
    df_okr = load_data('OKRs')
    if not df_okr.empty: df_okr = df_okr[(df_okr['Email']==u['Email']) & (df_okr['Dot']==period)]
    
    df_rev = load_data('FinalReviews')
    if not df_rev.empty: df_rev = df_rev[(df_rev['Email']==u['Email']) & (df_rev['Dot']==period)]
    
    gtxt = df_rev.iloc[0]['NhanXet_CuoiKy'] if not df_rev.empty else "..."
    st.info(f"GV: {gtxt}")
    
    if is_open:
        with st.expander("➕ Thêm OKR"):
            with st.form("add"):
                m = st.text_input("Mục tiêu")
                k = st.text_input("KR")
                t = st.number_input("Đích", 0.0)
                d = st.text_input("Đơn vị")
                if st.form_submit_button("Lưu"):
                    upsert_data('OKRs', {'ID': str(uuid.uuid4()), 'Email': u['Email'], 'Lop': u['Lop'], 'Dot': period, 'MucTieu': m, 'KetQuaThenChot': k, 'MucTieuSo': t, 'DonVi': d, 'TrangThai': 'Chờ duyệt'})
                    st.rerun()
    
    if not df_okr.empty:
        for o in df_okr['MucTieu'].unique():
            with st.container(border=True):
                st.write(f"**{o}**")
                for _, r in df_okr[df_okr['MucTieu']==o].iterrows():
                    st.caption(f"{r['KetQuaThenChot']} ({r['TrangThai']})")
                    c1, c2, c3 = st.columns([1, 2, 1])
                    cur = float(r['ThucDat'])
                    if is_open and r['TrangThai'] == 'Đã duyệt':
                        nv = c2.number_input("Đạt", value=cur, key=f"n_{r['ID']}")
                        pg = calculate_progress(nv, r['MucTieuSo'])
                        c2.progress(int(pg))
                        if c3.button("Lưu", key=f"s_{r['ID']}"):
                            upsert_data('OKRs', {'ID': r['ID'], 'ThucDat': nv, 'TienDo': pg})
                            st.rerun()
                    else:
                        c2.progress(int(float(r['TienDo'])))
                    
                    if is_open and r['YeuCauXoa'] == 'FALSE':
                        if c3.button("Xóa", key=f"d_{r['ID']}"):
                            upsert_data('OKRs', {'ID': r['ID'], 'YeuCauXoa': 'TRUE'})
                            st.rerun()

def parent_view(period, is_open):
    u = st.session_state.user
    st.title(f"PHHS: {u['ChildName']}")
    
    df_okr = load_data('OKRs')
    if not df_okr.empty: df_okr = df_okr[(df_okr['Email']==u['ChildEmail']) & (df_okr['Dot']==period)]
    
    if not df_okr.empty:
        for _, r in df_okr.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"{r['KetQuaThenChot']} ({r['TienDo']}%)")
                s = int(float(r['DiemHaiLong_PH']))
                ns = c2.slider("Sao", 1, 5, s if s > 0 else 5, key=f"sl_{r['ID']}")
                if c2.button("Lưu", key=f"b_{r['ID']}"):
                    upsert_data('OKRs', {'ID': r['ID'], 'DiemHaiLong_PH': ns})
                    st.success("OK")

# =============================================================================
# 6. MAIN
# =============================================================================

def main():
    if not st.session_state.user:
        em = cookie_manager.get(cookie="user_email")
        if em:
            if em == "admin@school.com":
                st.session_state.user = {'Email': em, 'Role': 'Admin', 'HoTen': 'Super Admin'}
            else:
                df = load_data('Users')
                if not df.empty:
                    u = df[df['Email'] == em]
                    if not u.empty: st.session_state.user = u.iloc[0].to_dict()
                    else:
                        p = df[df['EmailPH'] == em]
                        if not p.empty:
                            c = p.iloc[0]
                            st.session_state.user = {'Email': em, 'Role': 'PhuHuynh', 'HoTen': f"PH {c['HoTen']}", 'ChildEmail': c['Email'], 'ChildName': c['HoTen']}
    
    if not st.session_state.user:
        login_ui()
    else:
        period, is_open = sidebar_controller()
        if not period:
            st.warning("Vui lòng tạo đợt.")
            return
        
        r = st.session_state.user['Role']
        if r == 'Admin': admin_view(period, is_open)
        elif r == 'GiaoVien': teacher_view(period, is_open)
        elif r == 'HocSinh': student_view(period, is_open)
        elif r == 'PhuHuynh': parent_view(period, is_open)

if __name__ == "__main__":
    main()
