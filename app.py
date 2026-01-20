import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt
from io import BytesIO
import time
import uuid

# =============================================================================
# CẤU HÌNH & KẾT NỐI (CONFIGURATION & CONNECTION)
# =============================================================================

st.set_page_config(
    page_title="Hệ thống Quản lý OKR Trường Học",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CẤU HÌNH QUAN TRỌNG (ĐÃ CẬP NHẬT ID CỦA ANH) ---
SHEET_ID = "1iNzV2CIrPhdLqqXChGkTS-CicpAtEGRt9Qy0m0bzR0k"
MASTER_EMAIL = "admin@school.com"
MASTER_PASS = "123"

if 'user' not in st.session_state:
    st.session_state.user = None

# =============================================================================
# XỬ LÝ DỮ LIỆU & CACHE (DATA HANDLING & CACHING) - HIỆU SUẤT CAO
# =============================================================================

def get_gspread_client():
    """Kết nối Google Sheets sử dụng st.secrets"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Đọc thông tin xác thực từ secrets.toml
        # Lưu ý: Anh vẫn cần cấu hình [gcp_service_account] trong secrets
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
    """
    try:
        client = get_gspread_client()
        if not client: return pd.DataFrame()
        
        # SỬA: Mở bằng ID trực tiếp thay vì tên file
        sh = client.open_by_key(SHEET_ID)
        
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # Tự động tạo sheet nếu chưa có (Init)
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            # Khởi tạo header mặc định
            if sheet_name == 'Users':
                ws.append_row(['Email', 'Password', 'Role', 'HoTen', 'Lop', 'EmailPH'])
            elif sheet_name == 'OKRs':
                ws.append_row(['ID', 'Email', 'Lop', 'Dot', 'MucTieu', 'KetQua', 'TienDo', 'TrangThai', 'YeuCauXoa'])
            elif sheet_name == 'Reviews':
                ws.append_row(['Email', 'Dot', 'GV_Comment_1', 'GV_Status_1', 'GV_Comment_2', 'GV_Status_2', 'PH_Comment'])
            elif sheet_name == 'Settings':
                ws.append_row(['Key', 'Value'])
                ws.append_row(['CurrentDot', 'HocKy1'])
                ws.append_row(['IsActive', 'True'])
            return pd.DataFrame()

        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Chuyển đổi kiểu dữ liệu cơ bản để tránh lỗi
        if sheet_name == 'Users' and not df.empty:
            df['Password'] = df['Password'].astype(str)
        
        return df
    except Exception as e:
        st.error(f"Không thể tải dữ liệu {sheet_name}: {e}")
        return pd.DataFrame()

def clear_cache():
    """Xóa Cache khi có hành động Ghi/Sửa/Xóa"""
    st.cache_data.clear()

def save_dataframe(sheet_name, df):
    """Lưu toàn bộ DataFrame đè lên Sheet cũ"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID) # SỬA: Dùng ID
        ws = sh.worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")
        return False

def append_data(sheet_name, row_data):
    """Thêm 1 dòng dữ liệu"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID) # SỬA: Dùng ID
        ws = sh.worksheet(sheet_name)
        ws.append_row(row_data)
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi thêm dữ liệu: {e}")
        return False

def batch_append_data(sheet_name, data_list):
    """
    IMPORT EXCEL: Thêm nhiều dòng cùng lúc (Batch Processing).
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(SHEET_ID) # SỬA: Dùng ID
        ws = sh.worksheet(sheet_name)
        ws.append_rows(data_list)
        clear_cache()
        return True
    except Exception as e:
        st.error(f"Lỗi import dữ liệu hàng loạt: {e}")
        return False

# =============================================================================
# LOGIC NGHIỆP VỤ (BUSINESS LOGIC)
# =============================================================================

def get_current_dot():
    df = load_data('Settings')
    if df.empty: return "HocKy1"
    row = df[df['Key'] == 'CurrentDot']
    if not row.empty:
        return row.iloc[0]['Value']
    return "HocKy1"

def is_dot_active():
    df = load_data('Settings')
    if df.empty: return True
    row = df[df['Key'] == 'IsActive']
    if not row.empty:
        return str(row.iloc[0]['Value']).lower() == 'true'
    return True

# =============================================================================
# GIAO DIỆN NGƯỜI DÙNG (UI/UX)
# =============================================================================

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🔐 Đăng Nhập Hệ Thống OKR</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.form_submit_button("Đăng nhập", use_container_width=True)
            
            if submit:
                # 1. Check Master Key
                if email == MASTER_EMAIL and password == MASTER_PASS:
                    st.session_state.user = {
                        'Email': MASTER_EMAIL,
                        'Role': 'Admin',
                        'HoTen': 'Super Admin'
                    }
                    st.success("Đăng nhập Admin thành công (Master Key)!")
                    st.rerun()
                
                # 2. Check Database
                df_users = load_data('Users')
                if df_users.empty:
                    st.error("Chưa có dữ liệu người dùng (Hoặc lỗi kết nối Sheet).")
                else:
                    # Chuyển pass về string để so sánh
                    user_row = df_users[(df_users['Email'] == email) & (df_users['Password'].astype(str) == str(password))]
                    if not user_row.empty:
                        st.session_state.user = user_row.iloc[0].to_dict()
                        st.success(f"Xin chào {st.session_state.user['HoTen']}")
                        st.rerun()
                    else:
                        st.error("Sai Email hoặc Mật khẩu.")

# =============================================================================
# MODULE: ADMIN
# =============================================================================

def admin_interface():
    st.title("🛡️ Admin Dashboard")
    
    tab1, tab2, tab3 = st.tabs(["📊 Thống Kê", "⚙️ Cài Đặt Đợt", "👥 Quản Lý User"])
    
    with tab1:
        st.subheader("Thống kê toàn trường")
        df_okr = load_data('OKRs')
        df_users = load_data('Users')
        
        if not df_okr.empty and not df_users.empty:
            total_hs = len(df_users[df_users['Role'] == 'HocSinh'])
            total_okr = len(df_okr)
            approved = len(df_okr[df_okr['TrangThai'] == 'DaDuyet'])
            finished = len(df_okr[df_okr['TrangThai'] == 'HoanThanh'])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng Học Sinh", total_hs)
            c2.metric("Tổng OKR", total_okr)
            c3.metric("Đã Duyệt", approved)
            c4.metric("Hoàn Thành", finished)
            
            # Biểu đồ trạng thái
            st.write("---")
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.caption("Tỷ lệ trạng thái OKR")
                status_counts = df_okr['TrangThai'].value_counts()
                if not status_counts.empty:
                    fig, ax = plt.subplots()
                    ax.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', startangle=90)
                    ax.axis('equal')
                    st.pyplot(fig)
                else:
                    st.info("Chưa có OKR nào.")
            
            with col_chart2:
                st.caption("Số lượng OKR theo Lớp")
                if 'Lop' in df_okr.columns:
                    class_counts = df_okr['Lop'].value_counts()
                    st.bar_chart(class_counts)
        else:
            st.info("Chưa có dữ liệu thống kê.")

    with tab2:
        st.subheader("Quản lý Đợt Đánh Giá")
        current_dot = get_current_dot()
        is_active = is_dot_active()
        
        with st.form("settings_form"):
            new_dot = st.text_input("Tên Đợt Hiện Tại", value=current_dot)
            active_state = st.selectbox("Trạng Thái Đợt", ["Mở", "Khóa"], index=0 if is_active else 1)
            btn_save_settings = st.form_submit_button("Lưu Cài Đặt")
            
            if btn_save_settings:
                # Cập nhật Settings
                df_set = pd.DataFrame([
                    {'Key': 'CurrentDot', 'Value': new_dot},
                    {'Key': 'IsActive', 'Value': 'True' if active_state == "Mở" else 'False'}
                ])
                save_dataframe('Settings', df_set)
                st.success("Đã cập nhật cài đặt!")

    with tab3:
        st.subheader("Reset Mật Khẩu User")
        email_reset = st.text_input("Nhập Email cần reset pass")
        new_pass = st.text_input("Mật khẩu mới")
        if st.button("Đặt lại mật khẩu"):
            df_users = load_data('Users')
            if not df_users.empty and email_reset in df_users['Email'].values:
                df_users.loc[df_users['Email'] == email_reset, 'Password'] = new_pass
                save_dataframe('Users', df_users)
                st.success(f"Đã đổi mật khẩu cho {email_reset}")
            else:
                st.error("Email không tồn tại.")

# =============================================================================
# MODULE: GIÁO VIÊN (TEACHER)
# =============================================================================

def teacher_cascade_update_email(old_email, new_email, lop_quan_ly):
    """
    Cập nhật Email dây chuyền: Users -> OKRs -> Reviews
    """
    try:
        # 1. Update Users
        df_users = load_data('Users')
        idx = df_users[df_users['Email'] == old_email].index
        if not idx.empty:
            df_users.loc[idx, 'Email'] = new_email
            save_dataframe('Users', df_users)
        
        # 2. Update OKRs
        df_okr = load_data('OKRs')
        if not df_okr.empty:
            mask = df_okr['Email'] == old_email
            if mask.any():
                df_okr.loc[mask, 'Email'] = new_email
                save_dataframe('OKRs', df_okr)

        # 3. Update Reviews
        df_rev = load_data('Reviews')
        if not df_rev.empty:
            mask = df_rev['Email'] == old_email
            if mask.any():
                df_rev.loc[mask, 'Email'] = new_email
                save_dataframe('Reviews', df_rev)
        
        return True
    except Exception as e:
        st.error(f"Lỗi cập nhật dây chuyền: {e}")
        return False

def generate_word_report(df_hs, df_okr, df_review, current_dot):
    """Tạo file Word báo cáo"""
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    for _, hs in df_hs.iterrows():
        email_hs = hs['Email']
        doc.add_heading(f'PHIẾU ĐÁNH GIÁ OKR - {hs["HoTen"]}', 0)
        doc.add_paragraph(f"Lớp: {hs['Lop']} | Email: {email_hs}")
        doc.add_paragraph(f"Đợt: {current_dot}")
        
        # Bảng OKR
        hs_okrs = df_okr[df_okr['Email'] == email_hs] if not df_okr.empty else pd.DataFrame()
        if not hs_okrs.empty:
            table = doc.add_table(rows=1, cols=4)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Mục Tiêu'
            hdr_cells[1].text = 'Kết Quả Then Chốt'
            hdr_cells[2].text = 'Tiến Độ (%)'
            hdr_cells[3].text = 'Trạng Thái'
            
            for _, okr in hs_okrs.iterrows():
                row_cells = table.add_row().cells
                row_cells[0].text = str(okr['MucTieu'])
                row_cells[1].text = str(okr['KetQua'])
                row_cells[2].text = str(okr['TienDo'])
                row_cells[3].text = str(okr['TrangThai'])
        else:
            doc.add_paragraph("(Chưa có OKR)")

        # Nhận xét
        hs_rev = df_review[(df_review['Email'] == email_hs) & (df_review['Dot'] == current_dot)] if not df_review.empty else pd.DataFrame()
        doc.add_heading('Nhận xét & Đánh giá', level=2)
        if not hs_rev.empty:
            rev = hs_rev.iloc[0]
            doc.add_paragraph(f"GV Lần 1: {rev['GV_Comment_1']} (Kết quả: {rev['GV_Status_1']})")
            doc.add_paragraph(f"GV Lần 2: {rev['GV_Comment_2']} (Kết quả: {rev['GV_Status_2']})")
            doc.add_paragraph(f"Phụ Huynh: {rev['PH_Comment']}")
        else:
            doc.add_paragraph("(Chưa có đánh giá)")
            
        doc.add_page_break()
    
    bio = BytesIO()
    doc.save(bio)
    return bio

def teacher_interface():
    st.title(f"👩‍🏫 Giáo Viên Dashboard - {st.session_state.user['HoTen']}")
    gv_lop = st.session_state.user.get('Lop', '') 
    
    if not gv_lop:
        gv_lop = st.text_input("Nhập lớp bạn quản lý (VD: 10A1):")
    else:
        st.info(f"Đang quản lý lớp: {gv_lop}")

    if not gv_lop: return

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Quản Lý Học Sinh", "✅ Phê Duyệt OKR", "🗑️ Xử Lý Yêu Cầu Xóa", "🖨️ Xuất Báo Cáo"])

    # ---------------- TAB 1: QUẢN LÝ HS ----------------
    with tab1:
        st.subheader("Danh sách Học Sinh")
        df_users = load_data('Users')
        if df_users.empty:
             st.warning("Chưa có dữ liệu Users.")
             df_hs = pd.DataFrame()
        else:
            df_hs = df_users[(df_users['Role'] == 'HocSinh') & (df_users['Lop'] == gv_lop)]
            st.dataframe(df_hs[['Email', 'HoTen', 'EmailPH']])

        with st.expander("➕ Import Học Sinh từ Excel"):
            uploaded_file = st.file_uploader("Chọn file Excel (Cột: Email, HoTen, EmailPH)", type=['xlsx'])
            if uploaded_file and st.button("Import"):
                try:
                    df_upload = pd.read_excel(uploaded_file)
                    new_rows = []
                    for _, row in df_upload.iterrows():
                        if row['Email'] not in df_users['Email'].values:
                            new_rows.append([
                                str(row['Email']), "123", "HocSinh", str(row['HoTen']), gv_lop, str(row['EmailPH'])
                            ])
                    
                    if new_rows:
                        batch_append_data('Users', new_rows)
                        st.success(f"Đã thêm {len(new_rows)} học sinh!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("Không có dữ liệu mới hoặc Email đã tồn tại.")
                except Exception as e:
                    st.error(f"Lỗi file: {e}")

        with st.expander("✏️ Sửa Email / Xóa Học Sinh"):
            if not df_hs.empty:
                hs_email_action = st.selectbox("Chọn HS", df_hs['Email'].unique())
                col_a, col_b = st.columns(2)
                
                with col_a:
                    new_email_input = st.text_input("Email Mới")
                    if st.button("Cập nhật Email"):
                        if new_email_input and new_email_input != hs_email_action:
                            if teacher_cascade_update_email(hs_email_action, new_email_input, gv_lop):
                                st.success("Cập nhật thành công!")
                                st.rerun()

                with col_b:
                    if st.button("❌ Xóa Học Sinh Này", type="primary"):
                        df_users = df_users[df_users['Email'] != hs_email_action]
                        save_dataframe('Users', df_users) 
                        st.success("Đã xóa!")
                        st.rerun()

    # ---------------- TAB 2: PHÊ DUYỆT OKR ----------------
    with tab2:
        st.subheader("Duyệt & Đánh Giá OKR")
        df_okr = load_data('OKRs')
        df_reviews = load_data('Reviews')
        current_dot = get_current_dot()

        if df_hs.empty:
            st.warning("Chưa có học sinh.")
        else:
            hs_emails = df_hs['Email'].tolist()
            selected_hs = st.selectbox("Chọn Học Sinh để chấm", hs_emails)

            if selected_hs:
                hs_okrs = df_okr[(df_okr['Email'] == selected_hs) & (df_okr['Dot'] == current_dot)] if not df_okr.empty else pd.DataFrame()
                
                if hs_okrs.empty:
                    st.warning("Học sinh chưa tạo OKR đợt này.")
                else:
                    st.markdown("#### Chi tiết OKR")
                    def color_status(val):
                        color = 'black'
                        if val == 'ChoDuyet': color = 'orange'
                        elif val == 'DaDuyet': color = 'blue'
                        elif val == 'HoanThanh': color = 'green'
                        elif val == 'CanSua': color = 'red'
                        return f'color: {color}; font-weight: bold'

                    st.dataframe(hs_okrs[['ID', 'MucTieu', 'KetQua', 'TienDo', 'TrangThai']].style.map(color_status, subset=['TrangThai']))
                    
                    st.write("---")
                    st.markdown("#### 📝 Phần Phê Duyệt / Đánh Giá")
                    
                    curr_review = df_reviews[(df_reviews['Email'] == selected_hs) & (df_reviews['Dot'] == current_dot)] if not df_reviews.empty else pd.DataFrame()
                    
                    rev_g1 = curr_review.iloc[0]['GV_Comment_1'] if not curr_review.empty else ""
                    stat_g1 = curr_review.iloc[0]['GV_Status_1'] if not curr_review.empty else "Chưa Duyệt"
                    rev_g2 = curr_review.iloc[0]['GV_Comment_2'] if not curr_review.empty else ""
                    stat_g2 = curr_review.iloc[0]['GV_Status_2'] if not curr_review.empty else "Chưa Đánh Giá"
                    ph_comment = curr_review.iloc[0]['PH_Comment'] if not curr_review.empty else ""

                    st.info(f"💬 Ý kiến Phụ Huynh: {ph_comment}")

                    col_d1, col_d2 = st.columns(2)
                    
                    with col_d1:
                        st.markdown("**Lần 1: Duyệt Đề Xuất**")
                        new_rv1 = st.text_area("Nhận xét Lần 1", value=rev_g1)
                        # Xử lý index cho selectbox tránh lỗi nếu value k tồn tại
                        idx1 = ["Chưa Duyệt", "Đồng Ý", "Cần Sửa"].index(stat_g1) if stat_g1 in ["Chưa Duyệt", "Đồng Ý", "Cần Sửa"] else 0
                        new_st1 = st.selectbox("Trạng thái Lần 1", ["Chưa Duyệt", "Đồng Ý", "Cần Sửa"], index=idx1)
                    
                    with col_d2:
                        st.markdown("**Lần 2: Tổng Kết Cuối Đợt**")
                        new_rv2 = st.text_area("Nhận xét Lần 2", value=rev_g2, disabled=(stat_g1 != "Đồng Ý"))
                        idx2 = ["Chưa Đánh Giá", "Hoàn Thành", "Chưa Đạt"].index(stat_g2) if stat_g2 in ["Chưa Đánh Giá", "Hoàn Thành", "Chưa Đạt"] else 0
                        new_st2 = st.selectbox("Trạng thái Lần 2", ["Chưa Đánh Giá", "Hoàn Thành", "Chưa Đạt"], index=idx2, disabled=(stat_g1 != "Đồng Ý"))

                    if st.button("💾 Lưu Đánh Giá"):
                        new_review_row = {
                            'Email': selected_hs,
                            'Dot': current_dot,
                            'GV_Comment_1': new_rv1,
                            'GV_Status_1': new_st1,
                            'GV_Comment_2': new_rv2,
                            'GV_Status_2': new_st2,
                            'PH_Comment': ph_comment
                        }
                        
                        target_okr_status = "ChoDuyet"
                        if new_st1 == "Cần Sửa": target_okr_status = "CanSua"
                        elif new_st1 == "Đồng Ý": target_okr_status = "DaDuyet"
                        
                        if new_st2 == "Hoàn Thành": target_okr_status = "HoanThanh"
                        
                        if not df_reviews.empty:
                            df_reviews = df_reviews[~((df_reviews['Email'] == selected_hs) & (df_reviews['Dot'] == current_dot))]
                        
                        append_data('Reviews', list(new_review_row.values()))
                        
                        hs_okrs_idx = df_okr[(df_okr['Email'] == selected_hs) & (df_okr['Dot'] == current_dot)].index
                        if not hs_okrs_idx.empty:
                            df_okr.loc[hs_okrs_idx, 'TrangThai'] = target_okr_status
                            save_dataframe('OKRs', df_okr)
                        
                        st.success("Đã lưu đánh giá!")
                        st.rerun()

    # ---------------- TAB 3: XỬ LÝ YÊU CẦU XÓA ----------------
    with tab3:
        st.subheader("Yêu cầu xóa OKR từ Học Sinh")
        df_okr = load_data('OKRs')
        if not df_okr.empty:
            pending_deletes = df_okr[(df_okr['Lop'] == gv_lop) & (df_okr['YeuCauXoa'].astype(str) == 'TRUE')]
            
            if pending_deletes.empty:
                st.info("Không có yêu cầu xóa nào.")
            else:
                for idx, row in pending_deletes.iterrows():
                    col_del1, col_del2 = st.columns([3, 1])
                    with col_del1:
                        st.write(f"**{row['Email']}**: {row['MucTieu']} (ID: {row['ID']})")
                    with col_del2:
                        if st.button(f"Chấp nhận xóa ##{row['ID']}"):
                            df_okr = df_okr[df_okr['ID'] != row['ID']]
                            save_dataframe('OKRs', df_okr)
                            st.success("Đã xóa!")
                            st.rerun()
        else:
            st.info("Chưa có dữ liệu OKRs.")

    # ---------------- TAB 4: BÁO CÁO ----------------
    with tab4:
        st.subheader("Xuất Phiếu Kết Quả")
        col_rp1, col_rp2 = st.columns(2)
        
        with col_rp1:
            st.markdown("#### Từng Học Sinh")
            if not df_hs.empty:
                rp_hs = st.selectbox("Chọn HS xuất file", df_hs['Email'].tolist(), key='rp_hs_select')
                if st.button("Tải file Word cá nhân"):
                    d_hs = df_hs[df_hs['Email'] == rp_hs]
                    d_okr = df_okr
                    d_rev = df_reviews
                    docx_file = generate_word_report(d_hs, d_okr, d_rev, current_dot)
                    st.download_button("Download .docx", docx_file, f"OKR_{rp_hs}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            else:
                st.warning("Không có học sinh.")
        
        with col_rp2:
            st.markdown("#### Cả Lớp (Gộp)")
            if st.button("Tải file Word cả lớp"):
                d_hs = df_hs
                d_okr = df_okr
                d_rev = df_reviews
                docx_file = generate_word_report(d_hs, d_okr, d_rev, current_dot)
                st.download_button("Download All .docx", docx_file, f"OKR_Lop_{gv_lop}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# =============================================================================
# MODULE: HỌC SINH (STUDENT)
# =============================================================================

def student_interface():
    user = st.session_state.user
    st.title(f"🎓 Xin chào {user['HoTen']}")
    
    current_dot = get_current_dot()
    is_open = is_dot_active()
    
    st.info(f"Đợt hiện tại: **{current_dot}** | Trạng thái: **{'Đang Mở' if is_open else 'Đã Khóa'}**")
    
    df_okr = load_data('OKRs')
    my_okrs = pd.DataFrame()
    if not df_okr.empty:
        my_okrs = df_okr[(df_okr['Email'] == user['Email']) & (df_okr['Dot'] == current_dot)]
    
    if not my_okrs.empty:
        avg_progress = my_okrs['TienDo'].mean()
        st.progress(int(avg_progress))
        st.caption(f"Tiến độ trung bình: {avg_progress:.1f}%")
    
    with st.expander("➕ Thêm Mục Tiêu Mới", expanded=is_open):
        if is_open:
            with st.form("add_okr_form"):
                obj = st.text_input("Mục Tiêu (Objective)")
                kr = st.text_area("Kết Quả Then Chốt (Key Result)")
                submit_add = st.form_submit_button("Lưu Mục Tiêu")
                
                if submit_add and obj and kr:
                    new_id = str(uuid.uuid4())[:8]
                    new_okr = [
                        new_id, user['Email'], user['Lop'], current_dot,
                        obj, kr, 0, "ChoDuyet", "FALSE" # Mặc định ChoDuyet
                    ]
                    append_data('OKRs', new_okr)
                    st.success("Đã thêm! Đang chờ GV duyệt.")
                    st.rerun()
        else:
            st.warning("Đợt đánh giá đã khóa, không thể thêm mới.")

    st.subheader("Danh sách Mục Tiêu Của Tôi")
    if my_okrs.empty:
        st.write("Bạn chưa có mục tiêu nào.")
    else:
        for idx, row in my_okrs.iterrows():
            with st.container(border=True):
                status_color = "gray"
                if row['TrangThai'] == 'DaDuyet': status_color = "blue"
                elif row['TrangThai'] == 'CanSua': status_color = "red"
                elif row['TrangThai'] == 'HoanThanh': status_color = "green"
                elif row['TrangThai'] == 'ChoDuyet': status_color = "orange"
                
                st.markdown(f"<h4 style='color:{status_color}'>{row['MucTieu']} <small>({row['TrangThai']})</small></h4>", unsafe_allow_html=True)
                st.write(f"**KR:** {row['KetQua']}")
                
                c1, c2 = st.columns([3, 1])
                with c1:
                    new_prog = st.slider(f"Tiến độ ##{row['ID']}", 0, 100, int(row['TienDo']), key=f"sl_{row['ID']}", disabled=not is_open)

                with c2:
                    if is_open:
                        if st.button("Cập nhật", key=f"up_{row['ID']}"):
                            df_okr.loc[df_okr['ID'] == row['ID'], 'TienDo'] = new_prog
                            if row['TrangThai'] == 'CanSua':
                                df_okr.loc[df_okr['ID'] == row['ID'], 'TrangThai'] = 'ChoDuyet'
                            save_dataframe('OKRs', df_okr)
                            st.success("Đã lưu!")
                            st.rerun()
                            
                        if st.button("Yêu cầu Xóa", key=f"del_{row['ID']}"):
                            df_okr.loc[df_okr['ID'] == row['ID'], 'YeuCauXoa'] = 'TRUE'
                            save_dataframe('OKRs', df_okr)
                            st.warning("Đã gửi yêu cầu xóa cho GVCN.")
                            st.rerun()

# =============================================================================
# MODULE: PHỤ HUYNH (PARENT)
# =============================================================================

def parent_interface():
    user = st.session_state.user
    st.title("👨‍👩‍👧‍👦 Phụ Huynh Dashboard")
    
    df_users = load_data('Users')
    if df_users.empty:
        st.error("Chưa có dữ liệu Users.")
        return

    children = df_users[df_users['EmailPH'] == user['Email']]
    
    if children.empty:
        st.warning("Không tìm thấy thông tin học sinh liên kết với tài khoản này.")
        return
    
    child_selected = st.selectbox("Chọn con:", children['HoTen'] + " - " + children['Email'])
    child_email = child_selected.split(" - ")[1]
    
    current_dot = get_current_dot()
    
    st.subheader(f"Kết quả OKR - {child_selected}")
    
    df_okr = load_data('OKRs')
    if not df_okr.empty:
        child_okrs = df_okr[(df_okr['Email'] == child_email) & (df_okr['Dot'] == current_dot)]
        st.dataframe(child_okrs[['MucTieu', 'KetQua', 'TienDo', 'TrangThai']])
    else:
        st.info("Chưa có dữ liệu OKRs.")
    
    st.write("---")
    st.subheader("Phản hồi từ Gia đình & Nhà trường")
    
    df_reviews = load_data('Reviews')
    review_row = df_reviews[(df_reviews['Email'] == child_email) & (df_reviews['Dot'] == current_dot)] if not df_reviews.empty else pd.DataFrame()
    
    gv_cmt = "Chưa có nhận xét"
    ph_cmt_old = ""
    
    if not review_row.empty:
        r = review_row.iloc[0]
        gv_cmt = f"**GV Lần 1:** {r['GV_Comment_1']} ({r['GV_Status_1']})\n\n**GV Lần 2:** {r['GV_Comment_2']} ({r['GV_Status_2']})"
        ph_cmt_old = r['PH_Comment']
        
    st.info(gv_cmt)
    
    with st.form("ph_comment_form"):
        new_ph_cmt = st.text_area("Ý kiến của Phụ Huynh:", value=str(ph_cmt_old))
        submit_ph = st.form_submit_button("Gửi Nhận Xét")
        
        if submit_ph:
            if review_row.empty:
                new_data = [child_email, current_dot, "", "", "", "", new_ph_cmt]
                append_data('Reviews', new_data)
            else:
                idx = review_row.index
                df_reviews.loc[idx, 'PH_Comment'] = new_ph_cmt
                save_dataframe('Reviews', df_reviews)
            st.success("Cảm ơn đóng góp của quý phụ huynh!")
            st.rerun()

# =============================================================================
# MAIN APP ROUTING
# =============================================================================

def main():
    if st.session_state.user is None:
        login_ui()
    else:
        with st.sidebar:
            st.write(f"User: **{st.session_state.user['HoTen']}**")
            if st.button("Đăng xuất"):
                st.session_state.user = None
                st.rerun()
        
        role = st.session_state.user['Role']
        
        try:
            if role == 'Admin':
                admin_interface()
            elif role == 'GiaoVien':
                teacher_interface()
            elif role == 'HocSinh':
                student_interface()
            elif role == 'PhuHuynh':
                parent_interface()
            else:
                st.error("Vai trò không hợp lệ.")
        except Exception as e:
            st.error(f"Đã xảy ra lỗi hệ thống: {e}")

if __name__ == "__main__":
    main()
