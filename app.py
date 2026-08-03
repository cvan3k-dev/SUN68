#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   SUN68 - CASINO TÀI XỈU ONLINE (NHIỀU FILE)
#   Version: 3.0 | Flask + SQLite | Giao diện Sunwin
#   Cấu trúc: app.py + app/templates/
# ═══════════════════════════════════════════════════════════════════

import os
import json
import hashlib
import random
import time
import threading
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, desc

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'app', 'templates')

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sun68-secret-key-change-me')

# ─── DATABASE ──────────────────────────────────────────────────────
DATA_DIR = '/tmp/sun68_data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = os.path.join(DATA_DIR, 'sun68.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vui lòng đăng nhập SUN68'

# ─── FILTER ──────────────────────────────────────────────────────
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        return "0 VND"
    return f"{int(value):,} VND".replace(',', '.')

# ═══════════════════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════════════════
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    total_deposited = db.Column(db.Float, default=0.0)
    total_bet = db.Column(db.Float, default=0.0)
    total_win = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    first_deposit_bonus = db.Column(db.Boolean, default=False)
    bonus_requirements_met = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    type = db.Column(db.String(20))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20), default='pending')
    method = db.Column(db.String(50))
    description = db.Column(db.String(200))
    reference_code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

class BetHistory(db.Model):
    __tablename__ = 'bet_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    bet_type = db.Column(db.String(10))
    bet_amount = db.Column(db.Float)
    result = db.Column(db.String(10))
    win_amount = db.Column(db.Float, default=0.0)
    is_win = db.Column(db.Boolean, default=False)
    round_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('bets', lazy=True))

class RoundHistory(db.Model):
    __tablename__ = 'round_history'
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, unique=True)
    result = db.Column(db.String(10))
    hash_md5 = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ═══════════════════════════════════════════════════════════════════
#  FLASK-LOGIN
# ═══════════════════════════════════════════════════════════════════
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ═══════════════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════════════
def generate_md5_result():
    seed = f"{datetime.utcnow().timestamp()}{random.randint(1000, 9999)}"
    hash_obj = hashlib.md5(seed.encode())
    hash_hex = hash_obj.hexdigest()
    last_char = hash_hex[-1]
    result = "TAI" if int(last_char, 16) % 2 == 0 else "XIU"
    return result, hash_hex

def get_current_round():
    latest = RoundHistory.query.order_by(RoundHistory.round_id.desc()).first()
    if latest and (datetime.utcnow() - latest.created_at).seconds < 50:
        return latest
    
    result, hash_md5 = generate_md5_result()
    new_round = RoundHistory(
        round_id=len(RoundHistory.query.all()) + 1,
        result=result,
        hash_md5=hash_md5
    )
    db.session.add(new_round)
    db.session.commit()
    
    old_rounds = RoundHistory.query.order_by(RoundHistory.round_id.asc()).all()
    if len(old_rounds) > 50:
        for r in old_rounds[:-50]:
            db.session.delete(r)
        db.session.commit()
    
    return new_round

def check_bonus_requirement(user):
    if not user.first_deposit_bonus:
        return True
    if user.bonus_requirements_met:
        return True
    
    total_bet = db.session.query(func.sum(BetHistory.bet_amount)).filter(
        BetHistory.user_id == user.id,
        BetHistory.is_win.isnot(None)
    ).scalar() or 0
    
    required = (50000 + 200000) * 3
    if total_bet >= required:
        user.bonus_requirements_met = True
        db.session.commit()
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.first_deposit_bonus and not current_user.bonus_requirements_met:
            check_bonus_requirement(current_user)
    
    current_round = get_current_round()
    history = RoundHistory.query.order_by(RoundHistory.round_id.desc()).limit(50).all()
    
    return render_template('index.html', 
                         current_round=current_round,
                         history=reversed(history),
                         balance=current_user.balance if current_user.is_authenticated else 0)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Tài khoản đã bị khóa', 'danger')
                return render_template('login.html')
            login_user(user)
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('index'))
        flash('Sai tên đăng nhập hoặc mật khẩu', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        display_name = request.form.get('display_name', username)
        
        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập đã tồn tại', 'danger')
            return render_template('register.html')
        
        if len(username) < 4:
            flash('Tên đăng nhập ít nhất 4 ký tự', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Mật khẩu ít nhất 6 ký tự', 'danger')
            return render_template('register.html')
        
        if password != confirm:
            flash('Mật khẩu xác nhận không khớp', 'danger')
            return render_template('register.html')
        
        new_user = User(username=username, display_name=display_name)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if request.method == 'POST':
        method = request.form.get('method')
        amount = float(request.form.get('amount', 0))
        
        if amount <= 0:
            flash('Số tiền nạp phải > 0', 'danger')
            return redirect(url_for('deposit'))
        
        ref_code = f"DEP{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        
        transaction = Transaction(
            user_id=current_user.id,
            type='deposit',
            amount=amount,
            status='pending',
            method=method,
            reference_code=ref_code,
            description=f'Nạp tiền SUN68 qua {method}'
        )
        
        if method == 'card':
            transaction.card_code = request.form.get('card_code')
            transaction.card_serial = request.form.get('card_serial')
            transaction.card_provider = request.form.get('card_provider')
            transaction.card_value = amount
        elif method == 'bank_transfer':
            transaction.description = f'Nạp tiền SUN68 qua ngân hàng - {request.form.get("bank_note", "")}'
        else:
            flash('Phương thức nạp không hợp lệ', 'danger')
            return redirect(url_for('deposit'))
        
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'Đã tạo lệnh nạp {amount:,.0f} VND. Chờ admin duyệt.', 'success')
        return redirect(url_for('deposit'))
    
    return render_template('deposit.html')

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        bank_name = request.form.get('bank_name')
        bank_account = request.form.get('bank_account')
        bank_holder = request.form.get('bank_holder')
        
        if amount < 200000:
            flash('Số tiền rút tối thiểu 200,000 VND', 'danger')
            return redirect(url_for('withdraw'))
        
        if amount > 100000000:
            flash('Số tiền rút tối đa 100,000,000 VND', 'danger')
            return redirect(url_for('withdraw'))
        
        if amount > current_user.balance:
            flash('Số dư không đủ', 'danger')
            return redirect(url_for('withdraw'))
        
        if not check_bonus_requirement(current_user):
            flash('Bạn chưa đạt yêu cầu x3 vòng cược', 'danger')
            return redirect(url_for('withdraw'))
        
        ref_code = f"WIT{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        
        transaction = Transaction(
            user_id=current_user.id,
            type='withdraw',
            amount=amount,
            status='pending',
            method='bank_transfer',
            reference_code=ref_code,
            description=f'Rút tiền SUN68 về {bank_name} - {bank_account}',
            bank_name=bank_name,
            bank_account=bank_account,
            bank_holder=bank_holder
        )
        
        current_user.balance -= amount
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'Đã tạo đơn rút {amount:,.0f} VND. Chờ admin duyệt.', 'success')
        return redirect(url_for('withdraw'))
    
    return render_template('withdraw.html')

@app.route('/ranking')
def ranking():
    today = datetime.utcnow().date()
    month_start = datetime(today.year, today.month, 1)
    
    top_deposit_daily = db.session.query(
        User.id, User.username, User.display_name,
        func.sum(Transaction.amount).label('total_deposit')
    ).join(Transaction)\
     .filter(Transaction.type == 'deposit',
             Transaction.status == 'approved',
             func.date(Transaction.created_at) == today)\
     .group_by(User.id)\
     .order_by(func.sum(Transaction.amount).desc()).limit(10).all()
    
    top_deposit_monthly = db.session.query(
        User.id, User.username, User.display_name,
        func.sum(Transaction.amount).label('total_deposit')
    ).join(Transaction)\
     .filter(Transaction.type == 'deposit',
             Transaction.status == 'approved',
             Transaction.created_at >= month_start)\
     .group_by(User.id)\
     .order_by(func.sum(Transaction.amount).desc()).limit(10).all()
    
    top_bet = db.session.query(
        User.id, User.username, User.display_name,
        func.sum(BetHistory.bet_amount).label('total_bet'),
        func.sum(BetHistory.win_amount).label('total_win')
    ).join(BetHistory)\
     .group_by(User.id)\
     .order_by(func.sum(BetHistory.bet_amount).desc()).limit(10).all()
    
    return render_template('ranking.html',
                         top_deposit_daily=top_deposit_daily,
                         top_deposit_monthly=top_deposit_monthly,
                         top_bet=top_bet)

@app.route('/history')
@login_required
def history():
    bets = BetHistory.query.filter_by(user_id=current_user.id)\
        .order_by(BetHistory.created_at.desc()).limit(100).all()
    return render_template('history.html', bets=bets)

# ═══════════════════════════════════════════════════════════════════
#  API
# ═══════════════════════════════════════════════════════════════════
@app.route('/api/bet', methods=['POST'])
@login_required
def place_bet():
    data = request.get_json()
    bet_type = data.get('bet_type')
    bet_amount = float(data.get('bet_amount', 0))
    
    if bet_type not in ['TAI', 'XIU']:
        return jsonify({'error': 'Loại cược không hợp lệ'}), 400
    
    if bet_amount <= 0:
        return jsonify({'error': 'Số tiền cược phải > 0'}), 400
    
    if bet_amount > current_user.balance:
        return jsonify({'error': 'Số dư không đủ'}), 400
    
    current_round = get_current_round()
    if (datetime.utcnow() - current_round.created_at).seconds > 50:
        return jsonify({'error': 'Đã hết thời gian đặt cược'}), 400
    
    current_user.balance -= bet_amount
    current_user.total_bet += bet_amount
    
    bet = BetHistory(
        user_id=current_user.id,
        bet_type=bet_type,
        bet_amount=bet_amount,
        round_id=current_round.round_id
    )
    db.session.add(bet)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Đặt cược {bet_type} với {bet_amount:,.0f} VND thành công',
        'new_balance': current_user.balance
    })

@app.route('/api/round_result')
def get_round_result():
    current_round = get_current_round()
    history = RoundHistory.query.order_by(RoundHistory.round_id.desc()).limit(50).all()
    return jsonify({
        'round_id': current_round.round_id,
        'result': current_round.result,
        'hash_md5': current_round.hash_md5,
        'history': [{'round': r.round_id, 'result': r.result} for r in history[:20]],
        'time_remaining': max(0, 50 - (datetime.utcnow() - current_round.created_at).seconds)
    })

# ═══════════════════════════════════════════════════════════════════
#  ADMIN
# ═══════════════════════════════════════════════════════════════════
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bạn không có quyền truy cập', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_balance = db.session.query(func.sum(User.balance)).scalar() or 0
    pending_deposits = Transaction.query.filter_by(type='deposit', status='pending').count()
    pending_withdraws = Transaction.query.filter_by(type='withdraw', status='pending').count()
    recent_transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(20).all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_balance=total_balance,
                         pending_deposits=pending_deposits,
                         pending_withdraws=pending_withdraws,
                         recent_transactions=recent_transactions)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/transactions')
@login_required
@admin_required
def admin_transactions():
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return render_template('admin/transactions.html', transactions=transactions)

@app.route('/admin/transaction/<int:txn_id>/approve', methods=['POST'])
@login_required
@admin_required
def admin_approve_transaction(txn_id):
    transaction = Transaction.query.get_or_404(txn_id)
    user = User.query.get(transaction.user_id)
    
    if transaction.status != 'pending':
        flash('Giao dịch đã được xử lý', 'warning')
        return redirect(url_for('admin_transactions'))
    
    if transaction.type == 'deposit':
        user.balance += transaction.amount
        if not user.first_deposit_bonus and transaction.amount >= 50000:
            bonus_amount = 200000
            user.balance += bonus_amount
            user.first_deposit_bonus = True
            bonus_txn = Transaction(
                user_id=user.id, type='bonus', amount=bonus_amount,
                status='approved', method='system',
                description='Khuyến mãi nạp đầu SUN68 50k -> 250k'
            )
            db.session.add(bonus_txn)
            flash(f'Đã duyệt nạp và tặng bonus {bonus_amount:,.0f} VND', 'success')
        transaction.status = 'approved'
    elif transaction.type == 'withdraw':
        if user.first_deposit_bonus and not user.bonus_requirements_met:
            flash('User chưa đạt x3 vòng cược', 'danger')
            return redirect(url_for('admin_transactions'))
        transaction.status = 'approved'
        flash(f'Đã duyệt rút {transaction.amount:,.0f} VND', 'success')
    
    transaction.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('admin_transactions'))

@app.route('/admin/transaction/<int:txn_id>/reject', methods=['POST'])
@login_required
@admin_required
def admin_reject_transaction(txn_id):
    transaction = Transaction.query.get_or_404(txn_id)
    user = User.query.get(transaction.user_id)
    
    if transaction.status != 'pending':
        flash('Giao dịch đã được xử lý', 'warning')
        return redirect(url_for('admin_transactions'))
    
    if transaction.type == 'withdraw':
        user.balance += transaction.amount
    
    transaction.status = 'rejected'
    transaction.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Đã từ chối giao dịch', 'warning')
    return redirect(url_for('admin_transactions'))

# ═══════════════════════════════════════════════════════════════════
#  BACKGROUND TASK
# ═══════════════════════════════════════════════════════════════════
def auto_generate_rounds():
    while True:
        try:
            time.sleep(50)
            result, hash_md5 = generate_md5_result()
            current_round = get_current_round()
            new_round = RoundHistory(
                round_id=current_round.round_id + 1,
                result=result,
                hash_md5=hash_md5
            )
            db.session.add(new_round)
            
            pending_bets = BetHistory.query.filter_by(
                round_id=current_round.round_id,
                result=None
            ).all()
            
            for bet in pending_bets:
                if bet.bet_type == result:
                    win_amount = bet.bet_amount * 0.98
                    bet.win_amount = win_amount
                    bet.is_win = True
                    bet.result = result
                    user = User.query.get(bet.user_id)
                    if user:
                        user.balance += win_amount
                        user.total_win += win_amount
                else:
                    bet.is_win = False
                    bet.result = result
            
            db.session.commit()
            print(f"✅ SUN68 Vòng {new_round.round_id}: {result}")
        except Exception as e:
            print(f"⚠️ Lỗi auto: {e}")
            db.session.rollback()
        time.sleep(5)

threading.Thread(target=auto_generate_rounds, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', display_name='Admin SUN68', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin SUN68: admin / admin123")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
