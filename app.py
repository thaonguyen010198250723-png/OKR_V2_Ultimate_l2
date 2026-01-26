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
    page_title="Hệ thống Quản lý OKR",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ẩn Branding của Streamlit & Nút Fork
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display:none;}
    </style>
    """, unsafe_allow_html=True)

# Khởi tạo Cookie Manager (Direct Init to avoid CachedWidgetWarning)
cookie_manager = stx.CookieManager()

# --- THÔNG TIN KẾT NỐI SUPABASE CỦA ANH ---
SUPABASE_URL = "https://iwobcnevhvqavonbjnnw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml3b2JjbmV2aHZxYXZvbmJqbm53Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0NDI3MDMsImV4cCI6MjA4NTAxODcwM30.InEuVLSU3NBtbQg7yB0E9AI21LK73RWc8TcvPPvOvjw"

@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        return None

supabase: Client = init_supabase()

# SCHEMA ĐỊNH NGHĨA (Để đảm bảo cột luôn tồn tại)
SCHEMA = {
    'Users': ['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH', 'SiSo'],
    'Periods': ['TenDot', 'TrangThai'],
    'OKRs': ['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQuaThenChot', 
             'MucTieuSo', 'ThucDat', 'DonVi', 'TienDo', 'TrangThai', 
             'YeuCauXoa', 'NhanXet_GV', 'DiemHaiLong_PH', 'NhanXet_PH'],
    'FinalReviews': ['id', 'Email', 'Dot', 'NhanXet_CuoiKy', 'PhanHoi_PH', 'TrangThai_CuoiKy']
}

# Session State
if 'user' not in st.session_state:
    st.session_state.user = None
if 'active_expander' not in st.session_state:
    st.session_state.active_expander = None

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU (FIX LỖI PYARROW TRIỆT ĐỂ)
# =============================================================================

def load_data(table_name):
    """
    Tải dữ liệu và xử lý ép kiểu nghiêm ngặt để tránh lỗi ArrowTypeError.
    """
    if not supabase: return pd.DataFrame(columns=SCHEMA.get(table_name, []))
    
    try:
        response = supabase.table(table_name).select("*").execute()
        data = response.data
        
        # Nếu không có dữ liệu, trả về DataFrame rỗng với đúng cột
        if not data:
            return pd.DataFrame(columns=SCHEMA.get(table_name, []))
        
        df = pd.DataFrame(data)
        
        # --- FIX LỖI PYARROW Ở ĐÂY ---
        
        # 1. Ép kiểu chuỗi cho các cột ID/UUID/Text để tránh object lạ
        # Duyệt qua tất cả các cột, nếu không phải số thì ép về string
        for col in df.columns:
            # Danh sách các cột bắt buộc là Số
            if col in ['SiSo', 'MucTieuSo', 'ThucDat', 'TienDo', 'DiemHaiLong_PH']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            else:
                # Các cột còn lại (ID, Email, Text...) ép về string
                # Xử lý None thành chuỗi rỗng
                df[col] = df[col].astype(str).replace(['None', 'nan', '<NA>'], '')
                
        return df

    except Exception as e:
        # st.error(f"Lỗi tải {table_name}: {e}") # Debug only
        return pd.DataFrame(columns=SCHEMA.get(table_name, []))

def upsert_data(table_name, data_dict):
    try:
        supabase.table(table_name).upsert(data_dict).execute()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu: {e}")
        return False

def delete_data(table_name, col_name, value):
    try:
        supabase.table(table_name).delete().eq(col_name, value).execute()
        return True
    except Exception as e:
        st.error(f"Lỗi xóa: {e}")
        return False

# =============================================================================
# 3. TIỆN ÍCH & BÁO CÁO
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
        
        # Phần 1: OKR
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
                cells[4].text = f"{row['TienDo']}%"
                stars = int(float(row['DiemHaiLong_PH'])) # Fix float to int conversion
                cells[5].text = "★" * stars if stars > 0 else "-"
        else:
            doc.add_paragraph("(Chưa có dữ liệu OKR)")
        
        # Phần 2: Nhận xét
        doc.add_heading('II. TỔNG KẾT & PHẢN HỒI', level=1)
        sub_rev = df_rev[(df_rev['Email'] == hs['Email']) & (df_rev['Dot'] == period)]
        gv_cmt = ""
        ph_cmt = ""
        if not sub_rev.empty:
            r = sub_rev.iloc[0]
            gv_cmt = r['NhanXet_CuoiKy']
            ph_cmt = r['PhanHoi_PH']
            
        doc.add_paragraph(f"1. Nhận xét của GVCN:")
        doc.add_paragraph(gv_cmt if gv_cmt else "...")
        doc.add_paragraph(f"2. Ý kiến của Gia đình:")
        doc.add_paragraph(ph_cmt if ph_cmt else "...")
        
        if i < len(hs_data_list) - 1:
            doc.add_page_break()
            
    bio = BytesIO()
    doc.save(bio)
    return bio

# =============================================================================
# 4. GIAO DIỆN & LOGIN
# =============================================================================

def sidebar_controller():
    with st.sidebar:
        if st.session_state.user:
            u = st.session_state.user
            st.info(f"👤 {u['HoTen']}\nRole: {u['Role']}")
            st.divider()
            
            # Chọn đợt
            df_p = load_data('Periods')
            if df_p.empty:
                st.warning("Chưa có đợt nào.")
                if st.button("Đăng xuất"):
                    cookie_manager.delete("user_email")
                    st.session_state.user = None
                    st.rerun()
                return None, False
            
            p_opts = df_p['TenDot'].tolist()
            # Default to first 'Mở'
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts: idx = p_opts.index(opens[0])
            
            sel_period = st.selectbox("Chọn đợt:", p_opts, index=idx)
            
            # Check status
            row = df_p[df_p['TenDot'] == sel_period].iloc[0]
            is_open = (row['TrangThai'] == 'Mở')
            
            if is_open: st.success(f"Trạng thái: {row['TrangThai']} 🟢")
            else: st.error(f"Trạng thái: {row['TrangThai']} 🔒")
            
            # Đổi mật khẩu
            with st.expander("🔑 Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        # Logic đổi pass cho user hiện tại (hoặc con nếu là PH)
                        target_email = u['Email']
                        if u['Role'] == 'PhuHuynh': target_email = u['EmailPH'] # Cần check lại logic EmailPH
                        # Với Supabase User table, ta update thẳng vào dòng có Email đó
                        upsert_data('Users', {'Email': target_email, 'Password': np})
                        st.success("Đổi thành công")

            st.divider()
            if st.button("Đăng xuất", use_container_width=True):
                cookie_manager.delete("user_email")
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
                # 1. Master Admin Check
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    cookie_manager.set("user_email", email, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                # 2. Supabase Check
                try:
                    # Tìm trong bảng Users
                    # Check User thường
                    res = supabase.table('Users').select("*").eq('Email', email).eq('Password', password).execute()
                    if res.data:
                        st.session_state.user = res.data[0]
                        cookie_manager.set("user_email", email, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                        st.rerun()
                    
                    # Check Phụ huynh (Login bằng EmailPH)
                    res_ph = supabase.table('Users').select("*").eq('EmailPH', email).eq('Password', password).execute()
                    if res_ph.data:
                        child = res_ph.data[0]
                        st.session_state.user = {
                            'Email': email, 'Role': 'PhuHuynh',
                            'HoTen': f"PH em {child['HoTen']}",
                            'ChildEmail': child['Email'], 'ChildName': child['HoTen']
                        }
                        cookie_manager.set("user_email", email, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                        st.rerun()
                        
                    st.error("Sai thông tin đăng nhập.")
                except Exception as e:
                    st.error(f"Lỗi kết nối: {e}")

# =============================================================================
# 5. MODULES: ADMIN
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["⚙️ Quản lý Đợt", "📊 Thống kê", "👨‍🏫 Giáo Viên"])
    
    with t1:
        with st.form("new_p"):
            np = st.text_input("Tên đợt mới")
            if st.form_submit_button("Tạo"):
                upsert_data('Periods', {'TenDot': np, 'TrangThai': 'Mở'})
                st.success("Xong")
                st.rerun()
        
        df_p = load_data('Periods')
        for i, r in df_p.iterrows():
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"**{r['TenDot']}**")
            c2.write(r['TrangThai'])
            ns = "Khóa" if r['TrangThai'] == "Mở" else "Mở"
            if c3.button(f"Đổi sang {ns}", key=f"p_{i}"):
                upsert_data('Periods', {'TenDot': r['TenDot'], 'TrangThai': ns})
                st.rerun()

    with t2:
        st.write(f"Thống kê đợt: {period}")
        df_u = load_data('Users')
        df_okr = load_data('OKRs')
        df_okr = df_okr[df_okr['Dot'] == period]
        
        df_gv = df_u[df_u['Role'] == 'GiaoVien']
        stats = []
        for _, gv in df_gv.iterrows():
            lop = gv['Lop']
            siso = int(float(gv['SiSo']))
            cls_okrs = df_okr[df_okr['Lop'] == lop]
            submitted = cls_okrs['Email'].nunique()
            approved = cls_okrs[cls_okrs['TrangThai'] == 'Đã duyệt']['Email'].nunique()
            stats.append({
                "Lớp": lop, "GV": gv['HoTen'], "Sĩ số": siso,
                "Nộp": f"{submitted}/{siso}", "Duyệt": f"{approved}/{siso}"
            })
        st.dataframe(pd.DataFrame(stats), use_container_width=True)

    with t3:
        with st.form("add_gv"):
            e = st.text_input("Email")
            n = st.text_input("Tên")
            l = st.text_input("Lớp")
            s = st.number_input("Sĩ số", 0)
            if st.form_submit_button("Lưu"):
                upsert_data('Users', {'Email': e, 'Password': '123', 'Role': 'GiaoVien', 'HoTen': n, 'Lop': l, 'SiSo': s})
                st.success("OK")
                st.rerun()
        
        df_gv = load_data('Users')
        if not df_gv.empty:
            st.dataframe(df_gv[df_gv['Role'] == 'GiaoVien'][['Email', 'HoTen', 'Lop', 'SiSo']])

# =============================================================================
# 6. MODULE: TEACHER (FIX LAG)
# =============================================================================

def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = str(user.get('Lop', ''))
    st.title(f"👩‍🏫 LỚP {my_class}")
    
    # Load Data
    df_users = load_data('Users')
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    
    df_okr = load_data('OKRs')
    df_okr_class = df_okr[(df_okr['Lop'] == my_class) & (df_okr['Dot'] == period)]
    
    df_rev = load_data('FinalReviews')
    df_rev_class = df_rev[(df_rev['Dot'] == period)]
    
    t1, t2 = st.tabs(["🚀 Duyệt & Đánh Giá", "👥 Quản Lý HS"])
    
    with t1:
        if df_hs.empty: st.info("Lớp chưa có HS.")
        else:
            for idx, hs in df_hs.iterrows():
                email_hs = hs['Email']
                name_hs = hs['HoTen']
                
                # Check status
                hs_okrs = df_okr_class[df_okr_class['Email'] == email_hs]
                hs_rev = df_rev_class[df_rev_class['Email'] == email_hs]
                
                icon = "🔴"
                stt_txt = "Chưa nộp"
                if not hs_okrs.empty:
                    appr = len(hs_okrs[hs_okrs['TrangThai'] == 'Đã duyệt'])
                    if appr == len(hs_okrs): icon, stt_txt = "🟢", "Đã duyệt"
                    else: icon, stt_txt = "🟡", "Chờ duyệt"
                
                is_fin = False
                if not hs_rev.empty and hs_rev.iloc[0]['TrangThai_CuoiKy'] == 'Đã chốt':
                    icon, stt_txt = "✅", "Đã chốt"
                    is_fin = True
                
                # EXPANDER FIX LAG
                is_expanded = (st.session_state.active_expander == email_hs)
                
                with st.expander(f"{icon} {name_hs} ({stt_txt})", expanded=is_expanded):
                    if hs_okrs.empty: st.warning("Trống")
                    else:
                        for _, row in hs_okrs.iterrows():
                            c1, c2, c3 = st.columns([3, 1.5, 1.5])
                            c1.markdown(f"**{row['MucTieu']}** - {row['KetQuaThenChot']}")
                            c1.caption(f"{row['ThucDat']}/{row['MucTieuSo']} {row['DonVi']}")
                            
                            c2.write(f"`{row['TrangThai']}`")
                            
                            if is_open:
                                if row['YeuCauXoa'] == 'TRUE':
                                    c3.error("Xin xóa")
                                    if c3.button("Xóa", key=f"del_{row['ID']}"):
                                        delete_data('OKRs', 'ID', row['ID'])
                                        st.session_state.active_expander = email_hs
                                        st.rerun()
                                else:
                                    if row['TrangThai'] != 'Đã duyệt' and c3.button("Duyệt", key=f"app_{row['ID']}"):
                                        upsert_data('OKRs', {'ID': row['ID'], 'TrangThai': 'Đã duyệt'})
                                        st.session_state.active_expander = email_hs
                                        st.rerun()
                                    if row['TrangThai'] != 'Cần sửa' and c3.button("Sửa", key=f"rej_{row['ID']}"):
                                        upsert_data('OKRs', {'ID': row['ID'], 'TrangThai': 'Cần sửa'})
                                        st.session_state.active_expander = email_hs
                                        st.rerun()
                            st.divider()
                    
                    # Review
                    st.write("##### Đánh giá")
                    c_txt = hs_rev.iloc[0]['NhanXet_CuoiKy'] if not hs_rev.empty else ""
                    ph_txt = hs_rev.iloc[0]['PhanHoi_PH'] if not hs_rev.empty else ""
                    st.info(f"PH: {ph_txt}")
                    
                    with st.form(f"rv_{email_hs}"):
                        txt = st.text_area("Nhận xét", value=c_txt, disabled=not is_open)
                        fin = st.checkbox("Chốt sổ", value=is_fin, disabled=not is_open)
                        if st.form_submit_button("Lưu"):
                            stt_val = "Đã chốt" if fin else "Chưa chốt"
                            upsert_data('FinalReviews', {'Email': email_hs, 'Dot': period, 'NhanXet_CuoiKy': txt, 'TrangThai_CuoiKy': stt_val})
                            st.session_state.active_expander = email_hs
                            st.success("Lưu OK")
                            time.sleep(0.5)
                            st.rerun()

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            st.dataframe(df_hs[['Email', 'HoTen']])
            d_em = st.text_input("Email HS xóa:")
            if st.button("Xóa"):
                delete_data('Users', 'Email', d_em)
                st.rerun()
        with c2:
            with st.form("add_hs_fast"):
                e = st.text_input("Email")
                n = st.text_input("Tên")
                p = st.text_input("Email PH")
                if st.form_submit_button("Thêm"):
                    upsert_data('Users', {'Email': e, 'Password': '123', 'Role': 'HocSinh', 'HoTen': n, 'Lop': my_class, 'EmailPH': p})
                    st.rerun()

# =============================================================================
# 7. MODULE: STUDENT
# =============================================================================

def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    df_okr = load_data('OKRs')
    my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    df_rev = load_data('FinalReviews')
    rev = df_rev[(df_rev['Email'] == user['Email']) & (df_rev['Dot'] == period)]
    
    # 1. Info
    st.markdown("### 📝 Tổng kết")
    gv_t = rev.iloc[0]['NhanXet_CuoiKy'] if not rev.empty and rev.iloc[0]['NhanXet_CuoiKy'] else "..."
    st.info(f"GV: {gv_t}")
    ph_t = rev.iloc[0]['PhanHoi_PH'] if not rev.empty and rev.iloc[0]['PhanHoi_PH'] else "..."
    st.warning(f"PH: {ph_t}")
    
    # 2. Add
    if is_open:
        with st.expander("➕ Thêm OKR"):
            with st.form("new_okr"):
                o = st.text_input("Mục tiêu")
                k = st.text_input("Key Result")
                t = st.number_input("Mục tiêu số", 0.0)
                u = st.text_input("Đơn vị")
                if st.form_submit_button("Lưu"):
                    uid = str(uuid.uuid4())
                    upsert_data('OKRs', {
                        'ID': uid, 'Email': user['Email'], 'Lop': user['Lop'], 'Dot': period,
                        'MucTieu': o, 'KetQuaThenChot': k, 'MucTieuSo': t, 'DonVi': u,
                        'ThucDat': 0, 'TienDo': 0, 'TrangThai': 'Chờ duyệt'
                    })
                    st.success("Đã thêm")
                    st.rerun()
    
    # 3. List
    st.subheader("Tiến độ")
    if my_okrs.empty: st.info("Trống")
    else:
        for obj in my_okrs['MucTieu'].unique():
            with st.container(border=True):
                st.markdown(f"**🎯 {obj}**")
                for _, row in my_okrs[my_okrs['MucTieu'] == obj].iterrows():
                    st.divider()
                    st.markdown(f"{row['KetQuaThenChot']} ({row['TrangThai']})")
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.caption(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                    
                    cur = float(row['ThucDat'])
                    if is_open and row['TrangThai'] == 'Đã duyệt':
                        new_val = c2.number_input(f"Đạt ({row['DonVi']})", value=cur, step=0.1, key=f"n_{row['ID']}")
                        prog = calculate_progress(new_val, row['MucTieuSo'])
                        c2.progress(int(prog))
                        if c3.button("Lưu", key=f"sv_{row['ID']}"):
                            upsert_data('OKRs', {'ID': row['ID'], 'ThucDat': new_val, 'TienDo': prog})
                            st.success("Saved")
                            st.rerun()
                    else:
                        c2.write(f"Đạt: {cur}")
                        c2.progress(int(float(row['TienDo'])))
                    
                    if is_open and row['YeuCauXoa'] == 'FALSE':
                        if c3.button("Xin xóa", key=f"req_{row['ID']}"):
                            upsert_data('OKRs', {'ID': row['ID'], 'YeuCauXoa': 'TRUE'})
                            st.rerun()

# =============================================================================
# 8. MODULE: PARENT
# =============================================================================

def parent_view(period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 PHHS: {user['ChildName']}")
    
    df_okr = load_data('OKRs')
    c_okrs = df_okr[(df_okr['Email'] == user['ChildEmail']) & (df_okr['Dot'] == period)]
    
    st.subheader("Đánh giá")
    if c_okrs.empty: st.info("Con chưa có OKR")
    else:
        for _, row in c_okrs.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**KR:** {row['KetQuaThenChot']}")
                c1.caption(f"{row['TienDo']}%")
                star = int(float(row['DiemHaiLong_PH']))
                ns = c2.slider("Sao", 1, 5, star if star > 0 else 5, key=f"s_{row['ID']}")
                if c2.button("Lưu", key=f"btn_{row['ID']}"):
                    upsert_data('OKRs', {'ID': row['ID'], 'DiemHaiLong_PH': ns})
                    st.success("OK")
    
    st.divider()
    df_rev = load_data('FinalReviews')
    rev = df_rev[(df_rev['Email'] == user['ChildEmail']) & (df_rev['Dot'] == period)]
    
    txt_gv = rev.iloc[0]['NhanXet_CuoiKy'] if not rev.empty else "..."
    st.info(f"GV: {txt_gv}")
    
    old_ph = rev.iloc[0]['PhanHoi_PH'] if not rev.empty else ""
    with st.form("ph_f"):
        t = st.text_area("Ý kiến PH:", value=old_ph)
        if st.form_submit_button("Gửi"):
            upsert_data('FinalReviews', {'Email': user['ChildEmail'], 'Dot': period, 'PhanHoi_PH': t})
            st.success("Đã gửi")
            st.rerun()

# =============================================================================
# 9. MAIN APP
# =============================================================================

def main():
    # Auto Login
    if not st.session_state.user:
        c_em = cookie_manager.get(cookie="user_email")
        if c_em:
            if c_em == "admin@school.com":
                st.session_state.user = {'Email': c_em, 'Role': 'Admin', 'HoTen': 'Super Admin'}
            else:
                # Check DB
                df = load_data('Users')
                if not df.empty:
                    m = df[df['Email'] == c_em]
                    if not m.empty: st.session_state.user = m.iloc[0].to_dict()
                    else:
                        pm = df[df['EmailPH'] == c_em]
                        if not pm.empty:
                            c = pm.iloc[0]
                            st.session_state.user = {'Email': c_em, 'Role': 'PhuHuynh', 'HoTen': f"PH {c['HoTen']}", 'ChildEmail': c['Email'], 'ChildName': c['HoTen']}

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
