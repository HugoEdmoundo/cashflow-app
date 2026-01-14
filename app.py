from datetime import datetime, timedelta
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
import io
import os

app = Flask(__name__)
app.secret_key = 'cashflow-pro-secret-key-2024-very-secure'

# Setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize database
def init_db():
    conn = sqlite3.connect('cashflow.db')
    c = conn.cursor()
    
    # Drop tables if exist for fresh start
    c.execute('DROP TABLE IF EXISTS transactions')
    c.execute('DROP TABLE IF EXISTS users')
    
    # Create users table
    c.execute('''CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        password TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Create transactions table
    c.execute('''CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Create admin user
    hashed_password = generate_password_hash('admin123')
    c.execute("INSERT INTO users (username, email, full_name, password) VALUES (?, ?, ?, ?)",
              ('admin', 'admin@cashflow.local', 'Administrator', hashed_password))
    
    # Add sample transactions for admin
    sample_transactions = [
        (1, 'Gaji Bulan Januari', 'cash', 'income', 10000000),
        (1, 'Bayar Listrik', 'cash', 'expenditure', 500000),
        (1, 'Transfer ke Tabungan', 'non_cash', 'expenditure', 2000000),
        (1, 'Bonus Project', 'non_cash', 'income', 3000000),
        (1, 'Belanja Bulanan', 'cash', 'expenditure', 1500000),
    ]
    
    c.executemany("INSERT INTO transactions (user_id, description, category, transaction_type, amount) VALUES (?, ?, ?, ?, ?)",
                  sample_transactions)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# Initialize database
init_db()

# User model
class User(UserMixin):
    def __init__(self, id, username, email, full_name):
        self.id = id
        self.username = username
        self.email = email
        self.full_name = full_name

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('cashflow.db')
    c = conn.cursor()
    c.execute('SELECT id, username, email, full_name FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return User(user[0], user[1], user[2], user[3])
    return None

# Helper functions
def format_rupiah(amount):
    try:
        amount = float(amount)
        return f"Rp {amount:,.0f}".replace(",", ".")
    except:
        return "Rp 0"

def get_db_connection():
    conn = sqlite3.connect('cashflow.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_totals(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get counts
    c.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,))
    total_transactions = c.fetchone()[0]
    
    # Calculate balances
    # Cash
    c.execute('''SELECT 
                 COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as income,
                 COALESCE(SUM(CASE WHEN transaction_type = 'expenditure' THEN amount ELSE 0 END), 0) as expense
                 FROM transactions WHERE user_id = ? AND category = 'cash' ''', (user_id,))
    cash = c.fetchone()
    cash_income = cash['income']
    cash_expense = cash['expense']
    cash_balance = cash_income - cash_expense
    
    # Non-cash
    c.execute('''SELECT 
                 COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as income,
                 COALESCE(SUM(CASE WHEN transaction_type = 'expenditure' THEN amount ELSE 0 END), 0) as expense
                 FROM transactions WHERE user_id = ? AND category = 'non_cash' ''', (user_id,))
    non_cash = c.fetchone()
    non_cash_income = non_cash['income']
    non_cash_expense = non_cash['expense']
    non_cash_balance = non_cash_income - non_cash_expense
    
    # Counts
    c.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND category = 'cash'", (user_id,))
    cash_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND category = 'non_cash'", (user_id,))
    non_cash_count = c.fetchone()[0]
    
    conn.close()
    
    return {
        'total_transactions': total_transactions,
        'cash_count': cash_count,
        'non_cash_count': non_cash_count,
        'cash_income': cash_income,
        'cash_expense': cash_expense,
        'cash_balance': cash_balance,
        'non_cash_income': non_cash_income,
        'non_cash_expense': non_cash_expense,
        'non_cash_balance': non_cash_balance,
        'total_income': cash_income + non_cash_income,
        'total_expense': cash_expense + non_cash_expense,
        'total_balance': (cash_income + non_cash_income) - (cash_expense + non_cash_expense)
    }

def get_chart_data(user_id, days=30):
    dates = []
    income_data = []
    expense_data = []
    balances = []
    
    # Generate dummy data for 30 days
    for i in range(days, 0, -1):
        date = datetime.now() - timedelta(days=i)
        dates.append(date.strftime('%d/%m'))
        
        # Generate random data
        import random
        income = random.randint(500000, 3000000) if random.random() > 0.7 else 0
        expense = random.randint(200000, 1500000) if random.random() > 0.6 else 0
        
        income_data.append(income)
        expense_data.append(expense)
        
        # Calculate running balance
        if i == days:
            balances.append(income - expense)
        else:
            balances.append(balances[-1] + income - expense)
    
    # Category data
    category_labels = ['Cash Income', 'Cash Expense', 'Non-Cash Income', 'Non-Cash Expense']
    category_values = [5000000, 2000000, 3000000, 1000000]
    category_colors = ['#10B981', '#EF4444', '#3B82F6', '#8B5CF6']
    
    return {
        'dates': dates,
        'income_data': income_data,
        'expense_data': expense_data,
        'balances': balances,
        'category_labels': category_labels,
        'category_values': category_values,
        'category_colors': category_colors
    }

def get_monthly_summary(user_id):
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
    summary = []
    
    for i, month in enumerate(months[:6]):  # Last 6 months
        income = (i + 1) * 1000000 + 500000
        expense = (i + 1) * 500000 + 250000
        balance = income - expense
        
        summary.append({
            'month': month,
            'income': income,
            'expense': expense,
            'balance': balance
        })
    
    return summary

def get_recent_transactions(user_id, limit=5):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''SELECT * FROM transactions 
                 WHERE user_id = ? 
                 ORDER BY transaction_date DESC 
                 LIMIT ?''', (user_id, limit))
    
    transactions = []
    for row in c.fetchall():
        transactions.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'display_date': row['transaction_date'][:16].replace('-', '/')
        })
    
    conn.close()
    return transactions

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'], user['full_name'])
            login_user(user_obj)
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Password tidak cocok!', 'danger')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute('''INSERT INTO users (username, email, full_name, password) 
                         VALUES (?, ?, ?, ?)''',
                      (username, email, full_name, hashed_password))
            conn.commit()
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Username sudah digunakan!', 'danger')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        totals = get_user_totals(current_user.id)
        chart_data = get_chart_data(current_user.id)
        monthly_summary = get_monthly_summary(current_user.id)
        recent_transactions = get_recent_transactions(current_user.id)
        
        return render_template('dashboard.html',
                             totals=totals,
                             chart_data=chart_data,
                             monthly_summary=monthly_summary,
                             recent_transactions=recent_transactions,
                             current_year=datetime.now().year,
                             current_date=datetime.now().strftime('%d %B %Y'),
                             current_time=datetime.now().strftime('%H:%M'),
                             user_totals=totals,
                             format_rupiah=format_rupiah,
                             zip=zip)
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        return render_template('dashboard.html', 
                             totals={'total_transactions': 0, 'total_balance': 0},
                             chart_data={'dates': [], 'category_labels': []},
                             monthly_summary=[],
                             recent_transactions=[],
                             current_date=datetime.now().strftime('%d %B %Y'),
                             current_time=datetime.now().strftime('%H:%M'))

@app.route('/transactions')
@login_required
def transactions():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get filter parameters
    category = request.args.get('category', 'all')
    trans_type = request.args.get('type', 'all')
    search = request.args.get('search', '')
    
    # Build query
    query = "SELECT * FROM transactions WHERE user_id = ?"
    params = [current_user.id]
    
    if category != 'all':
        query += " AND category = ?"
        params.append(category)
    
    if trans_type != 'all':
        query += " AND transaction_type = ?"
        params.append(trans_type)
    
    if search:
        query += " AND description LIKE ?"
        params.append(f'%{search}%')
    
    query += " ORDER BY transaction_date DESC"
    
    c.execute(query, params)
    records = []
    for row in c.fetchall():
        records.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'display_date': row['transaction_date'][:16].replace('-', '/')
        })
    
    totals = get_user_totals(current_user.id)
    
    conn.close()
    
    return render_template('transactions.html',
                         records=records,
                         totals=totals,
                         filters={'category': category, 'type': trans_type, 'search': search},
                         format_rupiah=format_rupiah)

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    description = request.form.get('description')
    category = request.form.get('category')
    transaction_type = request.form.get('transaction')
    amount = float(request.form.get('amount', 0))
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''INSERT INTO transactions (user_id, description, category, transaction_type, amount) 
                 VALUES (?, ?, ?, ?, ?)''',
              (current_user.id, description, category, transaction_type, amount))
    
    conn.commit()
    conn.close()
    
    flash('Transaksi berhasil ditambahkan!', 'success')
    return redirect(url_for('transactions'))

@app.route('/edit_transaction/<int:id>')
@login_required
def edit_transaction(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', (id, current_user.id))
    transaction = c.fetchone()
    
    if not transaction:
        flash('Transaksi tidak ditemukan!', 'danger')
        return redirect(url_for('transactions'))
    
    transaction_dict = {
        'id': transaction['id'],
        'description': transaction['description'],
        'category': transaction['category'],
        'transaction_type': transaction['transaction_type'],
        'amount': transaction['amount']
    }
    
    conn.close()
    
    return render_template('edit.html', data=transaction_dict, format_rupiah=format_rupiah)

@app.route('/update_transaction/<int:id>', methods=['POST'])
@login_required
def update_transaction(id):
    description = request.form.get('description')
    category = request.form.get('category')
    transaction_type = request.form.get('transaction')
    amount = float(request.form.get('amount', 0))
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''UPDATE transactions 
                 SET description = ?, category = ?, transaction_type = ?, amount = ?
                 WHERE id = ? AND user_id = ?''',
              (description, category, transaction_type, amount, id, current_user.id))
    
    conn.commit()
    conn.close()
    
    flash('Transaksi berhasil diperbarui!', 'success')
    return redirect(url_for('transactions'))

@app.route('/delete_transaction/<int:id>')
@login_required
def delete_transaction(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('DELETE FROM transactions WHERE id = ? AND user_id = ?', (id, current_user.id))
    
    conn.commit()
    conn.close()
    
    flash('Transaksi berhasil dihapus!', 'success')
    return redirect(url_for('transactions'))

@app.route('/clear_all_transactions')
@login_required
def clear_all_transactions():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('DELETE FROM transactions WHERE user_id = ?', (current_user.id,))
    
    conn.commit()
    conn.close()
    
    flash('Semua transaksi berhasil dihapus!', 'success')
    return redirect(url_for('transactions'))

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC', (current_user.id,))
    transactions_list = []
    for row in c.fetchall():
        transactions_list.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'transaction_date': row['transaction_date']
        })
    
    totals = get_user_totals(current_user.id)
    
    # Calculate stats
    if totals['total_transactions'] > 0:
        stats = {
            'cash_ratio': (totals['cash_count'] / totals['total_transactions']) * 100,
            'non_cash_ratio': (totals['non_cash_count'] / totals['total_transactions']) * 100,
            'income_ratio': (totals['total_income'] / (totals['total_income'] + totals['total_expense'])) * 100 if (totals['total_income'] + totals['total_expense']) > 0 else 0,
            'expense_ratio': (totals['total_expense'] / (totals['total_income'] + totals['total_expense'])) * 100 if (totals['total_income'] + totals['total_expense']) > 0 else 0
        }
    else:
        stats = {'cash_ratio': 0, 'non_cash_ratio': 0, 'income_ratio': 0, 'expense_ratio': 0}
    
    conn.close()
    
    return render_template('report.html',
                         transactions=transactions_list,
                         totals=totals,
                         stats=stats,
                         format_rupiah=format_rupiah)

@app.route('/export_excel')
@login_required
def export_excel():
    conn = get_db_connection()
    
    df = pd.read_sql_query('''SELECT 
                             transaction_date as Tanggal,
                             description as Deskripsi,
                             category as Kategori,
                             transaction_type as Jenis,
                             amount as Jumlah
                             FROM transactions 
                             WHERE user_id = ?
                             ORDER BY transaction_date DESC''', 
                          conn, params=(current_user.id,))
    
    conn.close()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Transaksi', index=False)
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename=report_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    return response

@app.route('/export_csv')
@login_required
def export_csv():
    conn = get_db_connection()
    
    df = pd.read_sql_query('''SELECT * FROM transactions WHERE user_id = ?''', 
                          conn, params=(current_user.id,))
    
    conn.close()
    
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=report_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@app.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE id = ?', (current_user.id,))
    user = c.fetchone()
    
    user_data = {
        'username': user['username'],
        'email': user['email'],
        'full_name': user['full_name'],
        'created_at': user['created_at'][:10]
    }
    
    totals = get_user_totals(current_user.id)
    
    conn.close()
    
    return render_template('profile.html',
                         user_data=user_data,
                         user_totals=totals,
                         format_rupiah=format_rupiah)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)