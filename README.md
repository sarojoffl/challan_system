# Challan System

A comprehensive Django delivery-challan initiation, approval, billing, and warehouse stock management platform. Designed for single-operator business workflows, featuring role separation between Admin supervisors and operational Staff.

---

## Features & Core Capabilities

### 📄 1. Dual Challan Workflows & Backdated Date Handling
* **Quotation-based Challan (Initiation Form)**:
  * Used for physical challan book entries.
  * Selecting **Company (or Firm)** automatically updates the code prefix label (e.g. `[ GLT- | _____ ]`).
  * Typing `101` generates `GLT-101`. Leaving it blank auto-fetches the next sequential number.
  * Integrated **Nepali Calendar (BS) Date Picker** supporting past/backdated transactions.
* **Hand Challan Form**:
  * Auto-generates clean tracking numbers (`HC-YYYYMMDD-001`).
  * Auto-approved and merged directly into the Challan Dashboard.
  * Integrated **Nepali Calendar (BS) Date Picker** for backdated entries.
* **Expanded & Categorized Item Units**:
  * Standardized units: `pcs`, `pair`, `set`, `box`, `pkt`, `bag`, `bundle`, `roll`, `meter`, `feet`, `kg`, `ltr`, `core`, `lot`, `truck`.
* **Goods Detail & Adjust Layout**:
  * Clean form layout keeping **Adjust / Material Replacement** options right after the **Goods Detail** section.

### 🇳🇵 2. Nepali Calendar (Bikram Sambat / BS) Integration
* **Seamless AD ↔ BS Conversion**: Interactive custom datepicker displaying Bikram Sambat months and years alongside standard Gregorian dates (e.g., `Bhadra 24, 2083`).
* **Clean Date Display**: Uniform date representation across all tables, tickets, badges, and export files without timestamp clutter.

### 🧾 3. Billing Context & In-Page Modal Previews
* **Manual Bill No. Input**: Specify exact invoice/bill numbers with dynamic company code prefixes (e.g. `GLT-`) when billing out approved challans.
* **Multi-Filter Bar**: Filter eligible un-billed challans by **Client**, **Company**, **From Date**, and **To Date** on `/billing/`.
* **In-Page Glassmorphism Modal Overlay**: Click any Challan No. in Billing Context to open an in-page modal iframe preview with smooth backdrop blur.
* **Navigation & Back Support**: Dedicated `← Back` button on Challan Details page with smart browser history fallback.

### ⏱️ 4. Challan Lifecycle & Time-Window Rules
* **Day 0 – 3 (Active Window)**: Full operational control to Edit, Void, or Approve pending challans.
* **24-Hour Grace Period for Backdated Entries**: Newly entered backdated challans receive a 24-hour grace window from entry time for edits and corrections before locking.
* **Day 3 – 7 (Overdue Warning Window)**: Prompted on the dashboard warning table.
  * **`Extend (+3 Days)`**: One-time 3-day extension requiring a mandatory reason.
  * **`Change Challan No.`**: Updating physical book numbers with a mandatory reason.
* **Day 7+ (Locked Out Window)**: System automatically locks expired challans. Operational buttons are disabled until an **Admin** clicks **`Unlock Challan`** in the Approvals Desk.

### 🛡️ 5. Approval Desks & Admin Control (`/admin-panel/`)
* **Material Replacement / Adjustment Approvals**: Challans marked with `Adjust ☑` require Admin approval before regular staff can complete them.
* **Void Approval Request Workflow**:
  * Staff requesting to void an **Approved** or **Locked** challan enter a mandatory reason.
  * Enters `⏳ Void Requested (Pending Admin Approval)` status.
  * Queued in the Approvals Desk for 1-click Admin approval.
* **Billed Out Lock**: Billed-out challans (`is_billed_out = True`) can never be voided or edited.

### 🏢 6. Company Management (`/companies/`)
* **Company CRUD**: Manage issuing companies (`Name` and `Code/Prefix`) via dedicated interface for Admins and Users.
* **Deletion Protection**: Built-in safety checks prevent deleting companies linked to existing challans or billing entries.

### 🔍 7. Dashboard & AJAX Filter Switching
* **Reload-Free AJAX Filtering**: Smooth tab and stat card filtering (`All`, `Pending`, `Approved`, `Billed`, `Void`) with instant DOM updates and auto-scroll to results.
* **Item Search by Name**: Search directly for item names (e.g., `Cisco`, `Fiber`, `Printer`, `Toner`) in the Dashboard search box (`q`) to find all matching challans.
* **Items Column**: Main Dashboard table features a dedicated **Items** column displaying product names and quantities (`Item (xQty)`) for every challan at a glance.

### 📦 8. Stock Catalog, Employee Intakes & Top-Ups (`/stock/intake/`)
* **Grouped by Employee**: Overview table cleanly organizes stock intakes into individual cards per employee.
* **Consolidated Top-Ups**: Top-ups merge into 1 row per employee per item, preserving the original **Intake Date** while tracking **Last Updated** date & time.
* **Stock Decreases**: Quick modal to deduct stock quantities upon issuance or consumption.

---

## System Architecture & App Layout

```
challan_system/
├── challan/
│   ├── models.py              # Company, Client, Challan, ChallanItem, Billing, StockItem, StockIntake
│   ├── forms.py               # Formsets with 1-indexed sequential S.N., date pickers & validation
│   ├── views.py               # Dashboard, Initiation, Hand Challan, Billing, Company CRUD, Stock Intake, & Admin Panel
│   ├── templatetags/          # nepali_date_tags for Bikram Sambat date formatting
│   ├── context_processors.py  # Live Admin pending counter badge processor
│   ├── urls.py                # App routing configuration
│   └── templates/challan/     # Glassmorphism UI templates extending base.html
├── challan_system/
│   ├── settings.py            # Project settings, STATIC_URL, timezone & DB config
│   └── urls.py                # Main URL router
├── static/css/style.css       # Custom Glassmorphism UI stylesheet (Plus Jakarta Sans font)
└── manage.py
```

---

## Local Setup & Installation

1. **Clone the repository**:
   ```bash
   git clone <repository_url>
   cd challan_system
   ```

2. **Set up virtual environment & dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run database migrations**:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Seed initial test data (Optional)**:
   ```bash
   python manage.py shell < scratch/seed_fresh_data.py
   ```

5. **Start local development server**:
   ```bash
   python manage.py runserver
   ```
   Visit `http://127.0.0.1:8000/` and log in with your credentials.

---

## User Roles & Accounts

* **Admin User (`admin`)**: Full supervisor access to Executive Dashboard, Approvals & Unlocks Desk (`/admin-panel/`), Company Management (`/companies/`), Stock Intake (`/stock/intake/`), and Billing History.
* **Regular Staff User (`user`)**: Operational data entry for Initiation Form, Hand Challan, Billing Context, Company Management, and Stock Intake.
