# 🏠 Rental Home Management System (RHMS)

**RHMS** is a robust, Django-based **Property Management ERP** designed to bridge the gap between landlords, tenants, and maintenance staff. From tracking **payments** to managing **repair tickets**, RHMS centralizes the entire rental lifecycle into a single, intuitive interface.

---

## 🚀 Key Features

- **Triple-Role System**  
  Custom dashboards tailored for **Landlords** (analytics & oversight), **Tenants** (payments & issues), and **Maintenance Staff** (task tracking).

- **Smart Authentication**  
  Dual-identifier login (Username or Email) with a built-in **Security Guard** that forces tenants to update temporary passwords upon first login. Logout is CSRF-protected (POST-only).

- **Financial Integrity**  
  An automated balance engine that recalculates tenant debt instantly whenever payments are confirmed, edited, or deleted. Monthly rent charges are generated via a management command.

- **AI-Powered Features**  
  Powered by the Google Gemini API: AI-drafted announcements, automatic maintenance request classification (category + priority), a tenant virtual assistant chatbot, and daily landlord dashboard briefings.

- **Interactive Analytics**  
  Real-time data visualization using **Chart.js** to track revenue trends and maintenance distribution.

- **One-Click Compliance**  
  Exportable **CSV reports** for revenue summaries, tenant arrears, and maintenance history.

- **Mass Communications**  
  Broadcast messages to all tenants, tenants in arrears, or a specific tenant via Email and/or SMS channels, with a full delivery log.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.10+ / Django 6.0  
- **Database:** SQLite (Development) / PostgreSQL (Production-ready)  
- **UI/UX:** HTML5, Vanilla JavaScript, CSS3 (custom CSS variables + dark mode)  
- **Charts:** Chart.js  
- **AI:** Google Gemini API (`google-genai` SDK)  
- **Icons:** Font Awesome 6  

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

### 4. Configure Environment Variables

Copy the example environment file:

    cp .env.example .env

Open `.env` and verify/add your keys:

    SECRET_KEY=your-very-long-random-secret-key-here
    GEMINI_API_KEY=your-google-gemini-api-key-here

> **Generating a SECRET_KEY:** Run `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` and paste the output.  
> **Gemini API Key:** Get one free at [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). AI features will fail if this key is not set.

---

## 🗄️ Step 3: Database & Superuser Initialization

> **Important:** RHMS uses a **Custom User Model**. The order below is critical.

### 1. Apply Migrations

    python3 manage.py makemigrations accounts
    python3 manage.py migrate

### 2. Create the Master Admin (Landlord)

    python3 manage.py createsuperuser

Follow the prompts to set your username, email, and password.

### 3. Assign the Landlord Role & Approval

    python3 manage.py runserver

Open your browser and go to:

    http://127.0.0.1:8000/admin

- Log in with your superuser account  
- Under **Users**, locate your account  
- Change **Role** to **Landlord**  
- Check the **Is approved** box (required for landlord access)  
- Click **Save**

---

## 🛡️ Step 4: Security & Validation

### Password Strength

Password validators are currently **disabled** in `renthouse/settings.py` for development convenience. Before going to production, uncomment the `AUTH_PASSWORD_VALIDATORS` block in `settings.py` to enforce minimum length, common password checks, and numeric-only password rejection.

### Environment Variables

Ensure your `.env` file is never committed to version control. It is already listed in `.gitignore`.

---

## 🔑 Step 5: User Workflows

### 🏢 For Landlords (Manager)

- Dashboard:  
      
      http://127.0.0.1:8000/

- Add properties, units, and rent targets  
- Approve or manually onboard tenants  
- Confirm tenant payments to auto-update balances  
- Broadcast mass messages via Email/SMS  
- Post announcements to all tenants or a specific property  
- Use AI tools: draft announcements, classify maintenance, get dashboard insights  

### 🏠 For Tenants (Resident)

- Self-register and wait for landlord approval  
- Change password on first login (enforced automatically)  
- Report maintenance issues (AI auto-classifies category and priority)  
- Submit formal move-out notices  
- Chat with the AI tenant assistant  
- View all announcements from management  

### 🛠️ For Maintenance Staff (Technician)

- Register and select a **Target Landlord**  
- Wait for landlord approval before dashboard access  
- View assigned tasks  
- Update task status: Assigned → In Progress → Completed  

---

## ⚙️ Step 6: Custom Management Commands

RHMS includes custom Django management commands to automate routine actions like billing and lease lifecycle management. These can be run manually or set up via cron jobs/task schedulers in production.

### 1. Generate Monthly Rent

Generates monthly rent charges for all active tenants whose move-in date is today or in the past. Includes a safety lock to prevent double-billing for the same calendar month.

    python3 manage.py generate_rent

### 2. Check Lease Expirations

Scans the database and shifts active/notice-given tenants to `'expired'` status if their lease end date is in the past, then seals their final balance.

    python3 manage.py check_expired_leases

---

## 🧪 Step 7: Running Unit Tests

To run the verification test suite:

    python3 manage.py test

---

## ✉️ Step 8: Email & Notifications

During development, RHMS is configured to print emails (e.g., password reset requests, mass notifications) directly to the console:

- **Mail Backend**: `django.core.mail.backends.console.EmailBackend` (configured in `renthouse/settings.py`).
- Inspect your running server terminal output to view any sent email content.

For production, replace the mail backend with SMTP settings and add the credentials to your `.env` file.

---

## 🚢 Step 9: Production Checklist

Before deploying to production:

- [ ] Set `DEBUG = False` in `settings.py`
- [ ] Set a strong `SECRET_KEY` in `.env`
- [ ] Configure a real SMTP email backend
- [ ] Run `python3 manage.py collectstatic` (static files go to `staticfiles/`)
- [ ] Switch to PostgreSQL (update `DATABASES` in `settings.py`)
- [ ] Uncomment `AUTH_PASSWORD_VALIDATORS` in `settings.py`
- [ ] Set `ALLOWED_HOSTS` to your domain

---

## 📁 Project Structure

    renthouse/                          # Core project configuration
    accounts/                           # Core application logic
     ├── models.py                      # Users, properties, tenants, payments, announcements
     ├── views.py                       # Business logic and role-based routing
     ├── forms.py                       # Django ModelForms
     ├── admin.py                       # Django admin registrations
     ├── middleware.py                  # Password-change enforcement middleware
     ├── context_processors.py          # Global template context (tenant list, badge counts)
     ├── ai_utils.py                    # Google Gemini AI integration
     └── management/commands/           # Custom management commands
          ├── generate_rent.py          # Monthly billing engine
          └── check_expired_leases.py   # Lease expiry processor
    templates/                          # HTML templates
    static/                             # styles.css and main.js
    staticfiles/                        # Generated by collectstatic (gitignored)

---

## 🔍 Pro-Tip: Database Inspection

RHMS uses SQLite by default.

**Ubuntu**

    sudo apt install sqlitebrowser

**Windows / macOS**

    https://sqlitebrowser.org
