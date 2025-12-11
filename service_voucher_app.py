import streamlit as st
import pandas as pd
import io
import json
import uuid
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
# Libraries for Firestore 
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. SETUP & CONFIGURATION ---
st.set_page_config(page_title="Odaduu Service & Quote Generator", page_icon="🇯🇵", layout="wide")

# --- CUSTOM BRANDING (ODADUU) ---
# Note: Color definitions are placeholders until PDF module
OD_COMPANY_NAME = "Odaduu Travel DMC"
OD_EMAIL = "sales@odaduu.jp" 

# --- FIRESTORE INITIALIZATION ---
def initialize_firestore():
    """Initializes Firestore connection using Streamlit secrets."""
    try:
        if "firestore_initialized" not in st.session_state and "firestore_key" in st.secrets:
            # Check if secrets are present before trying to load
            if "firestore_key" in st.secrets:
                key_dict = json.loads(st.secrets["firestore_key"])
                cred = credentials.Certificate(key_dict)
                firebase_admin.initialize_app(cred)
                st.session_state.firestore_initialized = True
            else:
                 return None

        return firestore.client()
    except Exception as e:
        return None

db = initialize_firestore()
# --- END FIRESTORE INITIALIZATION ---


# --- AUTHENTICATION MODULE ---
def check_password():
    """Returns True if the user enters the correct credentials."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    def password_entered():
        # Requires [auth] section in secrets.toml
        if "auth" in st.secrets and (st.session_state["username"] == st.secrets["auth"]["username"] and
            st.session_state["password"] == st.secrets["auth"]["password"]):
            st.session_state["authenticated"] = True
            st.session_state["logged_in_user"] = st.session_state["username"] 
            del st.session_state["password"] 
            st.rerun()
        else:
            st.session_state["authenticated"] = False
            st.error("Login failed: Incorrect username or password.")
            if "password" in st.session_state:
                del st.session_state["password"] 

    if not st.session_state["authenticated"]:
        st.title(f"{OD_COMPANY_NAME} Sales Login")
        st.text_input("Username", key="username")
        st.text_input("Password", type="password", key="password", on_change=password_entered)
        return False
    return True
# --- END AUTHENTICATION ---


# --- 2. DATABASE SAVE FUNCTION ---

def save_voucher_to_db(doc_type, doc_data, structured_data, total_quote, username):
    """Saves the final structured data and status to Firestore."""
    if db is None:
        st.error("Database is not connected. Cannot save voucher history.")
        return False
        
    try:
        record = {
            "created_at": firestore.SERVER_TIMESTAMP,
            "created_by": username, 
            "guest_name": doc_data['guest_name'],
            "pax_count": doc_data['pax_count'],
            "date_start": doc_data['date_start'].isoformat(),
            "date_end": doc_data['date_end'].isoformat(),
            "total_quote_jpy": total_quote if total_quote is not None else 0,
            "doc_type": doc_type, 
            "status": "Quoted" if doc_type == 'QUOTE' else "Confirmed",
            "itinerary_data": structured_data 
        }
        
        db.collection("vouchers").add(record)
        return True
    except Exception as e:
        st.error(f"Failed to save to Firestore. Details: {e}")
        return False

# --- 3. DATA LOADING & HELPER FUNCTIONS ---

@st.cache_data
def load_rates(uploaded_files):
    # Dummy data for Phase 1 testing
    master_df = pd.DataFrame(columns=['City', 'Service Name', 'Service Type', 'Base Price'])
    dummy_data = [
        ['Tokyo', 'Tokyo Full Day Private Tour', 'Tour', 50000],
        ['Kyoto', 'Kyoto Highlights Shared Tour', 'Tour', 15000],
        ['Tokyo', 'NRT Airport Transfer Private', 'Transfer', 25000],
        ['Tokyo', 'Tokyo Skytree Ticket', 'Activity/Ticket', 2500],
        ['Japan', 'JR Pass 7 Day', 'Activity/Ticket', 40000]
    ]
    master_df = pd.concat([master_df, pd.DataFrame(dummy_data, columns=['City', 'Service Name', 'Service Type', 'Base Price'])], ignore_index=True)
    return master_df

if 'itinerary_cart' not in st.session_state:
    st.session_state.itinerary_cart = []
if 'total_quote' not in st.session_state:
    st.session_state.total_quote = 0.0

def add_to_cart(day, service_type, service_name, pax, cost, item_details=""):
    item_id = str(uuid.uuid4())
    st.session_state.itinerary_cart.append({
        'id': item_id, 
        'day': day,
        'type': service_type,
        'name': service_name,
        'pax': pax,
        'details': item_details,
        'cost': cost
    })
    st.session_state.total_quote += cost

def remove_from_cart(item_id, cost):
    st.session_state.itinerary_cart = [item for item in st.session_state.itinerary_cart if item['id'] != item_id]
    st.session_state.total_quote -= cost

def clear_cart():
    st.session_state.itinerary_cart = []
    st.session_state.total_quote = 0.0

# --- 5. AI & PDF PLACEHOLDERS ---

def structure_itinerary_data(*args):
    # Placeholder for Phase 1 DB Test
    return {"itinerary_summary": "Test DB connection structure ok."} 

def draw_pdf_content(*args):
    # Placeholder PDF generation for DB Test
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(100, 750, f"{OD_COMPANY_NAME} VOUCHER (TEST)")
    c.save()
    buffer.seek(0)
    return buffer

# --- MAIN APPLICATION START ---
if check_password():
    # --- UI LAYOUT ---
    username = st.session_state["logged_in_user"]
    st.sidebar.title(f"Welcome, {username}")
    st.title(f"🏯 {OD_COMPANY_NAME} Service & Quote Generator")
    
    # --- TAB NAVIGATION ---
    tab1, tab2, tab3 = st.tabs(["🇯🇵 Itinerary Builder", "📜 Quote History", "🖼️ Image Test"])
    
    with tab1:
        
        # --- File Uploader for Rates (Sidebar) ---
        with st.sidebar:
            st.header("Admin Price Sheets")
            # Check DB status
            if db is not None and "firestore_key" in st.secrets:
                st.success("Database Connected! (Firestore)")
            else:
                st.error("Database Disconnected! Check secrets.")

            uploaded_rate_files = st.file_uploader(
                "Drop all rate sheets (.csv/.xlsx)",
                type=['csv', 'xlsx'],
                accept_multiple_files=True,
                key="rate_uploader"
            )

            master_rates_df = pd.DataFrame()
            if uploaded_rate_files:
                master_rates_df = load_rates(uploaded_rate_files)
                st.success(f"Loaded {len(master_rates_df)} items (Dummy Filtered).")
            else:
                st.warning("Upload rates to enable quoting.")


        # --- MAIN FORM (Itinerary Builder) ---
        with st.form("itinerary_builder_form"):
            st.markdown("### A. Trip Details")
            col1, col2 = st.columns(2)
            
            initial_start_date = datetime.now().date() + timedelta(days=30)
            
            with col1:
                guest_name = st.text_input("Lead Guest Name(s)", value="DB TEST CLIENT")
                pax_count = st.number_input("Total No. of Pax", min_value=1, value=2, key="pax_count_input")
                cities_raw = st.text_input("Cities Covered", value="Tokyo, Kyoto")
            
            with col2:
                date_start = st.date_input("Travel Start Date", value=initial_start_date)
                date_end = st.date_input("Travel End Date", value=date_start + timedelta(days=7), min_value=date_start + timedelta(days=1))
                
                emergency_contact = st.text_input("Emergency Contact (Japan)", value="24/7 Helpline: +81 90-XXXX-XXXX")

            num_days = (date_end - date_start).days + 1
            
            st.markdown("### B. Build Itinerary (Day-by-Day)")
            st.info(f"Current Package Cost Estimate (Internal Running Total): ¥{st.session_state.total_quote:,.0f}")

            # --- DYNAMIC SERVICE BUILDER ---
            with st.container(border=True):
                st.markdown("##### Add New Service Item")
                
                col_b1, col_b2, col_b3 = st.columns([1, 1, 1.5])
                
                with col_b1:
                    day_to_add = st.number_input("Select Day", min_value=1, max_value=num_days, value=1, key="day_to_add")
                    
                    service_types = master_rates_df['Service Type'].unique().tolist()
                    service_types.extend(['Hotel', 'Meal Voucher', 'Free Spot'])
                    
                    service_type = st.selectbox(
                        "Service Category",
                        [''] + service_types,
                        key="builder_service_type"
                    )
                    
                with col_b2:
                    current_services = master_rates_df[master_rates_df['Service Type'] == service_type]['Service Name'].tolist()
                    
                    service_name_selected = st.selectbox(
                        "Select Service Item",
                        [''] + current_services,
                        key="builder_service_name_selected"
                    )
                    
                    service_name_final = service_name_selected
                    cost = 0.0
                    
                    if service_name_selected and not master_rates_df.empty:
                        rate_row = master_rates_df[master_rates_df['Service Name'] == service_name_selected]
                        if not rate_row.empty:
                            base_price = rate_row.iloc[0]['Base Price']
                            cost = base_price * pax_count
                    
                    if service_type in ['Hotel', 'Meal Voucher', 'Free Spot']:
                        service_name_final = st.text_input(f"Enter {service_type} Name/Title", key="builder_custom_name")
                        cost = 0.0
                        
                    st.markdown(f"**Calculated Cost: ¥{cost:,.0f}**")
                    
                with col_b3:
                    details_input = st.text_area("Details (Conf#, Car Type, Notes for AI)", key="builder_details_input", height=100, 
                                                 value="[Enter Conf#/Notes/Free Item Details for AI]")
                    
                    if st.button(f"➕ Add Day {day_to_add} Item", key="add_item_button", use_container_width=True):
                        if service_type and service_name_final:
                            add_to_cart(day_to_add, service_type, service_name_final, pax_count, cost, details_input)
                            st.rerun() 
                        else:
                            st.error("Please select a valid Service Category and Item Name.")


            # --- C. CURRENT ITINERARY CART DISPLAY (with Deletion per Item) ---
            if st.session_state.itinerary_cart:
                st.subheader("Current Itinerary Cart (Review & Edit)")
                
                # Custom table header 
                cols = st.columns([0.5, 0.5, 1.5, 2, 1, 0.5])
                cols[0].write("**Day**")
                cols[1].write("**Type**")
                cols[2].write("**Service Name**")
                cols[3].write("**Details**")
                cols[4].write("**Cost (JPY)**")
                cols[5].write("**Action**")
                st.divider()

                # Display items and delete buttons
                for item in sorted(st.session_state.itinerary_cart, key=lambda x: x['day']):
                    col_d = st.columns([0.5, 0.5, 1.5, 2, 1, 0.5])
                    col_d[0].write(str(item['day']))
                    col_d[1].write(item['type'])
                    col_d[2].write(item['name'])
                    col_d[3].write(item['details'][:40] + '...' if len(item['details']) > 40 else item['details'])
                    col_d[4].write(f"¥{item['cost']:,.0f}")
                    
                    # DELETE BUTTON per item
                    if col_d[5].button("❌", key=f"del_{item['id']}", help="Remove this item"):
                        remove_from_cart(item['id'], item['cost'])
                        st.rerun()

                st.markdown("---")
                if st.button("🗑️ Clear Entire Package (All Items)"):
                    clear_cart()
                    st.rerun()
            

            # --- D. FINAL SUBMISSION ---
            st.markdown("### D. Document Generation and Save")
            
            col_q, col_s = st.columns(2)
            
            with col_q:
                submit_quote = st.form_submit_button("💰 Generate QUOTE & SAVE", type="secondary")
            with col_s:
                submit_service = st.form_submit_button("✅ Generate SERVICE & SAVE", type="primary")

        # --- SUBMISSION HANDLER ---
        if submit_quote or submit_service:
            if not guest_name or not st.session_state.itinerary_cart:
                st.error("Please ensure the Lead Guest Name is filled and the Itinerary Cart is not empty.")
            elif db is None:
                st.error("Cannot proceed: Database is not connected. Check Admin settings.")
            else:
                doc_type = 'QUOTE' if submit_quote else 'SERVICE'
                total_quote = st.session_state.total_quote
                
                pdf_input_data = {
                    "guest_name": guest_name, "pax_count": pax_count, 
                    "date_start": date_start, "date_end": date_end,
                }

                # Step 1: AI Structuring (Placeholder for Phase 1)
                structured_data = structure_itinerary_data(st.session_state.itinerary_cart, pax_count, cities_raw, date_start)
                
                # Step 2: Database Save
                db_success = save_voucher_to_db(doc_type, pdf_input_data, structured_data, total_quote, st.session_state.logged_in_user)
                
                if db_success:
                    st.success(f"✅ Document generated AND successfully saved to Firestore history!")
                    
                    # Step 3: PDF Download (Placeholder for Phase 1)
                    pdf_buffer = draw_pdf_content(doc_type, pdf_input_data, structured_data, total_quote)
                    st.download_button(
                        f"⬇️ Download {doc_type.capitalize()} Voucher",
                        pdf_buffer,
                        f"Odaduu_Voucher_{doc_type}_{guest_name.replace(' ', '_')}.pdf",
                        "application/pdf",
                        type="primary"
                    )
                else:
                    st.error("❌ Document generated but FAILED to save to database.")

    # Placeholder for other tabs (Phase 4)
    with tab2:
        st.header("Quote History & Audit")
        st.warning("This feature will be built in Phase 4.")
    with tab3:
        st.header("Image Generation Test")
        st.warning("This feature will be built in Phase 3.")

### ⏭️ Your Next Step: Testing

Now that you have the files ready, you need to complete the deployment and set up the secrets.

1.  **Log into Streamlit Cloud** (share.streamlit.io).
2.  **Deploy the App:** Click **New App** and select the GitHub repository you just created (`odaduu-service-generator`). Set the **Main file path** to `service_voucher_app.py`.
3.  **Set Secrets:** Click the **Advanced Settings** dropdown and find the **Secrets** section. Paste the following content into the single text area, replacing the placeholders with your actual keys and desired login credentials:

    ```toml
    # 1. Login Credentials
    [auth]
    username = "sales_agent"  # Your desired login username
    password = "secure_password" # Your desired login password

    # 2. Firestore Service Account Key
    [firestore_key]
    # PASTE THE ENTIRE JSON CONTENT OF YOUR GOOGLE FIRESTORE SERVICE ACCOUNT KEY HERE
    # Ensure it is formatted correctly as a TOML table, starting with:
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "..."
    # ... rest of the JSON key content
    ```

4.  **Click Deploy!**

**Your task now is to successfully complete this deployment. Please report the outcome (success or error) for the Login and the Database Save.**