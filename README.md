# Challan System

A comprehensive Django delivery-challan initiation, approval, billing, and warehouse stock management platform. Designed for single-operator business workflows, featuring role separation between Admin supervisors and operational Staff.

---

## Features & Core Capabilities

### 📄 1. Dual Challan Workflows & Backdated Dates
* **Quotation-based Challan (Initiation Form)**:
  * Used for physical challan book entries.
  * Selecting a company automatically updates the code prefix label (e.g. `[ BPS- | _____ ]`).
  * Typing `101` generates `BPS-101`. Leaving it blank auto-fetches the next sequential number.
  * Customizable **Initiation Date** picker (`datetime-local`) to record past / backdated transactions.
* **Hand Challan Form**:
  * Auto-generates clean tracking numbers (`HC-YYYYMMDD-001`).
  * Auto-approved and merged directly into the Challan Dashboard.
  * Customizable **Hand Challan Date** picker (`datetime-local`) for backdated entries.
* **Goods Detail & Adjust Layout**:
  * Clean form layout keeping **Adjust / Material Replacement** options right after the **Goods Detail** section.

### 🧾 2. Billing Context & Manual Bill No. Entry
* **Manual Bill No. Input**: Specify exact invoice/bill numbers (e.g. `BILL-2026-001`) when billing out approved challans.
* **Date Range & Client Filters**: Filter eligible un-billed challans by **Client**, **From Date**, and **To Date** on `/billing/`.
* **Custom Billing Date**: Set exact **Billing Date** for past transaction logging.
* **Sidebar-Free Popup Detail Window**: Click any Challan No. in Billing Context to launch a clean modal popup window (`?popup=1`) showing details without sidebar/topbar clutter, with a 1-click `✕ Close Window` button.

### ⏱️ 3. Challan Lifecycle & Time-Window Rules
* **Day 0 – 3 (Active Window)**: Full operational control to Edit, Void, or Approve pending challans.
* **Day 3 – 7 (Overdue Warning Window)**: Prompted on the dashboard warning table.
  * **`Extend (+3 Days)`**: One-time 3-day extension requiring a mandatory reason.
  * **`Change Challan No.`**: Updating physical book numbers with a mandatory reason.
* **Day 7+ (Locked Out Window)**: System automatically locks expired challans. Operational buttons are disabled until an **Admin** clicks **`Unlock Challan`** in the Approvals Desk.

### 🛡️ 4. Approval Desks & Admin Control (`/admin-panel/`)
* **Material Replacement / Adjustment Approvals**: Challans marked with `Adjust ☑` require Admin approval before regular staff can complete them.
* **Void Approval Request Workflow**:
  * Staff requesting to void an **Approved** or **Locked** challan enter a mandatory reason.
  * Enters `⏳ Void Requested (Pending Admin Approval)` status.
  * Queued in the Approvals Desk for 1-click Admin approval.
* **Billed Out Lock**: Billed-out challans (`is_billed_out = True`) can never be voided or edited.

### 🏢 5. Company Management (`/companies/`)
* **Company CRUD**: Manage issuing companies (`Name` and `Code/Prefix`) via dedicated interface for Admins and Users.
* **Deletion Protection**: Built-in safety checks prevent deleting companies linked to existing challans or billing entries.

### 🔍 6. Advanced Dashboard & Item Search
* **Item Search by Name**: Search directly for item names (e.g., `Cisco`, `Fiber`, `Printer`, `CAR`) in the Dashboard search box (`q`) to find all matching challans.
* **Items Column**: Main Dashboard table features a dedicated **Items** column displaying product names and quantities (`Item (xQty)`) for every challan at a glance.
* **Multi-Criteria Filtering**: Filter by Search Query (`q`), Billed Company (`company`), Client (`client`), Challan Type (`type`), and **Date Range (`date_from` to `date_to`)**.

### 📦 7. Stock Catalog, Employee Intakes & Top-Ups (`/stock/intake/`)
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
│   ├── context_processors.py  # Live Admin pending counter badge processor
│   ├── urls.py                # App routing configuration
│   └── templates/challan/     # Glassmorphism UI templates extending base.html
├── challan_system/
│   ├── settings.py            # Project settings, STATIC_URL, FORCE_SCRIPT_NAME, timezone & DB config
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
