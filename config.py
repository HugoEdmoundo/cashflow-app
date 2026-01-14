import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Tambahkan di config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cashflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

class Config:
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "database.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
