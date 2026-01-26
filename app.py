import streamlit as st
import pandas as pd
from supabase import create_client, Client
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
    page_title="Hệ thống Quản lý OKR (Pro)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ẨN MENU THỪA ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display:none;}
    </style>
""", unsafe_allow_html=True)

# --- KẾT NỐI SUPABASE (THAY THÔNG TIN CỦA ANH VÀO ĐÂY) ---
# Anh lấy thông tin này trong phần Settings -> API của Supabase
SUPABASE_URL = "https://iwobcnevhvqavonbjnnw.supabase.co" 
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml3b2JjbmV2aHZxYXZvbmJqbm53Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0NDI3MDMsImV4cCI6MjA4NTAxODcwM30.InEuVLSU3NBtbQg7yB0E9AI21LK73RWc8TcvPPvOvjw"

@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except:
        return None

supabase = init_supabase()
cookie_manager = stx.CookieManager()

LOGO_URL = "logo FSC.png"

# --- STATE QUẢN LÝ UI (FIX GIẬT LAG) ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'active_expander' not in st.session_state:
    st.session_state.active_expander = None  # Biến này giúp nhớ vị trí HS đang mở

# =============================================================================
# 2. XỬ LÝ DỮ LIỆU (BACKEND SUPABASE)
# =============================================================================

def load_data(table_name):
    """Tải dữ liệu từ Supabase (Cực nhanh, không lo Quota)"""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(response.data)
        return df
    except Exception as e:
        # st.error(f"Lỗi tải {table_name}: {e}") # Ẩn lỗi để giao diện sạch
        return pd.DataFrame()

# --- CÁC HÀM GHI DỮ LIỆU AN TOÀN ---

def safe_insert(table, data_dict):
    try:
        supabase.table(table).insert(data_dict).execute()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu: {e}")
        return False

def safe_update(table, match_col, match_val, update_dict):
    try:
        supabase.table(table).update(update_dict).eq(match_col, match_val).execute()
        return True
    except Exception as e:
        st.error(f"Lỗi cập nhật: {e}")
        return False

def safe_delete(table, match_col, match_val):
    try:
        supabase.table(table).delete().eq(match_col, match_val).execute()
        return True
    except Exception as e:
        st.error(f"Lỗi xóa: {e}")
        return False

# =============================================================================
# 3. UTILITIES
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
                stars = int(row['DiemHaiLong_PH']) if row['DiemHaiLong_PH'] else 0
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
            
            # Load Periods từ DB
            df_p = load_data('Periods')
            if df_p.empty:
                st.warning("Chưa có Đợt nào.")
                return None, False
            
            p_opts = df_p['TenDot'].tolist()
            idx = 0
            opens = df_p[df_p['TrangThai'] == 'Mở']['TenDot'].tolist()
            if opens and opens[0] in p_opts: idx = p_opts.index(opens[0])
            
            sel_period = st.selectbox("Chọn đợt:", p_opts, index=idx)
            
            # Lấy trạng thái đợt
            status = df_p[df_p['TenDot'] == sel_period].iloc[0]['TrangThai']
            is_open = (status == 'Mở')
            if is_open: st.success(f"Trạng thái: {status} 🟢")
            else: st.error(f"Trạng thái: {status} 🔒")
            
            with st.expander("🔑 Đổi mật khẩu"):
                with st.form("cp"):
                    np = st.text_input("Mật khẩu mới", type="password")
                    if st.form_submit_button("Lưu"):
                        target_email = u['Email'] # Mặc định là user hiện tại
                        if u['Role'] == 'PhuHuynh': target_email = u['ChildEmail'] # Logic cũ của anh
                        
                        if safe_update("Users", "Email", target_email, {"Password": np}):
                            st.success("Đổi thành công!")
                        else: st.error("Lỗi cập nhật.")
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
                # 1. Master Admin
                if email == "admin@school.com" and password == "123":
                    st.session_state.user = {'Email': email, 'Role': 'Admin', 'HoTen': 'Super Admin'}
                    cookie_manager.set("user_email", email, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                    st.rerun()
                
                # 2. Check Supabase Users
                # Truy vấn trực tiếp API - Siêu nhanh
                try:
                    # Check User thường
                    res = supabase.table('Users').select("*").eq('Email', email).eq('Password', password).execute()
                    if res.data:
                        st.session_state.user = res.data[0]
                        cookie_manager.set("user_email", email, expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                        st.rerun()
                    
                    # Check Phụ huynh
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
                    st.error("Lỗi kết nối Server.")

# =============================================================================
# 4. MODULE: ADMIN
# =============================================================================

def admin_view(period, is_open):
    st.title("🛡️ Admin Dashboard")
    t1, t2, t3 = st.tabs(["⚙️ Quản lý Đợt", "📊 Thống kê", "👨‍🏫 Giáo Viên"])
    
    with t1:
        with st.form("new_p"):
            np = st.text_input("Tên đợt mới (VD: HocKy1_2024)")
            if st.form_submit_button("➕ Tạo đợt"):
                if safe_insert("Periods", {"TenDot": np, "TrangThai": "Mở"}):
                    st.success("Tạo thành công!")
                    st.rerun()
        
        df_periods = load_data('Periods')
        if not df_periods.empty:
            for i, r in df_periods.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1.5, 1.5])
                    c1.write(f"**{r['TenDot']}**")
                    c2.markdown(f":green[{r['TrangThai']}]" if r['TrangThai']=='Mở' else f":red[{r['TrangThai']}]")
                    if c3.button("Đổi trạng thái", key=f"tg_{i}"):
                        new_stt = "Khóa" if r['TrangThai']=="Mở" else "Mở"
                        safe_update("Periods", "TenDot", r['TenDot'], {"TrangThai": new_stt})
                        st.rerun()

    with t2:
        st.subheader("Thống kê nhanh")
        # Logic thống kê giữ nguyên, chỉ thay load_data
        df_okr = load_data('OKRs')
        df_users = load_data('Users')
        if not df_users.empty and not df_okr.empty:
            df_gv = df_users[df_users['Role'] == 'GiaoVien']
            df_okr_p = df_okr[df_okr['Dot'] == period]
            
            stats = []
            for _, gv in df_gv.iterrows():
                lop = gv['Lop']
                class_okrs = df_okr_p[df_okr_p['Lop'] == lop]
                submitted = class_okrs['Email'].nunique()
                approved = class_okrs[class_okrs['TrangThai'] == 'Đã duyệt']['Email'].nunique()
                stats.append({"Lớp": lop, "GV": gv['HoTen'], "Nộp": submitted, "Duyệt": approved})
            st.dataframe(pd.DataFrame(stats), use_container_width=True)

    with t3:
        # Quản lý GV
        with st.form("add_gv"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Tên")
            l = c1.text_input("Lớp")
            s = c2.number_input("Sĩ số", 0)
            if st.form_submit_button("Thêm GV"):
                data = {"Email": e, "Password": "123", "Role": "GiaoVien", "HoTen": n, "Lop": l, "SiSo": s}
                if safe_insert("Users", data):
                    st.success("Thêm thành công")
                    st.rerun()
        
        df_gv = load_data('Users')
        if not df_gv.empty:
            st.dataframe(df_gv[df_gv['Role'] == 'GiaoVien'][['Email', 'HoTen', 'Lop', 'SiSo']])

# =============================================================================
# 5. TEACHER MODULE (FIX GIẬT LAG)
# =============================================================================

def teacher_view(period, is_open):
    user = st.session_state.user
    my_class = user['Lop']
    st.title(f"👩‍🏫 LỚP {my_class}")
    
    # Load Data
    df_users = load_data('Users')
    if df_users.empty: return
    df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == my_class)]
    
    df_okr = load_data('OKRs')
    df_okr = df_okr[df_okr['Dot'] == period] if not df_okr.empty else pd.DataFrame()
    
    df_rev = load_data('FinalReviews')
    df_rev = df_rev[df_rev['Dot'] == period] if not df_rev.empty else pd.DataFrame()
    
    t1, t2 = st.tabs(["🚀 Duyệt bài", "👥 Quản lý HS"])
    
    with t1:
        if df_hs.empty: st.info("Lớp chưa có học sinh")
        else:
            for idx, hs in df_hs.iterrows():
                email_hs = hs['Email']
                name_hs = hs['HoTen']
                
                # --- FIX: Kiểm tra xem có đang mở HS này không ---
                is_expanded = (st.session_state.active_expander == email_hs)
                
                # Filter Data
                hs_okrs = df_okr[df_okr['Email'] == email_hs] if not df_okr.empty else pd.DataFrame()
                hs_rev = df_rev[df_rev['Email'] == email_hs] if not df_rev.empty else pd.DataFrame()
                
                # Icon Status
                icon = "🔴"
                status_txt = "Chưa nộp"
                if not hs_okrs.empty:
                    if len(hs_okrs[hs_okrs['TrangThai'] == 'Đã duyệt']) == len(hs_okrs):
                        icon = "🟢"
                        status_txt = "Đã duyệt"
                    else:
                        icon = "🟡"
                        status_txt = "Chờ duyệt"
                
                # Render Expander
                with st.expander(f"{icon} {name_hs} ({status_txt})", expanded=is_expanded):
                    if hs_okrs.empty: st.warning("Chưa có OKR")
                    else:
                        for _, row in hs_okrs.iterrows():
                            c1, c2, c3 = st.columns([3, 1.5, 1.5])
                            c1.write(f"**{row['MucTieu']}** - {row['KetQuaThenChot']}")
                            c1.caption(f"{row['ThucDat']}/{row['MucTieuSo']} {row['DonVi']}")
                            
                            stt = row['TrangThai']
                            color = "green" if stt == "Đã duyệt" else "orange" if stt == "Chờ duyệt" else "red"
                            c2.markdown(f":{color}[{stt}]")
                            
                            if is_open:
                                # Logic duyệt
                                if stt != "Đã duyệt":
                                    if c3.button("Duyệt", key=f"app_{row['ID']}"):
                                        safe_update("OKRs", "ID", row['ID'], {"TrangThai": "Đã duyệt"})
                                        st.session_state.active_expander = email_hs # Ghi nhớ vị trí
                                        st.rerun()
                                if stt != "Cần sửa":
                                    if c3.button("Yêu cầu sửa", key=f"rej_{row['ID']}"):
                                        safe_update("OKRs", "ID", row['ID'], {"TrangThai": "Cần sửa"})
                                        st.session_state.active_expander = email_hs # Ghi nhớ vị trí
                                        st.rerun()
                            st.divider()
                    
                    # Đánh giá cuối kỳ
                    st.write("##### Đánh giá cuối kỳ")
                    cur_rv = hs_rev.iloc[0]['NhanXet_CuoiKy'] if not hs_rev.empty else ""
                    cur_stt = hs_rev.iloc[0]['TrangThai_CuoiKy'] if not hs_rev.empty else "Chưa chốt"
                    is_final = (cur_stt == 'Đã chốt')
                    
                    with st.form(key=f"rv_{email_hs}"):
                        txt = st.text_area("Nhận xét:", value=cur_rv)
                        chk = st.checkbox("Chốt sổ", value=is_final)
                        if st.form_submit_button("Lưu đánh giá"):
                            new_stt = "Đã chốt" if chk else "Chưa chốt"
                            # Check exist
                            if hs_rev.empty:
                                safe_insert("FinalReviews", {"Email": email_hs, "Dot": period, "NhanXet_CuoiKy": txt, "TrangThai_CuoiKy": new_stt})
                            else:
                                safe_update("FinalReviews", "id", hs_rev.iloc[0]['id'], {"NhanXet_CuoiKy": txt, "TrangThai_CuoiKy": new_stt})
                            
                            st.session_state.active_expander = email_hs # Ghi nhớ vị trí
                            st.rerun()

    with t2:
        # Quản lý HS (Thêm nhanh)
        with st.form("add_hs"):
            c1, c2 = st.columns(2)
            e = c1.text_input("Email")
            n = c2.text_input("Họ tên")
            ph = st.text_input("Email PH")
            if st.form_submit_button("Thêm HS"):
                if safe_insert("Users", {"Email": e, "Password": "123", "Role": "HocSinh", "HoTen": n, "Lop": my_class, "EmailPH": ph}):
                    st.success("Thêm thành công")
                    st.rerun()
        
        st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']], use_container_width=True)

# =============================================================================
# 6. STUDENT MODULE
# =============================================================================

def student_view(period, is_open):
    user = st.session_state.user
    st.title(f"🎓 {user['HoTen']}")
    
    # Load Data
    df_okr = load_data('OKRs')
    if not df_okr.empty:
        my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == period)]
    else: my_okrs = pd.DataFrame()
    
    df_rev = load_data('FinalReviews')
    if not df_rev.empty:
        my_rev = df_rev[(df_rev['Email'] == user['Email']) & (df_rev['Dot'] == period)]
    else: my_rev = pd.DataFrame()
    
    # 1. Feedback
    st.markdown("### 📝 Tổng kết")
    gv_txt = my_rev.iloc[0]['NhanXet_CuoiKy'] if not my_rev.empty and my_rev.iloc[0]['NhanXet_CuoiKy'] else "Chưa có nhận xét"
    st.info(f"**Giáo viên:** {gv_txt}")
    
    # 2. Add OKR
    if is_open:
        with st.expander("➕ Đăng ký OKR", expanded=True):
            with st.form("add_okr"):
                c1, c2 = st.columns(2)
                mt = c1.text_input("Mục tiêu")
                kr = c2.text_input("KR")
                c3, c4 = st.columns(2)
                tgt = c3.number_input("Đích", min_value=0.0)
                unit = c4.text_input("Đơn vị")
                if st.form_submit_button("Lưu"):
                    data = {
                        "Email": user['Email'], "Lop": user['Lop'], "Dot": period,
                        "MucTieu": mt, "KetQuaThenChot": kr, "MucTieuSo": tgt, 
                        "DonVi": unit, "ThucDat": 0, "TienDo": 0, "TrangThai": "Chờ duyệt"
                    }
                    if safe_insert("OKRs", data):
                        st.success("Đã lưu")
                        st.rerun()
    
    # 3. List
    st.subheader("Tiến độ của em")
    if my_okrs.empty: st.info("Chưa có OKR")
    else:
        for obj in my_okrs['MucTieu'].unique():
            with st.container(border=True):
                st.markdown(f"**🎯 {obj}**")
                for _, row in my_okrs[my_okrs['MucTieu'] == obj].iterrows():
                    st.divider()
                    st.markdown(f"**KR: {row['KetQuaThenChot']}** ({row['TrangThai']})")
                    c1, c2, c3 = st.columns([2, 3, 1])
                    c1.caption(f"Đích: {row['MucTieuSo']} {row['DonVi']}")
                    
                    if is_open and row['TrangThai'] == 'Đã duyệt':
                        # Update progress
                        new_val = c2.number_input(f"Thực đạt ({row['DonVi']})", value=float(row['ThucDat']), key=f"v_{row['ID']}")
                        prog = calculate_progress(new_val, row['MucTieuSo'])
                        c2.progress(int(prog))
                        
                        if c3.button("Cập nhật", key=f"up_{row['ID']}"):
                            safe_update("OKRs", "ID", row['ID'], {"ThucDat": new_val, "TienDo": prog})
                            st.success("Lưu!")
                            st.rerun()
                    else:
                        c2.progress(int(row['TienDo']))
                        c2.write(f"Đạt: {row['ThucDat']}")

# =============================================================================
# 7. PARENT & MAIN
# =============================================================================

def parent_view(period, is_open):
    user = st.session_state.user
    st.title(f"👨‍👩‍👧‍👦 PHHS: {user['ChildName']}")
    
    df_okr = load_data('OKRs')
    child_okrs = df_okr[(df_okr['Email'] == user['ChildEmail']) & (df_okr['Dot'] == period)] if not df_okr.empty else pd.DataFrame()
    
    if child_okrs.empty: st.info("Chưa có OKR")
    else:
        for _, row in child_okrs.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**KR:** {row['KetQuaThenChot']} ({row['TienDo']}%)")
                
                s = c2.slider("Sao", 1, 5, int(row['DiemHaiLong_PH']) if row['DiemHaiLong_PH'] else 0, key=f"s_{row['ID']}")
                if c2.button("Lưu", key=f"bs_{row['ID']}"):
                    safe_update("OKRs", "ID", row['ID'], {"DiemHaiLong_PH": s})
                    st.success("OK")

def main():
    # Auto Login check
    if st.session_state.user is None:
        c_email = cookie_manager.get(cookie="user_email")
        if c_email:
            try:
                # Check DB Supabase
                res = supabase.table('Users').select("*").eq('Email', c_email).execute()
                if res.data:
                    st.session_state.user = res.data[0]
            except: pass

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
