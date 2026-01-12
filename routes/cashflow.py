from flask import Blueprint, render_template, request, redirect, url_for, send_file
from models import db, Cashflow
from datetime import datetime
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table

cashflow_bp = Blueprint("cashflow", __name__)

def recalc_saldo():
    records = Cashflow.query.order_by(Cashflow.date).all()
    cash, non_cash = 0, 0
    for r in records:
        if r.category == "cash":
            cash += r.amount if r.transaction == "income" else -r.amount
        else:
            non_cash += r.amount if r.transaction == "income" else -r.amount
        r.saldo_cash = cash
        r.saldo_non_cash = non_cash
    db.session.commit()

@cashflow_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        data = Cashflow(
            description=request.form["description"],
            category=request.form["category"],
            transaction=request.form["transaction"],
            amount=float(request.form["amount"])
        )
        db.session.add(data)
        db.session.commit()
        recalc_saldo()
        return redirect(url_for("cashflow.index"))

    month = request.args.get("month")
    query = Cashflow.query

    if month:
        query = query.filter(Cashflow.date.strftime("%Y-%m") == month)

    records = query.order_by(Cashflow.date.desc()).all()

    cash_total = records[-1].saldo_cash if records else 0
    non_cash_total = records[-1].saldo_non_cash if records else 0

    return render_template(
        "index.html",
        records=records,
        cash_total=cash_total,
        non_cash_total=non_cash_total
    )

@cashflow_bp.route("/delete/<int:id>")
def delete(id):
    db.session.delete(Cashflow.query.get(id))
    db.session.commit()
    recalc_saldo()
    return redirect(url_for("cashflow.index"))

@cashflow_bp.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    data = Cashflow.query.get(id)
    if request.method == "POST":
        data.description = request.form["description"]
        data.category = request.form["category"]
        data.transaction = request.form["transaction"]
        data.amount = float(request.form["amount"])
        db.session.commit()
        recalc_saldo()
        return redirect(url_for("cashflow.index"))
    return render_template("edit.html", data=data)

@cashflow_bp.route("/export/excel")
def export_excel():
    records = Cashflow.query.all()
    df = pd.DataFrame([{
        "Date": r.date.strftime("%Y-%m-%d"),
        "Desc": r.description,
        "Category": r.category,
        "Transaction": r.transaction,
        "Amount": r.amount,
        "Cash": r.saldo_cash,
        "Non Cash": r.saldo_non_cash
    } for r in records])

    file = "cashflow.xlsx"
    df.to_excel(file, index=False)
    return send_file(file, as_attachment=True)

@cashflow_bp.route("/export/pdf")
def export_pdf():
    file = "cashflow.pdf"
    records = Cashflow.query.all()

    data = [["Date", "Desc", "Category", "Transaction", "Amount", "Cash", "Non Cash"]]
    for r in records:
        data.append([
            r.date.strftime("%Y-%m-%d"),
            r.description,
            r.category,
            r.transaction,
            r.amount,
            r.saldo_cash,
            r.saldo_non_cash
        ])

    pdf = SimpleDocTemplate(file)
    pdf.build([Table(data)])
    return send_file(file, as_attachment=True)
