# Challan System

A comprehensive Django delivery-challan initiation, approval, billing, and warehouse stock management platform. Designed for single-operator business workflows, featuring role separation between Admin supervisors and operational Staff.

---

## Features & Core Capabilities

### 📄 1. Dual Challan Workflows
* **Quotation-based Challan (Initiation Form)**:
  * Used for physical challan book entries.
  * Selecting a company automatically updates the code prefix label (e.g. `[ BPS- | _____ ]`).
  * Typing `101` generates `BPS-101`. Leaving it blank auto-fetches the next sequential number.
* **Hand Challan Form**:
  * Auto-generates clean tracking numbers (`HC-YYYYMMDD-001`).
  * Auto-approved and merged directly into the Challan Dashboard.

### ⏱️ 2. Challan Lifecycle & Time-Window Rules
* **Day 0 – 3 (Active Window)**: Full operational control to Edit, Void, or Approve pending challans.
* **Day 3 – 7 (Overdue Warning Window)**: Prompted on the dashboard warning table.
  * **`Extend (+3 Days)`**: One-time 3-day extension requiring a mandatory reason.
  * **`Change Challan No.`**: Updating physical book numbers with a mandatory reason.
* **Day 7+ (Locked Out Window)**: System automatically locks expired challans. Operational buttons are disabled until an **Admin** clicks **`Unlock Challan`** in the Approvals Desk.

### 🛡️ 3. Approval Desks & Admin Control (`/admin-panel/`)
* **Material Replacement / Adjustment Approvals**: Challans marked with `Adjust ☑` require Admin approval before regular staff can complete them.
* **Void Approval Request Workflow**:
  * Staff requesting to void an **Approved** or **Locked** challan enter a mandatory reason.
  * Enters `⏳ Void Requested (Pending Admin Approval)` status.
  * Queued in the Approvals Desk for 1-click Admin approval.
* **Billed Out Lock**: Billed-out challans (`is_billed_out = True`) can never be voided or edited.

### 🔍 4. Dashboard & Billing History Filters
* **Multi-Criteria Filtering**: Filter by Search Query (`q`), Billed Company (`company`), Client (`client`), Challan Type (`type`), and **Date Range (`date_from` to `date_to`)**.
* Available on both the **Main Dashboard** (`/`) and **Billing History** (`/billing/history/`).

### 📦 5. Stock Catalog & Employee Allocation
* **Stock Catalog (`StockItem`)**: Running stock tracking fed by **Stock Intake** (`StockIntake`).
* **Employee Stock Issuance (`EmployeeStockChallan`)**: Issue warehouse items to staff with merged dashboard visibility.
* **Employee Stock Overview (`/stock/employee/<name>/`)**: Comprehensive per-employee equipment allocation log with canonical URL unquoting and double-encoding redirect protection.

---

## System Architecture & App Layout

```
challan_system/
├── challan/
│   ├── models.py              # Company, Client, Challan, ChallanItem, Billing, StockItem, StockIntake, EmployeeStockChallan
│   ├── forms.py               # Formsets with 1-indexed sequential S.N. assignment & custom validation
│   ├── views.py               # Dashboard, Initiation, Hand Challan, Billing, Stock, Admin Panel, & API endpoints
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

3. **Run database migrations & seed initial data**:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Start local development server**:
   ```bash
   python manage.py runserver
   ```
   Visit `http://127.0.0.1:8000/` and log in with your credentials.

---

## Deployment (cPanel / Phusion Passenger WSGI)

When deploying to cPanel or Phusion Passenger WSGI (`https://store.globallinknepal.com`):

1. Ensure static and script settings in `challan_system/settings.py` are set to:
   ```python
   STATIC_URL = "/static/"
   FORCE_SCRIPT_NAME = ""
   ```
2. Collect static files:
   ```bash
   python manage.py collectstatic --noinput
   ```
3. Restart Python App in cPanel **Setup Python App** dashboard (or `touch tmp/restart.txt`).

---

## User Roles & Accounts

* **Admin User (`admin`)**: Access to Executive Dashboard, Approvals & Unlocks Desk (`/admin-panel/`), Executive Stock Summary (`/stock/summary/`), and Billing History.
* **Regular Staff User (`user`)**: Operational data entry for Initiation Form, Hand Challan, Billing Context, Stock Intake, and Employee Stock issuance.
