from datetime import datetime, timedelta
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import pandas as pd
import io
import os
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.secret_key = 'cashflow-pro-secret-key-2024-very-secure'

# Setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Timezone Indonesia
TZ = ZoneInfo("Asia/Jakarta")

# Initialize database
def init_db():
    conn = sqlite3.connect('cashflow.db')
    c = conn.cursor()
    
    # Create users table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        password TEXT NOT NULL,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Create transactions table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Check if admin user exists
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed_password = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, email, full_name, password) VALUES (?, ?, ?, ?)",
                  ('admin', 'admin@cashflow.local', 'Administrator', hashed_password))
    
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
    cash_income = cash['income'] or 0
    cash_expense = cash['expense'] or 0
    cash_balance = cash_income - cash_expense
    
    # Non-cash
    c.execute('''SELECT 
                 COALESCE(SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END), 0) as income,
                 COALESCE(SUM(CASE WHEN transaction_type = 'expenditure' THEN amount ELSE 0 END), 0) as expense
                 FROM transactions WHERE user_id = ? AND category = 'non_cash' ''', (user_id,))
    non_cash = c.fetchone()
    non_cash_income = non_cash['income'] or 0
    non_cash_expense = non_cash['expense'] or 0
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
    conn = get_db_connection()
    c = conn.cursor()
    
    dates = []
    income_data = []
    expense_data = []
    balances = []
    
    # Get data from database for last 30 days
    end_date = datetime.now(TZ)
    start_date = end_date - timedelta(days=days)
    
    for i in range(days):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Get income for the day
        c.execute('''SELECT COALESCE(SUM(amount), 0) as total
                     FROM transactions 
                     WHERE user_id = ? 
                     AND transaction_type = 'income'
                     AND DATE(transaction_date) = ?
                     AND transaction_date >= ?''', 
                  (user_id, date_str, start_date))
        income = c.fetchone()['total']
        
        # Get expense for the day
        c.execute('''SELECT COALESCE(SUM(amount), 0) as total
                     FROM transactions 
                     WHERE user_id = ? 
                     AND transaction_type = 'expenditure'
                     AND DATE(transaction_date) = ?
                     AND transaction_date >= ?''', 
                  (user_id, date_str, start_date))
        expense = c.fetchone()['total']
        
        dates.append(current_date.strftime('%d/%m'))
        income_data.append(income)
        expense_data.append(expense)
        
        # Calculate running balance
        if i == 0:
            balances.append(income - expense)
        else:
            balances.append(balances[-1] + income - expense)
    
    # Category data from database
    c.execute('''SELECT category, transaction_type, COALESCE(SUM(amount), 0) as total
                 FROM transactions 
                 WHERE user_id = ? 
                 AND transaction_date >= ?
                 GROUP BY category, transaction_type''',
              (user_id, start_date))
    
    category_labels = ['Cash Income', 'Cash Expense', 'Non-Cash Income', 'Non-Cash Expense']
    category_values = [0, 0, 0, 0]
    category_colors = ['#10B981', '#EF4444', '#3B82F6', '#8B5CF6']
    
    for row in c.fetchall():
        if row['category'] == 'cash' and row['transaction_type'] == 'income':
            category_values[0] = row['total']
        elif row['category'] == 'cash' and row['transaction_type'] == 'expenditure':
            category_values[1] = row['total']
        elif row['category'] == 'non_cash' and row['transaction_type'] == 'income':
            category_values[2] = row['total']
        elif row['category'] == 'non_cash' and row['transaction_type'] == 'expenditure':
            category_values[3] = row['total']
    
    conn.close()
    
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
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get last 6 months data
    end_date = datetime.now(TZ)
    months_data = []
    
    for i in range(5, -1, -1):
        month_start = (end_date.replace(day=1) - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Get income for the month
        c.execute('''SELECT COALESCE(SUM(amount), 0) as income
                     FROM transactions 
                     WHERE user_id = ? 
                     AND transaction_type = 'income'
                     AND transaction_date BETWEEN ? AND ?''',
                  (user_id, month_start, month_end))
        income = c.fetchone()['income']
        
        # Get expense for the month
        c.execute('''SELECT COALESCE(SUM(amount), 0) as expense
                     FROM transactions 
                     WHERE user_id = ? 
                     AND transaction_type = 'expenditure'
                     AND transaction_date BETWEEN ? AND ?''',
                  (user_id, month_start, month_end))
        expense = c.fetchone()['expense']
        
        months_data.append({
            'month': month_start.strftime('%b'),
            'full_month': month_start.strftime('%B'),
            'income': income,
            'expense': expense,
            'balance': income - expense
        })
    
    conn.close()
    return months_data

def get_recent_transactions(user_id, limit=5):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''SELECT * FROM transactions 
                 WHERE user_id = ? 
                 ORDER BY transaction_date DESC 
                 LIMIT ?''', (user_id, limit))
    
    transactions = []
    for row in c.fetchall():
        # Convert UTC to Jakarta time
        trans_date = datetime.fromisoformat(row['transaction_date'].replace('Z', '+00:00'))
        jakarta_time = trans_date.astimezone(TZ)
        
        transactions.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'display_date': jakarta_time.strftime('%d/%m/%Y %H:%M')
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
        except Exception as e:
            print(f"Registration error: {e}")
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
        
        # Get current Jakarta time
        current_datetime = datetime.now(TZ)
        
        return render_template('dashboard.html',
                             totals=totals,
                             chart_data=chart_data,
                             monthly_summary=monthly_summary,
                             recent_transactions=recent_transactions,
                             current_year=current_datetime.year,
                             current_date=current_datetime.strftime('%d %B %Y'),
                             current_time=current_datetime.strftime('%H:%M'),
                             user_totals=totals,
                             format_rupiah=format_rupiah,
                             zip=zip)
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash('Error loading dashboard', 'danger')
        
        current_datetime = datetime.now(TZ)
        return render_template('dashboard.html', 
                             totals={'total_transactions': 0, 'total_balance': 0},
                             chart_data={'dates': [], 'category_labels': []},
                             monthly_summary=[],
                             recent_transactions=[],
                             current_date=current_datetime.strftime('%d %B %Y'),
                             current_time=current_datetime.strftime('%H:%M'))

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
        # Convert UTC to Jakarta time
        trans_date = datetime.fromisoformat(row['transaction_date'].replace('Z', '+00:00'))
        jakarta_time = trans_date.astimezone(TZ)
        
        records.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'display_date': jakarta_time.strftime('%d/%m/%Y %H:%M')
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

@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'GET':
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
            'amount': transaction['amount'],
            'transaction_date': transaction['transaction_date']
        }
        
        conn.close()
        
        return render_template('edit.html', data=transaction_dict, format_rupiah=format_rupiah)
    
    else:  # POST request for update
        description = request.form.get('description')
        category = request.form.get('category')
        transaction_type = request.form.get('transaction')
        amount = float(request.form.get('amount', 0))
        
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
        # Convert UTC to Jakarta time
        trans_date = datetime.fromisoformat(row['transaction_date'].replace('Z', '+00:00'))
        jakarta_time = trans_date.astimezone(TZ)
        
        transactions_list.append({
            'id': row['id'],
            'description': row['description'],
            'category': row['category'],
            'transaction_type': row['transaction_type'],
            'amount': row['amount'],
            'transaction_date': jakarta_time
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
    
    current_datetime = datetime.now(TZ)
    
    return render_template('reports.html',
                         transactions=transactions_list,
                         totals=totals,
                         stats=stats,
                         current_date=current_datetime.strftime('%d %B %Y'),
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
    response.headers['Content-Disposition'] = f'attachment; filename=report_{datetime.now(TZ).strftime("%Y%m%d")}.xlsx'
    
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
    response.headers['Content-Disposition'] = f'attachment; filename=report_{datetime.now(TZ).strftime("%Y%m%d")}.csv'
    
    return response

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'POST':
        # Update user data
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        # First, get current user data
        c.execute('SELECT password FROM users WHERE id = ?', (current_user.id,))
        user_data = c.fetchone()
        
        if new_password:
            # Verify current password
            if not check_password_hash(user_data['password'], current_password):
                flash('Password saat ini salah!', 'danger')
                return redirect(url_for('profile'))
            
            # Update with new password
            hashed_password = generate_password_hash(new_password)
            c.execute('''UPDATE users 
                         SET full_name = ?, email = ?, password = ?
                         WHERE id = ?''',
                      (full_name, email, hashed_password, current_user.id))
            flash('Profil dan password berhasil diperbarui!', 'success')
        else:
            # Update without password change
            c.execute('''UPDATE users 
                         SET full_name = ?, email = ?
                         WHERE id = ?''',
                      (full_name, email, current_user.id))
            flash('Profil berhasil diperbarui!', 'success')
        
        conn.commit()
    
    # Get user data for display
    c.execute('SELECT * FROM users WHERE id = ?', (current_user.id,))
    user = c.fetchone()
    
    # Convert UTC to Jakarta time for created_at
    created_date = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00'))
    jakarta_time = created_date.astimezone(TZ)
    
    user_data = {
        'username': user['username'],
        'email': user['email'],
        'full_name': user['full_name'],
        'created_at': jakarta_time.strftime('%d %B %Y')
    }
    
    totals = get_user_totals(current_user.id)
    
    conn.close()
    
    current_datetime = datetime.now(TZ)
    
    return render_template('profile.html',
                         user_data=user_data,
                         user_totals=totals,
                         current_date=current_datetime.strftime('%d %B %Y'),
                         format_rupiah=format_rupiah)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)