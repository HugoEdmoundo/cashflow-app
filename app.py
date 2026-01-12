import os
import sys
from flask import Flask, render_template, request, redirect, flash, session, send_file
from datetime import datetime, timezone, timedelta
from io import BytesIO
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cashflow-pro-vercel-' + str(os.urandom(26).hex()))
app.config['SESSION_TYPE'] = 'filesystem'


# Workaround untuk Vercel Python 3.9 compatibility
try:
    import numpy as np
    print(f"NumPy version: {np.__version__}")
except ImportError as e:
    print(f"NumPy import error: {e}")
    pass

# ========== HELPER FUNCTIONS ==========

def get_current_datetime():
    """Get current datetime in UTC timezone"""
    return datetime.now(timezone.utc)

def parse_datetime(dt_string):
    """Parse datetime string to timezone-aware datetime"""
    if isinstance(dt_string, datetime):
        if dt_string.tzinfo is None:
            return dt_string.replace(tzinfo=timezone.utc)
        return dt_string
    
    try:
        # Try parsing ISO format
        dt = datetime.fromisoformat(dt_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        # If parsing fails, return current datetime
        return get_current_datetime()

def format_datetime_for_display(dt):
    """Format datetime for display"""
    if isinstance(dt, str):
        dt = parse_datetime(dt)
    
    # Convert to local timezone (UTC+7 for Indonesia)
    local_tz = timezone(timedelta(hours=7))
    local_dt = dt.astimezone(local_tz)
    
    return local_dt.strftime('%d/%m/%Y %H:%M')

def format_datetime_short(dt):
    """Format datetime for short display"""
    if isinstance(dt, str):
        dt = parse_datetime(dt)
    
    local_tz = timezone(timedelta(hours=7))
    local_dt = dt.astimezone(local_tz)
    
    return local_dt.strftime('%d/%m/%Y')

def init_session():
    """Initialize session data if not exists"""
    if 'transactions' not in session:
        session['transactions'] = []
    if 'next_id' not in session:
        session['next_id'] = 1

def calculate_totals():
    """Calculate all financial totals from transactions"""
    init_session()
    transactions = session.get('transactions', [])
    
    total_transactions = len(transactions)
    
    # Initialize counters
    cash_income = 0
    cash_expense = 0
    non_cash_income = 0
    non_cash_expense = 0
    
    # Calculate by category and type
    for transaction in transactions:
        amount = float(transaction['amount'])
        
        if transaction['category'] == 'cash':
            if transaction['transaction'] == 'income':
                cash_income += amount
            else:  # expenditure
                cash_expense += amount
        else:  # non cash
            if transaction['transaction'] == 'income':
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
    utc_now = datetime.now(timezone.utc)
    indonesia_tz = timezone(timedelta(hours=7))
    indonesia_now = utc_now.astimezone(indonesia_tz)
    
    return {
        'current_date': indonesia_now.strftime('%A, %d %B %Y'),
        'current_time': indonesia_now.strftime('%H:%M'),
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
    init_session()
    transactions = session.get('transactions', [])
    
    # Get recent transactions (last 5)
    if transactions:
        # Sort by date descending
        sorted_transactions = sorted(
            transactions,
            key=lambda x: parse_datetime(x['date']),
            reverse=True
        )[:5]
        
        # Format dates for display
        for t in sorted_transactions:
            t['display_date'] = format_datetime_short(t['date'])
    else:
        sorted_transactions = []
    
    totals = calculate_totals()
    
    return render_template('dashboard.html',
                         recent_transactions=sorted_transactions,
                         **totals)

@app.route('/transactions')
def transactions_page():
    """Transactions management page"""
    init_session()
    transactions = session.get('transactions', [])
    
    # Sort by date descending
    sorted_transactions = sorted(
        transactions,
        key=lambda x: parse_datetime(x['date']),
        reverse=True
    )
    
    # Format dates for display
    for t in sorted_transactions:
        t['display_date'] = format_datetime_for_display(t['date'])
    
    totals = calculate_totals()
    
    return render_template('transactions.html', 
                         records=sorted_transactions,
                         **totals)

@app.route('/add', methods=['POST'])
def add_transaction():
    """Add new transaction"""
    init_session()
    
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
        
        # Create transaction object with timezone-aware datetime
        transaction = {
            'id': session['next_id'],
            'description': description,
            'category': category,
            'transaction': transaction_type,
            'amount': amount,
            'date': get_current_datetime().isoformat()
        }
        
        # Add to session
        transactions = session.get('transactions', [])
        transactions.append(transaction)
        session['transactions'] = transactions
        session['next_id'] = session['next_id'] + 1
        
        flash(f'Transaksi "{description}" berhasil ditambahkan', 'success')
        
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    
    return redirect('/transactions')

@app.route('/edit/<int:id>')
def edit_transaction(id):
    """Edit transaction page"""
    init_session()
    transactions = session.get('transactions', [])
    
    # Find transaction by ID
    transaction = next((t for t in transactions if t['id'] == id), None)
    
    if transaction:
        # Format date for display
        transaction['display_date'] = format_datetime_for_display(transaction['date'])
        return render_template('edit.html', data=transaction)
    
    flash('Transaksi tidak ditemukan', 'error')
    return redirect('/transactions')

@app.route('/update/<int:id>', methods=['POST'])
def update_transaction(id):
    """Update existing transaction"""
    init_session()
    
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
        
        # Get transactions from session
        transactions = session.get('transactions', [])
        
        # Find and update transaction
        updated = False
        for i, t in enumerate(transactions):
            if t['id'] == id:
                # Update transaction (keep original date)
                transactions[i] = {
                    'id': id,
                    'description': description,
                    'category': category,
                    'transaction': transaction_type,
                    'amount': amount,
                    'date': t['date']  # Keep original date
                }
                updated = True
                break
        
        if updated:
            # Save back to session
            session['transactions'] = transactions
            flash(f'Transaksi "{description}" berhasil diperbarui', 'success')
        else:
            flash('Transaksi tidak ditemukan', 'error')
        
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
    
    return redirect('/transactions')

@app.route('/delete/<int:id>')
def delete_transaction(id):
    """Delete transaction"""
    init_session()
    transactions = session.get('transactions', [])
    
    # Find transaction to delete
    transaction_to_delete = next((t for t in transactions if t['id'] == id), None)
    
    if transaction_to_delete:
        # Remove transaction
        transactions = [t for t in transactions if t['id'] != id]
        session['transactions'] = transactions
        
        flash(f'Transaksi "{transaction_to_delete["description"]}" berhasil dihapus', 'success')
    else:
        flash('Transaksi tidak ditemukan', 'error')
    
    return redirect('/transactions')

@app.route('/clear-all')
def clear_all():
    """Clear all transactions"""
    session['transactions'] = []
    session['next_id'] = 1
    flash('Semua transaksi berhasil dihapus', 'success')
    return redirect('/')

@app.route('/reports')
def reports():
    """Reports page"""
    init_session()
    totals = calculate_totals()
    
    return render_template('reports.html', **totals)

@app.route('/export/excel')
def export_excel():
    """Export transactions to Excel"""
    init_session()
    transactions = session.get('transactions', [])
    
    if not transactions:
        flash('Tidak ada data untuk diexport', 'error')
        return redirect('/reports')
    
    try:
        # Prepare data for DataFrame
        data = []
        for t in transactions:
            display_date = format_datetime_for_display(t['date'])
            
            data.append({
                'ID': t['id'],
                'Tanggal': display_date,
                'Deskripsi': t['description'],
                'Kategori': 'Cash' if t['category'] == 'cash' else 'Non-Cash',
                'Jenis': 'Pemasukan' if t['transaction'] == 'income' else 'Pengeluaran',
                'Jumlah (Rp)': t['amount'],
                'Status': 'Pemasukan' if t['transaction'] == 'income' else 'Pengeluaran'
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
    init_session()
    transactions = session.get('transactions', [])
    
    if not transactions:
        flash('Tidak ada data untuk diexport', 'error')
        return redirect('/reports')
    
    try:
        # Prepare data
        data = []
        for t in transactions:
            display_date = format_datetime_for_display(t['date'])
            
            data.append({
                'ID': t['id'],
                'Tanggal': display_date,
                'Deskripsi': t['description'],
                'Kategori': 'Cash' if t['category'] == 'cash' else 'Non-Cash',
                'Jenis': 'Pemasukan' if t['transaction'] == 'income' else 'Pengeluaran',
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
    init_session()
    
    # Get current datetime
    now = get_current_datetime()
    
    sample_transactions = [
        {
            'id': 1,
            'description': 'Gaji Bulanan',
            'category': 'cash',
            'transaction': 'income',
            'amount': 5000000,
            'date': (now - timedelta(days=30)).isoformat()
        },
        {
            'id': 2,
            'description': 'Bayar Listrik',
            'category': 'non cash',
            'transaction': 'expenditure',
            'amount': 750000,
            'date': (now - timedelta(days=25)).isoformat()
        },
        {
            'id': 3,
            'description': 'Freelance Project',
            'category': 'non cash',
            'transaction': 'income',
            'amount': 3000000,
            'date': (now - timedelta(days=20)).isoformat()
        },
        {
            'id': 4,
            'description': 'Belanja Bulanan',
            'category': 'cash',
            'transaction': 'expenditure',
            'amount': 1200000,
            'date': (now - timedelta(days=15)).isoformat()
        },
        {
            'id': 5,
            'description': 'Investasi Saham',
            'category': 'non cash',
            'transaction': 'income',
            'amount': 2000000,
            'date': (now - timedelta(days=10)).isoformat()
        }
    ]
    
    session['transactions'] = sample_transactions
    session['next_id'] = 6
    
    flash('Sample data berhasil ditambahkan', 'success')
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


# ========== ERROR HANDLERS ==========
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    session.clear()
    return render_template('500.html'), 500

# ========== MAIN ==========

# ========== PRODUCTION CONFIG ==========
if __name__ == '__main__':
    # Untuk production, gunakan environment variable PORT
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
