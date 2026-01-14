```
# SCUN IBC SAC Smart Booking System

## Project Overview
The **SCUN IBC SAC Smart Booking System** is a lightweight classroom resource management platform designed for the International Business College (IBC) at South China Normal University. The system aims to resolve booking conflicts for laboratories and meeting rooms through a visual Web interface, automated email notifications, and an AI intelligent assistant.

Built on Python FastAPI, this project is designed for local server deployment, offering stability and out-of-the-box functionality.

## Core Features

* **Resource Dashboard**: Real-time display of weekly/daily occupancy for all laboratories (distinguishing between "Free", "Pending", and "Taken" statuses).
* **Role-Based Access**:
    * **Student Mode**: View classroom availability and submit booking requests.
    * **Admin Mode**: Secure login (password protected), batch course scheduling, auditing applications, and force-canceling bookings.
* **AI Assistant**: Integrated with the DeepSeek Large Language Model using RAG technology to answer natural language queries about laboratory facilities (e.g., "Which room has sandbox equipment?").
* **Automated Notifications**: Automatically sends email notifications to students via SMTP based on audit results (Approve/Reject).
* **Data Visualization**: Integrated Chart.js dynamic charts on the dashboard to display weekly laboratory usage statistics.

## Technology Stack

* **Backend Framework**: Python FastAPI (High-performance, Async)
* **Database**: SQLite + SQLModel (ORM)
* **Frontend**: HTML5 + Jinja2 Templates + Tailwind CSS (UI) + JavaScript
* **AI Service**: DeepSeek API (OpenAI-compatible)
* **External APIs**: Open-Meteo (Weather data), SMTP (Email service)

## Project Structure

```text
/
├── main.py            # Main application entry point (API routes & business logic)
├── database.py        # Database connection and configuration
├── models.py          # Database model definitions (Room, Booking schemas)
├── database.db        # SQLite database file (Auto-generated)
└── templates/         # Frontend template directory
    └── dashboard.html # Main frontend page
```


## Quick Start


### 1. Prerequisites

Ensure Python 3.10 or higher is installed locally.


### 2. Install Dependencies

It is recommended to create a virtual environment and install the required dependencies:


```
pip install fastapi uvicorn sqlmodel jinja2 openai requests pydantic
```


### 3. Configuration

- **Email Service**: Modify the `SMTP_CONFIG` dictionary in `main.py` to configure the sender email.
- **AI API**: Replace `DEEPSEEK_API_KEY` in `main.py` with a valid Token.


### 4. Run the Application

Execute the following command in the project root directory:


```
uvicorn main:app --reload
```

After startup, access: `http://127.0.0.1:8000`


### 5. Initial Accounts

- **Admin Entry**: Click "Admin Login" on the page.
- **Default Password**: `123456`


## Notes

- The system will automatically create `database.db` and initialize basic laboratory data upon the first run.
- To ensure frontend styles load correctly, the running environment requires an internet connection (dependency on Tailwind CSS CDN).


---

**Copyright 2026 SCNU IBC SAC | Smart Booking System Team**


