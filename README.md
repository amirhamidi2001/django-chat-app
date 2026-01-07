# Django Chat Application

A real-time private chat application built with **Django** and **Django Channels**, featuring WebSocket-based messaging, user presence, typing indicators, read receipts, and file sharing. The project is deployed on **Render** with a live demo available.

**Live Demo:** [https://chatify-1uaw.onrender.com/](https://chatify-1uaw.onrender.com/)

---

## Features

* Real-time private messaging using **WebSockets**
* Online / offline user presence with last-seen tracking
* Typing indicators
* Read receipts
* Message pagination (load older messages)
* File and image sharing
* Secure message validation (anti-spoofing, input validation)
* Authentication-based access control
* Responsive UI built with **Tailwind CSS**

---

## Tech Stack

### Backend

* Python
* Django
* Django Channels (ASGI)
* PostgreSQL
* Redis (via Channels layer, if configured)

### Frontend

* JavaScript
* Tailwind CSS
* HTML (Django templates)

### Deployment

* Render (production hosting)
* ASGI application with Channels

---

## Project Structure

```text
.
├── build.sh
├── chat
│   ├── admin.py
│   ├── apps.py
│   ├── consumers.py
│   ├── migrations
│   ├── models.py
│   ├── routing.py
│   ├── templates
│   │   ├── chat
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   └── room.html
│   │   └── registration
│   │       └── login.html
│   ├── urls.py
│   └── views.py
├── core
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── media
├── static
│   └── js
│       └── room.js
├── manage.py
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Core Functionality Overview

### WebSocket Communication

* Implemented using `AsyncWebsocketConsumer`
* Secure room generation based on participating usernames
* Server-side validation for:

  * Authentication
  * Message ownership
  * Message length
  * UUID integrity

### Messaging System

* Messages stored in PostgreSQL
* Supports:

  * Text messages
  * File attachments
  * Soft deletion
  * Read/unread state
* Messages are paginated to improve performance

### User Presence

* Tracks online/offline status
* Updates `last_seen` timestamp
* Broadcasts status changes in real time

---

## Setup and Installation

### Prerequisites

* Python 3.10+
* PostgreSQL
* Virtual environment tool (recommended)

### Clone the Repository

```bash
git clone https://github.com/amirhamidi2001/django-chat-app.git
cd django-chat-app
```

### Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux / macOS
venv\Scripts\activate     # Windows
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file or configure environment variables:

```env
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgresql://user:password@localhost:5432/db_name
```

### Apply Migrations

```bash
python manage.py migrate
```

### Create Superuser

```bash
python manage.py createsuperuser
```

### Run Development Server

```bash
python manage.py runserver
```

Access the app at:
`http://127.0.0.1:8000/`

---

## Deployment Notes (Render)

* Uses an **ASGI** entry point (`core/asgi.py`)
* `build.sh` handles setup during deployment
* Static files and media configured for production
* PostgreSQL used as the primary database

---

## Security Considerations

* WebSocket connections require authentication
* Users cannot message themselves
* Message sender spoofing is prevented server-side
* UUID validation for all message references
* Message length limits enforced

---

## License

This project is licensed under the **MIT License**.
See the `LICENSE` file for details.

---

## Author

**Amir Hamidi**
Python & Django Developer

* GitHub: [https://github.com/amirhamidi2001](https://github.com/amirhamidi2001)
* Website: [https://amirhamidi.pythonanywhere.com/](https://amirhamidi.pythonanywhere.com/)
