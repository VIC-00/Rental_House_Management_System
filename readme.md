# 🏠 Rental Home Management System (RHMS)

**RHMS** is a robust, Django-based **Property Management ERP** designed to bridge the gap between landlords, tenants, and maintenance staff. From tracking **payments** to managing **repair tickets**, RHMS centralizes the entire rental lifecycle into a single, intuitive interface.

---

## 🚀 Key Features

- **Triple-Role System**  
  Custom dashboards tailored for **Landlords** (analytics & oversight), **Tenants** (payments & issues), and **Maintenance Staff** (task tracking).

- **Smart Authentication**  
  Dual-identifier login (Username or Email) with a built-in **Security Guard** that forces tenants to update temporary passwords upon first login.

- **Financial Integrity**  
  An automated balance engine that recalculates tenant debt instantly whenever payments are confirmed, edited, or deleted.

- **Interactive Analytics**  
  Real-time data visualization using **Chart.js** to track revenue trends and maintenance distribution.

- **One-Click Compliance**  
  Exportable **CSV reports** for revenue summaries, tenant arrears, and maintenance history.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+ / Django 6.0  
- **Database:** SQLite (Development) / PostgreSQL (Production-ready)  
- **UI/UX:** HTML5, Vanilla JavaScript, CSS3 (custom variables), Bootstrap 5 via Crispy Forms  
- **Charts:** Chart.js  

---

## 🛠️ Step 1: Prerequisites

Ensure the following are installed:

- Python 3.10+
- pip
- Git

---

## 💻 Step 2: Installation & Setup

### 1. Clone & Enter the Project

    git clone <your-repository-link>
    cd RHMS

### 2. Set Up a Virtual Environment

**macOS / Linux**

    python3 -m venv venv
    source venv/bin/activate

**Windows**

    python -m venv venv
    venv\Scripts\activate

### 3. Install Dependencies

    pip install -r requirements.txt

---

## 🗄️ Step 3: Database & Superuser Initialization

> **Important:** RHMS uses a **Custom User Model**. The order below is critical.

### 1. Generate & Apply Migrations

    python manage.py makemigrations accounts
    python manage.py migrate

### 2. Create the Master Admin (Landlord)

    python manage.py createsuperuser

Follow the prompts to set your username, email, and password.

### 3. Assign the Landlord Role

    python manage.py runserver

Open your browser and go to:

    http://127.0.0.1:8000/admin

- Log in with your superuser account  
- Under **Users**, locate your account  
- Change **Role** to **Landlord**  
- Click **Save**

---

## 🛡️ Step 4: Security & Validation

### Password Strength

Enable strong password validation in `renthouse/settings.py`:

    AUTH_PASSWORD_VALIDATORS = [
        { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
        { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
        { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
        { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
    ]

---

## 🔑 Step 5: User Workflows

### 🏢 For Landlords (Manager)

- Dashboard:  
      
      http://127.0.0.1:8000/

- Add properties, units, and rent targets  
- Approve or manually onboard tenants  
- Confirm tenant payments to auto-update balances  

### 🏠 For Tenants (Resident)

- Self-register and wait for landlord approval  
- Change password on first login  
- Report maintenance issues  
- Submit formal move-out notices  

### 🛠️ For Maintenance Staff (Technician)

- Register and select a **Target Landlord**  
- View assigned tasks  
- Update task status: Assigned → In Progress → Completed  

---

## ⚙️ Step 6: Custom Management Commands

RHMS includes custom Django management commands to automate routine actions like billing and lease lifecycle management. These can be run manually or set up via cron jobs/task schedulers in production.

### 1. Generate Monthly Rent
Generates monthly rent charges for all active tenants. It automatically calculates and bills **pro-rated rent** for a tenant's first month based on their move-in date, and full rent amount thereafter. It includes safety checks to prevent double-billing for the same calendar month.

    python manage.py generate_rent

### 2. Check Lease Expirations
Scans the database and shifts active/notified tenants to `'expired'` status if their lease end date is in the past, updating their final balance ledger.

    python manage.py check_expired_leases

---

## 🧪 Step 7: Running Unit Tests

To run the verification test suite covering payment validations, pro-rata logic, and announcement broadcasting:

    python manage.py test

---

## ✉️ Step 8: Email & Notifications
During development, RHMS is configured to print emails (e.g., password reset requests, mass notifications) directly to the console:

- **Mail Backend**: `django.core.mail.backends.console.EmailBackend` (configured in `renthouse/settings.py`).
- Inspect your running server terminal output to view any sent email content.

---

## 📁 Project Structure

    renthouse/      # Core project configuration
    accounts/       # Core application logic
     ├── models.py  # Users, properties, tenants, payments
     ├── views.py   # Business logic and role handling
     ├── forms.py   # Styled Django ModelForms
    templates/      # HTML templates
    static/         # styles.css and main.js

---

## 🔍 Pro-Tip: Database Inspection

RHMS uses SQLite by default.

**Ubuntu**

    sudo apt install sqlitebrowser

**Windows / macOS**

    https://sqlitebrowser.org