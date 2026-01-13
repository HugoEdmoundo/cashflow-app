from flask import Flask, render_template, request, redirect, flash, send_file, g
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
import sqlite3
import os
from contextlib import closing

app = Flask(__name__)
app.secret_key = 'cashflow-pro-secret-key-2024'
app.config['DATABASE'] = 'cashflow.db'

# ========== DATABASE FUNCTIONS ==========

def get_db():
    """Get database connection with proper connection management"""
    if 'db' not in g:
        db_path = os.path.join(os.path.dirname(__file__), app.config['DATABASE'])
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        # Set timeout to handle concurrent access
        g.db.execute('PRAGMA busy_timeout = 5000')
        g.db.execute('PRAGMA journal_mode = WAL')  # Write-Ahead Logging for better concurrency
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection at the end of request"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_database():
    """Initialize database tables"""
    with app.app_context():
        db = get_db()
        
        # Create transactions table
        db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create settings table for next_id
        db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Initialize next_id if not exists
        db.execute('''
            INSERT OR IGNORE INTO settings (key, value) 
            VALUES ('next_id', '1')
        ''')
        
        db.commit()

# ========== HELPER FUNCTIONS ==========

def get_current_datetime():
    """Get current datetime"""
    return datetime.now()

def format_datetime_for_display(dt_str):
    """Format datetime string for display"""
    try:
        if isinstance(dt_str, str):
            # Remove timezone info if present
            if 'T' in dt_str:
                dt_str = dt_str.split('T')[0] + ' ' + dt_str.split('T')[1].split('+')[0]
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        else:
            dt = dt_str
        
        # Format to Indonesian format
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception as e:
        print(f"Error formatting datetime: {e}")
        return dt_str

def format_datetime_short(dt_str):
    """Format datetime for short display"""
    try:
        if isinstance(dt_str, str):
            # Remove timezone info if present
            if 'T' in dt_str:
                dt_str = dt_str.split('T')[0]
            dt = datetime.strptime(dt_str, '%Y-%m-%d')
        else:
            dt = dt_str
        
        return dt.strftime('%d/%m/%Y')
    except:
        return dt_str

def get_next_id():
    """Get next transaction ID"""
    db = get_db()
    result = db.execute('SELECT value FROM settings WHERE key = ?', ('next_id',)).fetchone()
    if result:
        return int(result['value'])
    return 1

def update_next_id(new_id):
    """Update next transaction ID"""
    db = get_db()
    db.execute('UPDATE settings SET value = ? WHERE key = ?', (str(new_id), 'next_id'))
    db.commit()

def calculate_totals():
    """Calculate all financial totals from transactions"""
    db = get_db()
    
    # Get all transactions
    transactions = db.execute('SELECT * FROM transactions ORDER BY created_at DESC').fetchall()
    
    total_transactions = len(transactions)
    
    # Initialize counters
    cash_income = 0
    cash_expense = 0
    non_cash_income = 0
    non_cash_expense = 0
    
    # Calculate by category and type
    for transaction in transactions:
        amount = transaction['amount']
        category = transaction['category']
        transaction_type = transaction['transaction_type']
        
        if category == 'cash':
            if transaction_type == 'income':
                cash_income += amount
            else:  # expenditure
                cash_expense += amount
        else:  # non cash
            if transaction_type == 'income':
                non_cash_income += amount
            else:  # expenditure
                non_cash_expense += amount
    
    # Calculate balances
    cash_balance = cash_income - cash_expense
    non_cash_balance = non_cash_income - non_cash_expense
    
    # Totals
    total_income = cash_income + non_cash_income
    total_expense = cash_expense + non_cash_expense
    total_balance = cash_balance + non_cash_balance
    
    # Count transactions by category
    cash_count = len([t for t in transactions if t['category'] == 'cash'])
    non_cash_count = len([t for t in transactions if t['category'] == 'non cash'])
    
    return {
        'total_transactions': total_transactions,
        'cash_income': cash_income,
        'cash_expense': cash_expense,
        'cash_balance': cash_balance,
        'non_cash_income': non_cash_income,
        'non_cash_expense': non_cash_expense,
        'non_cash_balance': non_cash_balance,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_balance': total_balance,
        'cash_count': cash_count,
        'non_cash_count': non_cash_count
    }

@app.context_processor
def inject_globals():
    """Inject global variables to all templates"""
    totals = calculate_totals()
    
    # Get current time in Indonesia timezone
    now = datetime.now()
    
    return {
        'current_date': now.strftime('%A, %d %B %Y'),
        'current_time': now.strftime('%H:%M'),
        'total_count': totals['total_transactions'],
        'cash_balance': totals['cash_balance'],
        'non_cash_balance': totals['non_cash_balance'],
        'total_balance': totals['total_balance'],
        'cash_income': totals['cash_income'],
        'cash_expense': totals['cash_expense'],
        'non_cash_income': totals['non_cash_income'],
        'non_cash_expense': totals['non_cash_expense'],
        'total_income': totals['total_income'],
        'total_expense': totals['total_expense'],
        'cash_count': totals['cash_count'],
        'non_cash_count': totals['non_cash_count']
    }

# ========== ROUTES ==========

@app.route('/')
def dashboard():
    """Dashboard homepage"""
    db = get_db()
    
    # Get recent transactions (last 5)
    transactions = db.execute('''
        SELECT * FROM transactions 
        ORDER BY created_at DESC 
        LIMIT 5
    ''').fetchall()
    
    # Format dates for display
    formatted_transactions = []
    for t in transactions:
        t_dict = dict(t)
        t_dict['display_date'] = format_datetime_short(t['created_at'])
        formatted_transactions.append(t_dict)
    
    totals = calculate_totals()
    
    return render_template('dashboard.html',
                         recent_transactions=formatted_transactions,
                         **totals)

@app.route('/transactions')
def transactions_page():
    """Transactions management page"""
    db = get_db()
    
    # Get all transactions sorted by date
    transactions = db.execute('''
        SELECT * FROM transactions 
        ORDER BY created_at DESC
    ''').fetchall()
    
    # Format dates for display
    formatted_transactions = []
    for t in transactions:
        t_dict = dict(t)
        t_dict['display_date'] = format_datetime_for_display(t['created_at'])
        formatted_transactions.append(t_dict)
    
    totals = calculate_totals()
    
    return render_template('transactions.html', 
                         records=formatted_transactions,
                         **totals)

@app.route('/add', methods=['POST'])
def add_transaction():
    """Add new transaction"""
    try:
        # Get form data
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'cash')
        transaction_type = request.form.get('transaction', 'income')
        amount_str = request.form.get('amount', '0')
        
        # Validation
        if not description:
            flash('Deskripsi harus diisi', 'error')
            return redirect('/transactions')
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                flash('Jumlah harus lebih besar dari 0', 'error')
                return redirect('/transactions')
        except ValueError:
            flash('Jumlah harus berupa angka', 'error')
            return redirect('/transactions')
        
        # Get next ID
        next_id = get_next_id()
        
        db = get_db()
        # Insert transaction
        db.execute('''
            INSERT INTO transactions (id, description, category, transaction_type, amount)
            VALUES (?, ?, ?, ?, ?)
        ''', (next_id, description, category, transaction_type, amount))
        
        # Update next_id
        update_next_id(next_id + 1)
        db.commit()
        
        flash(f'Transaksi "{description}" berhasil ditambahkan', 'success')
        
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    
    return redirect('/transactions')

@app.route('/edit/<int:id>')
def edit_transaction(id):
    """Edit transaction page"""
    db = get_db()
    
    # Find transaction by ID
    transaction = db.execute('SELECT * FROM transactions WHERE id = ?', (id,)).fetchone()
    
    if transaction:
        transaction_dict = dict(transaction)
        transaction_dict['display_date'] = format_datetime_for_display(transaction['created_at'])
        # Rename transaction_type to transaction for template compatibility
        transaction_dict['transaction'] = transaction_dict['transaction_type']
        return render_template('edit.html', data=transaction_dict)
    
    flash('Transaksi tidak ditemukan', 'error')
    return redirect('/transactions')

@app.route('/update/<int:id>', methods=['POST'])
def update_transaction(id):
    """Update existing transaction"""
    try:
        # Get form data
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'cash')
        transaction_type = request.form.get('transaction', 'income')
        amount_str = request.form.get('amount', '0')
        
        # Validation
        if not description:
            flash('Deskripsi harus diisi', 'error')
            return redirect('/transactions')
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                flash('Jumlah harus lebih besar dari 0', 'error')
                return redirect('/transactions')
        except ValueError:
            flash('Jumlah harus berupa angka', 'error')
            return redirect('/transactions')
        
        db = get_db()
        # Update transaction
        result = db.execute('''
            UPDATE transactions 
            SET description = ?, category = ?, transaction_type = ?, amount = ?
            WHERE id = ?
        ''', (description, category, transaction_type, amount, id))
        
        db.commit()
        
        if result.rowcount > 0:
            flash(f'Transaksi "{description}" berhasil diperbarui', 'success')
        else:
            flash('Transaksi tidak ditemukan', 'error')
        
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    
    return redirect('/transactions')

@app.route('/delete/<int:id>')
def delete_transaction(id):
    """Delete transaction"""
    db = get_db()
    
    # Get transaction description before deleting
    transaction = db.execute('SELECT description FROM transactions WHERE id = ?', (id,)).fetchone()
    
    if transaction:
        # Delete transaction
        db.execute('DELETE FROM transactions WHERE id = ?', (id,))
        db.commit()
        
        flash(f'Transaksi "{transaction["description"]}" berhasil dihapus', 'success')
    else:
        flash('Transaksi tidak ditemukan', 'error')
    
    return redirect('/transactions')

@app.route('/clear-all')
def clear_all():
    """Clear all transactions"""
    db = get_db()
    
    # Delete all transactions
    db.execute('DELETE FROM transactions')
    # Reset next_id to 1
    db.execute('UPDATE settings SET value = ? WHERE key = ?', ('1', 'next_id'))
    db.commit()
    
    flash('Semua transaksi berhasil dihapus', 'success')
    return redirect('/')

@app.route('/reports')
def reports():
    """Reports page"""
    totals = calculate_totals()
    return render_template('reports.html', **totals)

@app.route('/export/excel')
def export_excel():
    """Export transactions to Excel"""
    db = get_db()
    
    transactions = db.execute('SELECT * FROM transactions ORDER BY created_at DESC').fetchall()
    
    if not transactions:
        flash('Tidak ada data untuk diexport', 'error')
        return redirect('/reports')
    
    try:
        # Prepare data for DataFrame
        data = []
        for t in transactions:
            display_date = format_datetime_for_display(t['created_at'])
            
            data.append({
                'ID': t['id'],
                'Tanggal': display_date,
                'Deskripsi': t['description'],
                'Kategori': 'Cash' if t['category'] == 'cash' else 'Non-Cash',
                'Jenis': 'Pemasukan' if t['transaction_type'] == 'income' else 'Pengeluaran',
                'Jumlah (Rp)': t['amount'],
                'Status': 'Pemasukan' if t['transaction_type'] == 'income' else 'Pengeluaran'
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Transaksi', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Transaksi']
            
            # Add header format
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#F3F4F6',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            
            # Money format
            money_format = workbook.add_format({'num_format': '#,##0'})
            
            # Apply header format to all columns
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Apply money format to amount column
            amount_col = df.columns.get_loc('Jumlah (Rp)')
            worksheet.set_column(amount_col, amount_col, None, money_format)
            
            # Auto-adjust column widths
            for i, col in enumerate(df.columns):
                column_width = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, column_width)
            
            # Add summary sheet
            totals = calculate_totals()
            summary_data = {
                'Metric': [
                    'Total Transaksi',
                    'Saldo Cash',
                    'Saldo Non-Cash', 
                    'Total Saldo',
                    'Total Pemasukan',
                    'Total Pengeluaran',
                    'Jumlah Transaksi Cash',
                    'Jumlah Transaksi Non-Cash'
                ],
                'Value': [
                    totals['total_transactions'],
                    totals['cash_balance'],
                    totals['non_cash_balance'],
                    totals['total_balance'],
                    totals['total_income'],
                    totals['total_expense'],
                    totals['cash_count'],
                    totals['non_cash_count']
                ]
            }
            
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Ringkasan', index=False)
            
            # Format summary sheet
            worksheet_summary = writer.sheets['Ringkasan']
            for col_num, value in enumerate(df_summary.columns.values):
                worksheet_summary.write(0, col_num, value, header_format)
            
            # Format numbers in summary
            money_col_summary = df_summary.columns.get_loc('Value')
            worksheet_summary.set_column(money_col_summary, money_col_summary, None, money_format)
            
            for i, col in enumerate(df_summary.columns):
                column_width = max(df_summary[col].astype(str).map(len).max(), len(col)) + 2
                worksheet_summary.set_column(i, i, column_width)
        
        output.seek(0)
        
        # Generate filename with timestamp
        filename = f'laporan_transaksi_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        flash('Export Excel berhasil', 'success')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error saat export: {str(e)}', 'error')
        return redirect('/reports')

@app.route('/export/csv')
def export_csv():
    """Export transactions to CSV"""
    db = get_db()
    
    transactions = db.execute('SELECT * FROM transactions ORDER BY created_at DESC').fetchall()
    
    if not transactions:
        flash('Tidak ada data untuk diexport', 'error')
        return redirect('/reports')
    
    try:
        # Prepare data
        data = []
        for t in transactions:
            display_date = format_datetime_for_display(t['created_at'])
            
            data.append({
                'ID': t['id'],
                'Tanggal': display_date,
                'Deskripsi': t['description'],
                'Kategori': 'Cash' if t['category'] == 'cash' else 'Non-Cash',
                'Jenis': 'Pemasukan' if t['transaction_type'] == 'income' else 'Pengeluaran',
                'Jumlah': t['amount']
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create CSV in memory
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        
        # Generate filename
        filename = f'laporan_transaksi_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        flash('Export CSV berhasil', 'success')
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error saat export: {str(e)}', 'error')
        return redirect('/reports')

@app.route('/sample-data')
def sample_data():
    """Add sample data for testing"""
    try:
        db = get_db()
        
        # Check if we already have sample data
        existing = db.execute('SELECT COUNT(*) as count FROM transactions').fetchone()
        
        if existing['count'] == 0:
            # Get current datetime
            now = get_current_datetime()
            
            # Sample transactions
            sample_transactions = [
                (1, 'Gaji Bulanan', 'cash', 'income', 5000000, now - timedelta(days=30)),
                (2, 'Bayar Listrik', 'non cash', 'expenditure', 750000, now - timedelta(days=25)),
                (3, 'Freelance Project', 'non cash', 'income', 3000000, now - timedelta(days=20)),
                (4, 'Belanja Bulanan', 'cash', 'expenditure', 1200000, now - timedelta(days=15)),
                (5, 'Investasi Saham', 'non cash', 'income', 2000000, now - timedelta(days=10))
            ]
            
            # Insert sample data
            db.executemany('''
                INSERT INTO transactions (id, description, category, transaction_type, amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', sample_transactions)
            
            # Update next_id
            db.execute('UPDATE settings SET value = ? WHERE key = ?', ('6', 'next_id'))
            db.commit()
            
            flash('Sample data berhasil ditambahkan', 'success')
        else:
            flash('Data sudah ada, sample data tidak ditambahkan', 'info')
    
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect('/')

@app.route('/backup')
def backup_database():
    """Create a backup of the database"""
    try:
        db_path = os.path.join(os.path.dirname(__file__), app.config['DATABASE'])
        backup_path = f'cashflow_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        
        import shutil
        shutil.copy2(db_path, backup_path)
        
        flash(f'Backup berhasil dibuat: {backup_path}', 'success')
    except Exception as e:
        flash(f'Error saat backup: {str(e)}', 'error')
    
    return redirect('/')

@app.errorhandler(404)
def page_not_found(e):
    """404 Error handler"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """500 Error handler"""
    flash('Terjadi kesalahan pada server', 'error')
    return redirect('/')

# ========== INITIALIZATION ==========

if __name__ == '__main__':
    # Initialize database
    with app.app_context():
        init_database()
    
    print(f"CashFlow Pro starting on http://localhost:5050")
    print(f"Database file: {app.config['DATABASE']}")
    print(f"Press Ctrl+C to stop")
    
    # Run the app
    app.run(debug=True, port=5050, host='0.0.0.0')