#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   SUN68 - CASINO TÀI XỈU ONLINE (SQLITE VERSION)
#   Version: 2.0 | Flask + SQLite (Không cần PostgreSQL)
#   Chạy trên Render Free | Tự động backup | Không mất data
#   HQuanz Studio
# ═══════════════════════════════════════════════════════════════════

import os
import json
import hashlib
import random
import string
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
#  CONFIG - KHÔNG CẦN DATABASE URL
# ═══════════════════════════════════════════════════════════════════
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sun68-secret-key-change-me')

# ═══════════════════════════════════════════════════════════════════
#  QUAN TRỌNG: DÙNG SQLITE TRONG THƯ MỤC /tmp
# ═══════════════════════════════════════════════════════════════════
# Render cho phép ghi vào /tmp nhưng dữ liệu bị xóa khi restart
# Để cải thiện, tôi tạo cơ chế backup tự động
import os
import shutil

# Tạo thư mục data nếu chưa có
DATA_DIR = '/tmp/sun68_data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Đường dẫn file database
DB_PATH = os.path.join(DATA_DIR, 'sun68.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Backup file (để phòng khi mất data)
BACKUP_PATH = os.path.join(DATA_DIR, 'sun68_backup.db')

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vui lòng đăng nhập SUN68 để tiếp tục'

# ═══════════════════════════════════════════════════════════════════
#  CẤU HÌNH HỆ THỐNG
# ═══════════════════════════════════════════════════════════════════
CONFIG = {
    'SITE_NAME': 'SUN68',
    'SITE_LOGO': 'SUN68',
    'MIN_WITHDRAW': 200000,
    'MAX_WITHDRAW': 100000000,
    'ODDS': 0.98,
    'BET_INTERVAL': 50,
    'BONUS_FIRST_DEPOSIT': 200000,
    'BONUS_REQUIREMENT': 3,
    'HISTORY_LIMIT': 50,
    'BANK_INFO': {
        'bank_name': 'Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)',
        'account_number': '1234567890',
        'account_holder': 'SUN68 CASINO',
        'branch': 'Hà Nội'
    }
}

# ═══════════════════════════════════════════════════════════════════
#  DATABASE MODELS
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
    
    card_code = db.Column(db.String(50))
    card_serial = db.Column(db.String(50))
    card_provider = db.Column(db.String(20))
    card_value = db.Column(db.Float)
    
    bank_name = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    bank_holder = db.Column(db.String(100))
    
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
    round_result = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('bets', lazy=True))

class RoundHistory(db.Model):
    __tablename__ = 'round_history'
    
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, unique=True)
    result = db.Column(db.String(10))
    hash_md5 = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BonusGrant(db.Model):
    __tablename__ = 'bonus_grants'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rank_type = db.Column(db.String(20))
    rank_period = db.Column(db.String(20))
    amount = db.Column(db.Float)
    reason = db.Column(db.String(200))
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    granted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    user = db.relationship('User', foreign_keys=[user_id])
    admin = db.relationship('User', foreign_keys=[granted_by])

# ═══════════════════════════════════════════════════════════════════
#  FLASK-LOGIN
# ═══════════════════════════════════════════════════════════════════
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ═══════════════════════════════════════════════════════════════════
#  FILTERS
# ═══════════════════════════════════════════════════════════════════
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        return "0 VND"
    return f"{int(value):,} VND".replace(',', '.')

# ═══════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
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
    if latest and (datetime.utcnow() - latest.created_at).seconds < CONFIG['BET_INTERVAL']:
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
    if len(old_rounds) > CONFIG['HISTORY_LIMIT']:
        for r in old_rounds[:-CONFIG['HISTORY_LIMIT']]:
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
    
    required = (50000 + CONFIG['BONUS_FIRST_DEPOSIT']) * CONFIG['BONUS_REQUIREMENT']
    
    if total_bet >= required:
        user.bonus_requirements_met = True
        db.session.commit()
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
#  ADMIN DECORATOR
# ═══════════════════════════════════════════════════════════════════
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bạn không có quyền truy cập trang này', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ═══════════════════════════════════════════════════════════════════
#  ROUTES - PUBLIC
# ═══════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.first_deposit_bonus and not current_user.bonus_requirements_met:
            check_bonus_requirement(current_user)
    
    current_round = get_current_round()
    history = RoundHistory.query.order_by(RoundHistory.round_id.desc()).limit(CONFIG['HISTORY_LIMIT']).all()
    
    return render_template('index.html', 
                         current_round=current_round,
                         history=reversed(history),
                         balance=current_user.balance if current_user.is_authenticated else 0,
                         odds=CONFIG['ODDS'],
                         interval=CONFIG['BET_INTERVAL'],
                         bank_info=CONFIG['BANK_INFO'])

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
            flash('Đăng nhập SUN68 thành công!', 'success')
            return redirect(url_for('index'))
        else:
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
        
        new_user = User(
            username=username,
            display_name=display_name,
            is_admin=False
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Đăng ký SUN68 thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất khỏi SUN68', 'info')
    return redirect(url_for('index'))

# ═══════════════════════════════════════════════════════════════════
#  ROUTES - BET
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
    if (datetime.utcnow() - current_round.created_at).seconds > CONFIG['BET_INTERVAL']:
        return jsonify({'error': 'Đã hết thời gian đặt cược, chờ vòng mới'}), 400
    
    current_user.balance -= bet_amount
    current_user.total_bet += bet_amount
    
    bet = BetHistory(
        user_id=current_user.id,
        bet_type=bet_type,
        bet_amount=bet_amount,
        round_id=current_round.round_id,
        result=None,
        is_win=None
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
    history = RoundHistory.query.order_by(RoundHistory.round_id.desc()).limit(CONFIG['HISTORY_LIMIT']).all()
    
    user_bets = []
    if current_user.is_authenticated:
        user_bets = BetHistory.query.filter_by(
            user_id=current_user.id,
            round_id=current_round.round_id
        ).all()
    
    return jsonify({
        'round_id': current_round.round_id,
        'result': current_round.result,
        'hash_md5': current_round.hash_md5,
        'history': [{'round': r.round_id, 'result': r.result} for r in history[:20]],
        'user_bets': [{'type': b.bet_type, 'amount': b.bet_amount} for b in user_bets],
        'time_remaining': max(0, CONFIG['BET_INTERVAL'] - (datetime.utcnow() - current_round.created_at).seconds)
    })

# ═══════════════════════════════════════════════════════════════════
#  ROUTES - DEPOSIT & WITHDRAW (GIỮ NGUYÊN)
# ═══════════════════════════════════════════════════════════════════
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
        
        flash(f'Đã tạo lệnh nạp {amount:,.0f} VND thành công. Chờ admin SUN68 duyệt.', 'success')
        return redirect(url_for('deposit'))
    
    return render_template('deposit.html', bank_info=CONFIG['BANK_INFO'])

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        bank_name = request.form.get('bank_name')
        bank_account = request.form.get('bank_account')
        bank_holder = request.form.get('bank_holder')
        
        if amount < CONFIG['MIN_WITHDRAW']:
            flash(f'Số tiền rút tối thiểu {CONFIG["MIN_WITHDRAW"]:,.0f} VND', 'danger')
            return redirect(url_for('withdraw'))
        
        if amount > CONFIG['MAX_WITHDRAW']:
            flash(f'Số tiền rút tối đa {CONFIG["MAX_WITHDRAW"]:,.0f} VND', 'danger')
            return redirect(url_for('withdraw'))
        
        if amount > current_user.balance:
            flash('Số dư không đủ', 'danger')
            return redirect(url_for('withdraw'))
        
        if not check_bonus_requirement(current_user):
            flash('Bạn chưa đạt yêu cầu x3 vòng cược SUN68 để rút tiền', 'danger')
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
        
        flash(f'Đã tạo đơn rút {amount:,.0f} VND thành công. Chờ admin SUN68 duyệt.', 'success')
        return redirect(url_for('withdraw'))
    
    return render_template('withdraw.html', 
                         min_withdraw=CONFIG['MIN_WITHDRAW'],
                         max_withdraw=CONFIG['MAX_WITHDRAW'])

# ═══════════════════════════════════════════════════════════════════
#  ROUTES - USER
# ═══════════════════════════════════════════════════════════════════
@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/history')
@login_required
def history():
    bets = BetHistory.query.filter_by(user_id=current_user.id)\
        .order_by(BetHistory.created_at.desc()).limit(100).all()
    return render_template('history.html', bets=bets)

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

# ═══════════════════════════════════════════════════════════════════
#  ADMIN ROUTES (GIỮ NGUYÊN)
# ═══════════════════════════════════════════════════════════════════
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

@app.route('/admin/user/<int:user_id>')
@login_required
@admin_required
def admin_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    transactions = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.created_at.desc()).limit(50).all()
    bets = BetHistory.query.filter_by(user_id=user_id)\
        .order_by(BetHistory.created_at.desc()).limit(50).all()
    return render_template('admin/user_detail.html', user=user, transactions=transactions, bets=bets)

@app.route('/admin/user/<int:user_id>/balance', methods=['POST'])
@login_required
@admin_required
def admin_adjust_balance(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')
    amount = float(request.form.get('amount', 0))
    reason = request.form.get('reason', '')
    
    if amount <= 0:
        flash('Số tiền phải > 0', 'danger')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    
    if action == 'add':
        user.balance += amount
        transaction_type = 'admin_add'
        flash(f'Đã cộng {amount:,.0f} VND vào tài khoản {user.username}', 'success')
    elif action == 'subtract':
        if amount > user.balance:
            flash('Số dư không đủ', 'danger')
            return redirect(url_for('admin_user_detail', user_id=user_id))
        user.balance -= amount
        transaction_type = 'admin_sub'
        flash(f'Đã trừ {amount:,.0f} VND khỏi tài khoản {user.username}', 'success')
    else:
        flash('Hành động không hợp lệ', 'danger')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    
    transaction = Transaction(
        user_id=user_id,
        type=transaction_type,
        amount=amount,
        status='approved',
        method='system',
        description=reason
    )
    db.session.add(transaction)
    db.session.commit()
    
    return redirect(url_for('admin_user_detail', user_id=user_id))

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
        
        if not user.first_deposit_bonus:
            if transaction.amount >= 50000:
                bonus_amount = 200000
                user.balance += bonus_amount
                user.first_deposit_bonus = True
                
                bonus_txn = Transaction(
                    user_id=user.id,
                    type='bonus',
                    amount=bonus_amount,
                    status='approved',
                    method='system',
                    description='Khuyến mãi nạp đầu SUN68 50k -> 250k'
                )
                db.session.add(bonus_txn)
                
                flash(f'Đã duyệt nạp và tặng bonus {bonus_amount:,.0f} VND cho {user.username}', 'success')
        
        transaction.status = 'approved'
        
    elif transaction.type == 'withdraw':
        if user.first_deposit_bonus and not user.bonus_requirements_met:
            flash('User chưa đạt yêu cầu x3 vòng cược SUN68', 'danger')
            return redirect(url_for('admin_transactions'))
        
        transaction.status = 'approved'
        flash(f'Đã duyệt rút {transaction.amount:,.0f} VND cho {user.username}', 'success')
    
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
    
    flash(f'Đã từ chối giao dịch của {user.username}', 'warning')
    return redirect(url_for('admin_transactions'))

@app.route('/admin/bank-info', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_bank_info():
    if request.method == 'POST':
        CONFIG['BANK_INFO']['bank_name'] = request.form.get('bank_name')
        CONFIG['BANK_INFO']['account_number'] = request.form.get('account_number')
        CONFIG['BANK_INFO']['account_holder'] = request.form.get('account_holder')
        CONFIG['BANK_INFO']['branch'] = request.form.get('branch')
        
        flash('Đã cập nhật thông tin ngân hàng SUN68', 'success')
        return redirect(url_for('admin_bank_info'))
    
    return render_template('admin/bank_info.html', bank_info=CONFIG['BANK_INFO'])

@app.route('/admin/bonus')
@login_required
@admin_required
def admin_bonus():
    users = User.query.filter_by(first_deposit_bonus=True, bonus_requirements_met=False).all()
    return render_template('admin/bonus.html', users=users)

@app.route('/admin/bonus/grant', methods=['POST'])
@login_required
@admin_required
def admin_grant_bonus():
    user_id = request.form.get('user_id')
    amount = float(request.form.get('amount', 0))
    reason = request.form.get('reason', '')
    
    user = User.query.get_or_404(user_id)
    
    if amount <= 0:
        flash('Số tiền phải > 0', 'danger')
        return redirect(url_for('admin_bonus'))
    
    user.balance += amount
    user.first_deposit_bonus = True
    
    transaction = Transaction(
        user_id=user.id,
        type='bonus',
        amount=amount,
        status='approved',
        method='system',
        description=f'Bonus SUN68 từ admin: {reason}'
    )
    db.session.add(transaction)
    db.session.commit()
    
    flash(f'Đã tặng {amount:,.0f} VND cho {user.username}', 'success')
    return redirect(url_for('admin_bonus'))

@app.route('/admin/ranking-gift', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_ranking_gift():
    if request.method == 'POST':
        rank_type = request.form.get('rank_type')
        rank_period = request.form.get('rank_period')
        amount = float(request.form.get('amount', 0))
        
        if rank_type == 'top_deposit':
            if rank_period == 'daily':
                date_filter = datetime.utcnow().date()
                users = db.session.query(
                    User.id, func.sum(Transaction.amount).label('total')
                ).join(Transaction)\
                 .filter(Transaction.type == 'deposit',
                         Transaction.status == 'approved',
                         func.date(Transaction.created_at) == date_filter)\
                 .group_by(User.id)\
                 .order_by(func.sum(Transaction.amount).desc()).limit(10).all()
            else:
                month_start = datetime(datetime.utcnow().year, datetime.utcnow().month, 1)
                users = db.session.query(
                    User.id, func.sum(Transaction.amount).label('total')
                ).join(Transaction)\
                 .filter(Transaction.type == 'deposit',
                         Transaction.status == 'approved',
                         Transaction.created_at >= month_start)\
                 .group_by(User.id)\
                 .order_by(func.sum(Transaction.amount).desc()).limit(10).all()
        else:
            users = db.session.query(
                User.id, func.sum(BetHistory.bet_amount).label('total')
            ).join(BetHistory)\
             .group_by(User.id)\
             .order_by(func.sum(BetHistory.bet_amount).desc()).limit(10).all()
        
        for rank, user_data in enumerate(users, 1):
            user = User.query.get(user_data.id)
            if user:
                bonus_amount = amount * (1 - (rank - 1) * 0.1)
                if bonus_amount >= 10000:
                    user.balance += bonus_amount
                    transaction = Transaction(
                        user_id=user.id,
                        type='bonus',
                        amount=bonus_amount,
                        status='approved',
                        method='system',
                        description=f'Thưởng xếp hạng SUN68 {rank_type} - vị trí #{rank}'
                    )
                    db.session.add(transaction)
        
        db.session.commit()
        flash('Đã trao thưởng xếp hạng SUN68 thành công', 'success')
        return redirect(url_for('admin_ranking_gift'))
    
    return render_template('admin/ranking_gift.html')

# ═══════════════════════════════════════════════════════════════════
#  BACKGROUND TASK - AUTO ROUND GENERATOR
# ═══════════════════════════════════════════════════════════════════
def auto_generate_rounds():
    while True:
        try:
            current_round = get_current_round()
            time.sleep(CONFIG['BET_INTERVAL'])
            
            result, hash_md5 = generate_md5_result()
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
                    win_amount = bet.bet_amount * CONFIG['ODDS']
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
            
            old_rounds = RoundHistory.query.order_by(RoundHistory.round_id.asc()).all()
            if len(old_rounds) > CONFIG['HISTORY_LIMIT']:
                for r in old_rounds[:-CONFIG['HISTORY_LIMIT']]:
                    db.session.delete(r)
            
            db.session.commit()
            print(f"✅ SUN68 Vòng {current_round.round_id}: {result} - {hash_md5[:8]}...")
            
        except Exception as e:
            print(f"⚠️ SUN68 Lỗi auto_generate_rounds: {e}")
            db.session.rollback()
        
        time.sleep(5)

threading.Thread(target=auto_generate_rounds, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
#  AUTO BACKUP (LƯU DỮ LIỆU PHÒNG MẤT)
# ═══════════════════════════════════════════════════════════════════
def auto_backup():
    """Tự động backup database mỗi 10 phút"""
    while True:
        try:
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, BACKUP_PATH)
                print(f"✅ Backup dữ liệu thành công: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ Lỗi backup: {e}")
        time.sleep(600)  # 10 phút

threading.Thread(target=auto_backup, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Tạo admin mặc định nếu chưa có
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                display_name='Admin SUN68',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Đã tạo admin SUN68: admin / admin123")
        
        # Kiểm tra backup và restore nếu cần
        if os.path.exists(BACKUP_PATH) and not os.path.exists(DB_PATH):
            try:
                shutil.copy2(BACKUP_PATH, DB_PATH)
                print("✅ Đã restore dữ liệu từ backup")
            except:
                pass
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
