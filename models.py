from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Cashflow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(20))      # cash / non cash
    transaction = db.Column(db.String(20))   # income / expenditure
    amount = db.Column(db.Float, nullable=False)
    saldo_cash = db.Column(db.Float, default=0)
    saldo_non_cash = db.Column(db.Float, default=0)
