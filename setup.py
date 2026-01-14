# setup.py
import os
import sys
import subprocess

def setup_project():
    print("Setting up CashFlow Pro...")
    
    # Install Python dependencies
    print("\n1. Installing Python dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "flask-login", "pandas", "openpyxl", "werkzeug"])
    
    # Initialize database
    print("\n2. Initializing database...")
    from app import init_database
    init_database()
    
    print("\n3. Setup completed!")
    print("\nTo run the application:")
    print("  python app.py")
    print("\nDefault login:")
    print("  Username: admin")
    print("  Password: admin123")

if __name__ == "__main__":
    setup_project()