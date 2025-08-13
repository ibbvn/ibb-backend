# Kiểm trafrom flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import sqlite3
import hashlib
import os
import json
import glob
import shutil
import re
from datetime import datetime, timedelta
from PIL import Image
import logging
from flask import Flask, request, jsonify, send_from_directory
app = Flask(__name__)
# Cấu hình cũ
DB_PATH = 'users.db'

# Cấu hình mới cho cấu trúc thư mục
DATA_DIR = 'data'
CHEBIEN_ACTIVE_DIR = os.path.join(DATA_DIR, 'chebien', 'active')
CHEBIEN_COMPLETED_DIR = os.path.join(DATA_DIR, 'chebien', 'completed')
QA_DIR = os.path.join(DATA_DIR, 'qa')
QA_LENMEN_DIR = os.path.join(DATA_DIR, 'qa', 'lenmen')
QA_LOC_DIR = os.path.join(DATA_DIR, 'qa', 'loc')
TANK_METRICS_DIR = os.path.join(DATA_DIR, 'tank_metrics')

# Cấu hình upload ảnh
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Tạo tất cả thư mục cần thiết
def create_directories():
    dirs_to_create = [
        CHEBIEN_ACTIVE_DIR,
        CHEBIEN_COMPLETED_DIR,
        QA_DIR,
        QA_LENMEN_DIR,
        QA_LOC_DIR,
        TANK_METRICS_DIR,
        UPLOAD_FOLDER,
        os.path.join(UPLOAD_FOLDER, 'Chebien', 'Plato'),
        os.path.join(UPLOAD_FOLDER, 'Chebien', 'Hanoi'),
        os.path.join(UPLOAD_FOLDER, 'Chebien', 'ChaiHG')
    ]
    
    for dir_path in dirs_to_create:
        os.makedirs(dir_path, exist_ok=True)
        print(f"📁 Created/verified directory: {dir_path}")

def create_user_table():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                full_name TEXT,
                department TEXT,
                role TEXT,
                active INTEGER DEFAULT 1
            )
        ''')
        conn.commit()

def hash_password(password):
    if password is None:
        raise ValueError("Password cannot be None")
    return hashlib.sha256(password.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compress_image(image_path, quality=85):
    """Nén ảnh để tiết kiệm dung lượng"""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            max_size = (1920, 1080)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(image_path, "JPEG", quality=quality, optimize=True)
            
    except Exception as e:
        print(f"Error compressing image: {e}")

# ==================== API CŨ (GIỮ NGUYÊN) ====================

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')

    # Ensure required credentials are provided
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400

    password_hash = hash_password(password)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, department, role, active FROM users WHERE username=? AND password_hash=?", (username, password_hash))
        result = cursor.fetchone()

    if result:
        full_name, department, role, active = result
        if not active:
            return jsonify({'success': False, 'message': 'Tài khoản đã bị khóa.'}), 403
        return jsonify({
            'success': True,
            'full_name': full_name,
            'department': department,
            'role': role
        })
    else:
        return jsonify({'success': False, 'message': 'Sai tài khoản hoặc mật khẩu'}), 401

@app.route('/create_user', methods=['POST'])
def create_user():
    data = request.json
    username = data['username']
    password = data['password']
    full_name = data['full_name']
    department = data['department']
    role = data['role']
    password_hash = hash_password(password)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password_hash, full_name, department, role) VALUES (?, ?, ?, ?, ?)",
                           (username, password_hash, full_name, department, role))
            conn.commit()
        return jsonify({'success': True, 'message': 'Tạo tài khoản thành công'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Tên đăng nhập đã tồn tại'}), 400

@app.route('/save_form', methods=['POST'])
def save_form():
    """API cũ - lưu vào active directory với format mới"""
    data = request.json
    now = datetime.now()
    ngay = now.strftime('%Y-%m-%d')
    ms = now.strftime('%H%M%S')
    
    # Lấy thông tin từ data
    me_so = str(data.get('field_002', data.get('me_so', '01'))).zfill(2)
    tank_so = str(data.get('field_003', data.get('tank_so', '01'))).zfill(2)
    beer_type = data.get('beer_type', 'river')
    
    # Format mới: YYYY-MM-DD_meXX_tankYY_HHMMSS.json
    filename = f'{ngay}_me{me_so}_tank{tank_so}_{ms}.json'
    
    # Thêm metadata
    data['created_at'] = now.isoformat()
    data['saved_via'] = 'save_form_api'
    data['beer_type'] = beer_type
    
    # Lưu vào active directory
    filepath = os.path.join(CHEBIEN_ACTIVE_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Saved batch to active: {filename}")
        return jsonify({
            'success': True, 
            'message': 'Đã lưu dữ liệu vào server',
            'filename': filename,
            'location': 'active'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi lưu file: {str(e)}'}), 500

# ==================== API MỚI CHO CHEBIEN ====================

@app.route('/api/chebien/active/tank/<int:tank_number>', methods=['GET'])
def get_active_batches_for_tank(tank_number):
    """Lấy tất cả phiếu nấu đang hoạt động cho tank cụ thể"""
    try:
        tank_pattern = f"_tank{tank_number:02d}_"
        batches = []
        
        # Quét tất cả file JSON trong active directory
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json') and tank_pattern in filename:
                file_path = os.path.join(CHEBIEN_ACTIVE_DIR, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                        batch_data['filename'] = filename
                        batch_data['file_path'] = file_path
                        batches.append(batch_data)
                except Exception as e:
                    print(f"❌ Error reading {filename}: {e}")
                    continue
        
        # Sắp xếp theo thời gian tạo (mới nhất trước)
        batches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        print(f"📋 Found {len(batches)} active batches for tank {tank_number}")
        
        return jsonify({
            'success': True,
            'batches': batches,
            'tank_number': tank_number,
            'count': len(batches)
        })
        
    except Exception as e:
        print(f"❌ Error getting active batches for tank {tank_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chebien/move-to-completed/tank/<int:tank_number>', methods=['POST'])
def move_tank_batches_to_completed(tank_number):
    """Di chuyển tất cả phiếu nấu của tank từ active sang completed"""
    try:
        data = request.get_json()
        total_filtered = data.get('total_filtered', 0)
        filter_date = data.get('filter_date')
        operator = data.get('operator', 'Unknown')
        
        tank_pattern = f"_tank{tank_number:02d}_"
        moved_count = 0
        errors = []
        
        # Tìm tất cả file của tank này
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json') and tank_pattern in filename:
                active_path = os.path.join(CHEBIEN_ACTIVE_DIR, filename)
                completed_path = os.path.join(CHEBIEN_COMPLETED_DIR, filename)
                
                try:
                    # Đọc và cập nhật dữ liệu
                    with open(active_path, 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                    
                    # Thêm metadata hoàn thành
                    batch_data['completed_at'] = datetime.now().isoformat()
                    batch_data['filter_date'] = filter_date
                    batch_data['total_filtered'] = total_filtered
                    batch_data['completed_by'] = operator
                    batch_data['status'] = 'completed'
                    
                    # Ghi vào completed directory
                    with open(completed_path, 'w', encoding='utf-8') as f:
                        json.dump(batch_data, f, ensure_ascii=False, indent=2)
                    
                    # Xóa khỏi active directory
                    os.remove(active_path)
                    moved_count += 1
                    
                    print(f"✅ Moved {filename} to completed")
                    
                except Exception as e:
                    error_msg = f"Error moving {filename}: {str(e)}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
        
        result = {
            'success': True,
            'moved_count': moved_count,
            'tank_number': tank_number,
            'message': f'Moved {moved_count} batches to completed'
        }
        
        if errors:
            result['errors'] = errors
            result['partial_success'] = True
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error moving batches for tank {tank_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chebien/all-active', methods=['GET'])
def get_all_active_batches():
    """Lấy tất cả phiếu nấu đang hoạt động"""
    try:
        batches = []
        
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(CHEBIEN_ACTIVE_DIR, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                        batch_data['filename'] = filename
                        batches.append(batch_data)
                except Exception as e:
                    print(f"❌ Error reading {filename}: {e}")
                    continue
        
        # Sắp xếp theo thời gian tạo
        batches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'batches': batches,
            'count': len(batches)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chebien/all-completed', methods=['GET'])
def get_all_completed_batches():
    """Lấy tất cả phiếu nấu đã hoàn thành"""
    try:
        batches = []
        
        for filename in os.listdir(CHEBIEN_COMPLETED_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(CHEBIEN_COMPLETED_DIR, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                        batch_data['filename'] = filename
                        batches.append(batch_data)
                except Exception as e:
                    print(f"❌ Error reading {filename}: {e}")
                    continue
        
        # Sắp xếp theo thời gian hoàn thành
        batches.sort(key=lambda x: x.get('completed_at', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'batches': batches,
            'count': len(batches)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API CHO QA - UPDATED ====================

@app.route('/api/qa/filtered-volume/tank/<int:tank_number>', methods=['GET'])
def get_filtered_volume_for_tank(tank_number):
    """Tính tổng volume đã lọc cho tank từ các file QA - Enhanced"""
    try:
        total_filtered = 0
        filter_files = []
        
        # Tìm tất cả file lọc cho tank này trong thư mục riêng
        pattern = f"loc_tank{tank_number}_day_*.json"
        qa_files = glob.glob(os.path.join(QA_LOC_DIR, pattern))
        
        for qa_file in qa_files:
            try:
                with open(qa_file, 'r', encoding='utf-8') as f:
                    qa_data = json.load(f)
                    
                    if 'lo_list' in qa_data and isinstance(qa_data['lo_list'], list):
                        file_filtered = 0
                        for lo in qa_data['lo_list']:
                            volume = float(lo.get('volume', 0))
                            file_filtered += volume
                            total_filtered += volume
                        
                        filter_files.append({
                            'filename': os.path.basename(qa_file),
                            'date': qa_data.get('ngay', 'Unknown'),
                            'volume_filtered': file_filtered,
                            'lo_count': len(qa_data['lo_list']),
                            'is_closed': qa_data.get('da_dong', False),
                            'created_at': qa_data.get('created_at'),
                            'updated_at': qa_data.get('updated_at')
                        })
                        
            except Exception as e:
                print(f"❌ Error reading QA filter file {qa_file}: {e}")
                continue
        
        # Sort by date (newest first)
        filter_files.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'totalFiltered': total_filtered,
            'tank_number': tank_number,
            'filter_files': filter_files,
            'files_count': len(filter_files),
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error getting filtered volume for tank {tank_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qa/tank-metrics/tank/<int:tank_number>', methods=['GET'])
def get_tank_metrics(tank_number):
    """Lấy nhiệt độ và áp suất hiện tại của tank từ lenmen logs"""
    try:
        metrics_file = os.path.join(TANK_METRICS_DIR, f'tank_{tank_number}_metrics.json')
        
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r', encoding='utf-8') as f:
                metrics = json.load(f)
                return jsonify({
                    'success': True,
                    'temperature': metrics.get('temperature', 10),
                    'pressure': metrics.get('pressure', 0),
                    'last_updated': metrics.get('last_updated'),
                    'tank_number': tank_number,
                    'source': metrics.get('source', 'metrics_file')
                })
        
        # Fallback: đọc từ file lên men mới nhất trong thư mục riêng
        latest_temp = 10
        latest_pressure = 0
        
        lenmen_pattern = f"tank_{tank_number}_day_*.json"
        lenmen_files = glob.glob(os.path.join(QA_LENMEN_DIR, lenmen_pattern))
        
        if lenmen_files:
            # Lấy file mới nhất
            latest_file = max(lenmen_files, key=os.path.getctime)
            
            try:
                with open(latest_file, 'r', encoding='utf-8') as f:
                    lenmen_data = json.load(f)
                    
                    if 'data' in lenmen_data and isinstance(lenmen_data['data'], list):
                        # Lấy nhiệt độ và áp suất từ ngày gần nhất có dữ liệu
                        for day_data in reversed(lenmen_data['data']):
                            if day_data.get('nhiet_do') and latest_temp == 10:
                                try:
                                    latest_temp = float(day_data['nhiet_do'])
                                except ValueError:
                                    pass
                            
                            if day_data.get('ap_suat') and latest_pressure == 0:
                                try:
                                    latest_pressure = float(day_data['ap_suat'])
                                except ValueError:
                                    pass
                            
                            if latest_temp != 10 and latest_pressure != 0:
                                break
                                
            except Exception as e:
                print(f"❌ Error reading lenmen file {latest_file}: {e}")
        
        return jsonify({
            'success': True,
            'temperature': latest_temp,
            'pressure': latest_pressure,
            'tank_number': tank_number,
            'source': 'lenmen_log_fallback',
            'note': 'Using default or lenmen log values'
        })
        
    except Exception as e:
        print(f"❌ Error getting tank metrics for tank {tank_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qa/lenmen/save', methods=['POST'])
def save_lenmen_log():
    """Lưu nhật ký lên men vào thư mục riêng và cập nhật real-time metrics"""
    try:
        data = request.get_json()
        tank_number = data.get('tank_number')
        log_data = data.get('log_data')
        filename = data.get('filename')
        
        # Lưu file nhật ký lên men vào thư mục riêng
        log_path = os.path.join(QA_LENMEN_DIR, filename)
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        
        # Trích xuất nhiệt độ và áp suất mới nhất
        latest_temp = None
        latest_pressure = None
        
        if 'data' in log_data and isinstance(log_data['data'], list):
            for day_data in reversed(log_data['data']):
                if day_data.get('nhiet_do') and latest_temp is None:
                    try:
                        latest_temp = float(day_data['nhiet_do'])
                    except ValueError:
                        pass
                
                if day_data.get('ap_suat') and latest_pressure is None:
                    try:
                        latest_pressure = float(day_data['ap_suat'])
                    except ValueError:
                        pass
                
                if latest_temp is not None and latest_pressure is not None:
                    break
        
        # Lưu metrics real-time
        metrics_data = {
            'tank_number': tank_number,
            'temperature': latest_temp if latest_temp is not None else 10,
            'pressure': latest_pressure if latest_pressure is not None else 0,
            'last_updated': datetime.now().isoformat(),
            'source': 'lenmen_log',
            'log_file': filename
        }
        
        metrics_path = os.path.join(TANK_METRICS_DIR, f'tank_{tank_number}_metrics.json')
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump(metrics_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Saved lenmen log: {filename} in QA_LENMEN_DIR")
        print(f"📊 Updated tank {tank_number} metrics: T={latest_temp}°C, P={latest_pressure}Bar")
        
        return jsonify({
            'success': True,
            'message': 'Lenmen log saved successfully',
            'filename': filename,
            'saved_to': 'qa/lenmen/',
            'tank_metrics_updated': {
                'temperature': latest_temp,
                'pressure': latest_pressure
            }
        })
        
    except Exception as e:
        print(f"❌ Error saving lenmen log: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== NEW API FOR TANK METRICS CONSOLIDATION ====================

@app.route('/api/tank/comprehensive-metrics/tank/<int:tank_number>', methods=['GET'])
def get_comprehensive_tank_metrics(tank_number):
    """
    Lấy thông số tank tổng hợp từ 3 nguồn:
    1. data/chebien/active - thể tích ban đầu, ngày bắt đầu, số mẻ
    2. data/qa/lenmen - nhiệt độ, áp suất cập nhật
    3. data/qa/loc - lượng đã lọc, lượng tồn
    """
    try:
        comprehensive_metrics = {
            'tank_number': tank_number,
            'status': 'empty',
            'batch_info': {
                'batch_count': 0,
                'latest_batch': None,
                'start_date': None,
                'total_initial_volume': 0,
                'beer_type': None
            },
            'current_metrics': {
                'temperature': 10,
                'pressure': 0,
                'last_updated': None
            },
            'filtering_info': {
                'total_filtered': 0,
                'remaining_volume': 0,
                'fill_percentage': 0,
                'filter_logs_count': 0,
                'last_filter_date': None
            },
            'data_sources': {
                'chebien_files': [],
                'lenmen_files': [],
                'loc_files': []
            }
        }
        
        # 1. Lấy thông tin từ Chế biến Active
        tank_pattern = f"_tank{tank_number:02d}_"
        active_batches = []
        
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json') and tank_pattern in filename:
                file_path = os.path.join(CHEBIEN_ACTIVE_DIR, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        batch_data = json.load(f)
                        batch_data['filename'] = filename
                        active_batches.append(batch_data)
                        comprehensive_metrics['data_sources']['chebien_files'].append(filename)
                except Exception as e:
                    print(f"❌ Error reading chebien file {filename}: {e}")
                    continue
        
        if active_batches:
            comprehensive_metrics['status'] = 'active'
            comprehensive_metrics['batch_info']['batch_count'] = len(active_batches)
            
            # Tính tổng thể tích ban đầu
            total_volume = 0
            latest_date = None
            latest_batch = None
            beer_type = None
            
            for batch in active_batches:
                # Thể tích (field_025 hoặc the_tich_dau)
                volume = float(batch.get('field_025', batch.get('the_tich_dau', 0)))
                total_volume += volume
                
                # Ngày tạo mới nhất
                created_at = batch.get('created_at', batch.get('field_001'))
                if not latest_date or (created_at and created_at > latest_date):
                    latest_date = created_at
                    latest_batch = batch.get('field_002', batch.get('me_so'))
                
                # Loại bia
                if not beer_type:
                    beer_type = batch.get('beer_type', 'river')
            
            comprehensive_metrics['batch_info']['total_initial_volume'] = total_volume
            comprehensive_metrics['batch_info']['latest_batch'] = latest_batch
            comprehensive_metrics['batch_info']['start_date'] = latest_date
            comprehensive_metrics['batch_info']['beer_type'] = beer_type
        
        # 2. Lấy nhiệt độ, áp suất từ Lenmen logs
        lenmen_pattern = f"tank_{tank_number}_day_*.json"
        lenmen_files = glob.glob(os.path.join(QA_LENMEN_DIR, lenmen_pattern))
        
        if lenmen_files:
            # Lấy file mới nhất
            latest_lenmen_file = max(lenmen_files, key=os.path.getctime)
            comprehensive_metrics['data_sources']['lenmen_files'] = [os.path.basename(f) for f in lenmen_files]
            
            try:
                with open(latest_lenmen_file, 'r', encoding='utf-8') as f:
                    lenmen_data = json.load(f)
                    
                    if 'data' in lenmen_data and isinstance(lenmen_data['data'], list):
                        # Lấy dữ liệu mới nhất có nhiệt độ/áp suất
                        for day_data in reversed(lenmen_data['data']):
                            if day_data.get('nhiet_do'):
                                try:
                                    comprehensive_metrics['current_metrics']['temperature'] = float(day_data['nhiet_do'])
                                    break
                                except ValueError:
                                    pass
                        
                        for day_data in reversed(lenmen_data['data']):
                            if day_data.get('ap_suat'):
                                try:
                                    comprehensive_metrics['current_metrics']['pressure'] = float(day_data['ap_suat'])
                                    break
                                except ValueError:
                                    pass
                    
                    comprehensive_metrics['current_metrics']['last_updated'] = lenmen_data.get('updated_at', 
                        datetime.fromtimestamp(os.path.getmtime(latest_lenmen_file)).isoformat())
                        
            except Exception as e:
                print(f"❌ Error reading lenmen file {latest_lenmen_file}: {e}")
        
        # 3. Lấy thông tin lọc từ LOC logs
        loc_pattern = f"loc_tank{tank_number}_day_*.json"
        loc_files = glob.glob(os.path.join(QA_LOC_DIR, loc_pattern))
        
        total_filtered = 0
        last_filter_date = None
        
        for loc_file in loc_files:
            try:
                with open(loc_file, 'r', encoding='utf-8') as f:
                    loc_data = json.load(f)
                    comprehensive_metrics['data_sources']['loc_files'].append(os.path.basename(loc_file))
                    
                    if 'lo_list' in loc_data and isinstance(loc_data['lo_list'], list):
                        for lo in loc_data['lo_list']:
                            volume = float(lo.get('volume', 0))
                            total_filtered += volume
                    
                    # Ngày lọc gần nhất
                    filter_date = loc_data.get('ngay')
                    if not last_filter_date or (filter_date and filter_date > last_filter_date):
                        last_filter_date = filter_date
                        
            except Exception as e:
                print(f"❌ Error reading loc file {loc_file}: {e}")
                continue
        
        comprehensive_metrics['filtering_info']['total_filtered'] = total_filtered
        comprehensive_metrics['filtering_info']['filter_logs_count'] = len(loc_files)
        comprehensive_metrics['filtering_info']['last_filter_date'] = last_filter_date
        
        # Tính lượng tồn và % đầy
        initial_volume = comprehensive_metrics['batch_info']['total_initial_volume']
        remaining_volume = max(0, initial_volume - total_filtered)
        fill_percentage = (remaining_volume / initial_volume * 100) if initial_volume > 0 else 0
        
        comprehensive_metrics['filtering_info']['remaining_volume'] = remaining_volume
        comprehensive_metrics['filtering_info']['fill_percentage'] = fill_percentage
        
        # Cập nhật status
        if remaining_volume <= 0 and initial_volume > 0:
            comprehensive_metrics['status'] = 'filtered_empty'
        elif initial_volume > 0:
            comprehensive_metrics['status'] = 'active_filtering'
        
        print(f"📊 Tank {tank_number} comprehensive metrics:")
        print(f"   • Status: {comprehensive_metrics['status']}")
        print(f"   • Batches: {comprehensive_metrics['batch_info']['batch_count']}")
        print(f"   • Initial: {initial_volume}L, Filtered: {total_filtered}L, Remaining: {remaining_volume}L")
        print(f"   • Temperature: {comprehensive_metrics['current_metrics']['temperature']}°C")
        
        return jsonify({
            'success': True,
            'tank_metrics': comprehensive_metrics,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error getting comprehensive tank metrics for tank {tank_number}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tank/all-comprehensive-metrics', methods=['GET'])
def get_all_tanks_comprehensive_metrics():
    """Lấy metrics tổng hợp cho tất cả 17 tank"""
    try:
        all_tanks_metrics = []
        
        for tank_num in range(1, 18):  # Tank 1-17
            # Gọi API comprehensive metrics cho từng tank
            response = get_comprehensive_tank_metrics(tank_num)
            if response[1] == 200:  # Success
                response_data = response[0].get_json()
                if response_data.get('success'):
                    all_tanks_metrics.append(response_data['tank_metrics'])
        
        # Tính thống kê tổng quan
        summary = {
            'total_tanks': 17,
            'active_tanks': len([t for t in all_tanks_metrics if t['status'] in ['active', 'active_filtering']]),
            'empty_tanks': len([t for t in all_tanks_metrics if t['status'] == 'empty']),
            'total_volume': sum(t['batch_info']['total_initial_volume'] for t in all_tanks_metrics),
            'total_filtered': sum(t['filtering_info']['total_filtered'] for t in all_tanks_metrics),
            'total_remaining': sum(t['filtering_info']['remaining_volume'] for t in all_tanks_metrics),
            'beer_types': {}
        }
        
        # Thống kê theo loại bia
        for tank in all_tanks_metrics:
            beer_type = tank['batch_info']['beer_type']
            if beer_type:
                if beer_type not in summary['beer_types']:
                    summary['beer_types'][beer_type] = {'tanks': 0, 'volume': 0}
                summary['beer_types'][beer_type]['tanks'] += 1
                summary['beer_types'][beer_type]['volume'] += tank['filtering_info']['remaining_volume']
        
        return jsonify({
            'success': True,
            'tanks_metrics': all_tanks_metrics,
            'summary': summary,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error getting all tanks comprehensive metrics: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API UPLOAD ẢNH (GIỮ NGUYÊN) ====================

@app.route('/api/qa/save-filter-log', methods=['POST'])
def save_filter_log():
    """Lưu nhật ký lọc vào thư mục riêng từ LocScreen"""
    try:
        data = request.get_json()
        tank_number = data.get('tank_number')
        date = data.get('date')
        filename = data.get('filename')
        filter_data = data.get('data')
        
        if not all([tank_number, date, filename, filter_data]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Ensure QA LOC directory exists
        os.makedirs(QA_LOC_DIR, exist_ok=True)
        
        # Save filter log to LOC directory
        filter_path = os.path.join(QA_LOC_DIR, filename)
        with open(filter_path, 'w', encoding='utf-8') as f:
            json.dump(filter_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Saved filter log: {filename} in QA_LOC_DIR")
        print(f"📊 Tank {tank_number} - {len(filter_data.get('lo_list', []))} filter entries")
        
        # If log is closed, trigger batch completion
        if filter_data.get('da_dong', False):
            total_filtered = filter_data.get('total_volume_filtered', 0)
            print(f"🔄 Filter log closed for tank {tank_number}, triggering batch completion...")
            
            # Note: The move-to-completed API will be called separately by the app
        
        return jsonify({
            'success': True,
            'message': f'Filter log saved successfully for tank {tank_number}',
            'filename': filename,
            'saved_to': 'qa/loc/',
            'entries_count': len(filter_data.get('lo_list', [])),
            'total_filtered': filter_data.get('total_volume_filtered', 0),
            'is_closed': filter_data.get('da_dong', False)
        })
        
    except Exception as e:
        print(f"❌ Error saving filter log: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qa/startup-sync', methods=['POST'])
def qa_startup_sync():
    """Đồng bộ toàn bộ dữ liệu QA khi khởi động app"""
    try:
        data = request.get_json()
        client_last_sync = data.get('last_sync')  # Client's last sync timestamp
        
        result = {
            'filter_logs': [],
            'lenmen_logs': [],
            'tank_metrics': [],
            'sync_timestamp': datetime.now().isoformat()
        }
        
        # 1. Sync Filter Logs từ thư mục riêng
        filter_pattern = "loc_tank*_day_*.json"
        filter_files = glob.glob(os.path.join(QA_LOC_DIR, filter_pattern))
        
        for filter_file in filter_files:
            try:
                file_modified = datetime.fromtimestamp(os.path.getmtime(filter_file)).isoformat()
                
                # Only include files modified after client's last sync
                if client_last_sync and file_modified <= client_last_sync:
                    continue
                
                with open(filter_file, 'r', encoding='utf-8') as f:
                    filter_data = json.load(f)
                
                # Extract tank number from filename
                filename = os.path.basename(filter_file)
                tank_match = re.search(r'loc_tank(\d+)_day_', filename)
                tank_number = int(tank_match.group(1)) if tank_match else None
                
                result['filter_logs'].append({
                    'filename': filename,
                    'tank_number': tank_number,
                    'date': filter_data.get('ngay'),
                    'data': filter_data,
                    'modified_at': file_modified
                })
                
            except Exception as e:
                print(f"❌ Error processing filter file {filter_file}: {e}")
                continue
        
        # 2. Sync Lenmen Logs từ thư mục riêng
        lenmen_pattern = "tank_*_day_*.json"
        lenmen_files = glob.glob(os.path.join(QA_LENMEN_DIR, lenmen_pattern))
        
        for lenmen_file in lenmen_files:
            try:
                file_modified = datetime.fromtimestamp(os.path.getmtime(lenmen_file)).isoformat()
                
                if client_last_sync and file_modified <= client_last_sync:
                    continue
                
                with open(lenmen_file, 'r', encoding='utf-8') as f:
                    lenmen_data = json.load(f)
                
                filename = os.path.basename(lenmen_file)
                tank_match = re.search(r'tank_(\d+)_day_', filename)
                tank_number = int(tank_match.group(1)) if tank_match else None
                
                result['lenmen_logs'].append({
                    'filename': filename,
                    'tank_number': tank_number,
                    'date': lenmen_data.get('ngay'),
                    'data': lenmen_data,
                    'modified_at': file_modified
                })
                
            except Exception as e:
                print(f"❌ Error processing lenmen file {lenmen_file}: {e}")
                continue
        
        # 3. Sync Tank Metrics
        if os.path.exists(TANK_METRICS_DIR):
            for metrics_file in os.listdir(TANK_METRICS_DIR):
                if metrics_file.endswith('_metrics.json'):
                    try:
                        metrics_path = os.path.join(TANK_METRICS_DIR, metrics_file)
                        file_modified = datetime.fromtimestamp(os.path.getmtime(metrics_path)).isoformat()
                        
                        if client_last_sync and file_modified <= client_last_sync:
                            continue
                        
                        with open(metrics_path, 'r', encoding='utf-8') as f:
                            metrics_data = json.load(f)
                        
                        result['tank_metrics'].append({
                            'filename': metrics_file,
                            'tank_number': metrics_data.get('tank_number'),
                            'data': metrics_data,
                            'modified_at': file_modified
                        })
                        
                    except Exception as e:
                        print(f"❌ Error processing metrics file {metrics_file}: {e}")
                        continue
        
        print(f"📡 QA Startup Sync completed:")
        print(f"   • Filter logs: {len(result['filter_logs'])}")
        print(f"   • Lenmen logs: {len(result['lenmen_logs'])}")
        print(f"   • Tank metrics: {len(result['tank_metrics'])}")
        
        return jsonify({
            'success': True,
            'message': 'QA startup sync completed',
            'result': result,
            'stats': {
                'filter_logs_count': len(result['filter_logs']),
                'lenmen_logs_count': len(result['lenmen_logs']),
                'tank_metrics_count': len(result['tank_metrics'])
            }
        })
        
    except Exception as e:
        print(f"❌ Error in QA startup sync: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API UPLOAD ẢNH (GIỮ NGUYÊN) ====================

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Upload ảnh từ app mobile"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'Không có file được gửi'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Không có file được chọn'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Định dạng file không được hỗ trợ'}), 400
        
        # Lấy thông tin từ form
        folder = request.form.get('folder', 'Chebien/Plato')
        field_id = request.form.get('fieldId', '')
        batch_id = request.form.get('batchId', '')
        tank_number = request.form.get('tankNumber', '')
        batch_number = request.form.get('batchNumber', '')
        beer_type = request.form.get('beerType', 'river')
        
        # Tạo tên file theo format và beer type
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if beer_type.lower() == 'hanoi':
            filename = f"Hanoi_Tank{tank_number}_Batch{batch_number}_{field_id}_{timestamp}.jpg"
            folder = 'Chebien/Hanoi'
        elif beer_type.lower() == 'chaihg':
            filename = f"ChaiHG_Tank{tank_number}_Batch{batch_number}_{field_id}_{timestamp}.jpg"
            folder = 'Chebien/ChaiHG'
        else:
            filename = f"River_Tank{tank_number}_Batch{batch_number}_{field_id}_{timestamp}.jpg"
            folder = 'Chebien/Plato'
        
        # Tạo đường dẫn thư mục
        full_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(full_folder_path, exist_ok=True)
        
        # Lưu file
        file_path = os.path.join(full_folder_path, filename)
        file.save(file_path)
        
        # Nén ảnh
        compress_image(file_path, quality=80)
        
        # Tạo URL
        image_url = f"/uploads/{folder}/{filename}"
        
        print(f"📷 Image uploaded: {filename} - {beer_type.upper()} Tank: {tank_number}, Batch: {batch_number}")
        
        return jsonify({
            'success': True,
            'message': 'Upload thành công',
            'imageUrl': image_url,
            'fileName': filename,
            'fieldId': field_id,
            'batchId': batch_id,
            'tankNumber': tank_number,
            'batchNumber': batch_number,
            'beerType': beer_type,
            'fileSize': os.path.getsize(file_path)
        })
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({
            'error': 'Lỗi server khi upload ảnh',
            'details': str(e)
        }), 500

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/images/<field_id>/<batch_id>')
def get_batch_images(field_id, batch_id):
    """Lấy danh sách ảnh của một batch"""
    try:
        images = []
        upload_path = app.config['UPLOAD_FOLDER']
        
        # Tìm ảnh trong tất cả thư mục beer type
        beer_dirs = ['Chebien/Plato', 'Chebien/Hanoi', 'Chebien/ChaiHG']
        
        for beer_dir in beer_dirs:
            dir_path = os.path.join(upload_path, beer_dir)
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    if filename.endswith(('.jpg', '.jpeg', '.png')):
                        if f"Batch{batch_id}" in filename and field_id in filename:
                            file_path = os.path.join(dir_path, filename)
                            file_size = os.path.getsize(file_path)
                            
                            images.append({
                                'filename': filename,
                                'url': f"/uploads/{beer_dir}/{filename}",
                                'size': file_size,
                                'beer_type': beer_dir.split('/')[-1],
                                'upload_time': datetime.fromtimestamp(
                                    os.path.getctime(file_path)
                                ).isoformat()
                            })
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images)
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Lỗi khi lấy danh sách ảnh',
            'details': str(e)
        }), 500

# ==================== API THỐNG KÊ VÀ QUẢN LÝ ====================

@app.route('/api/stats/overview', methods=['GET'])
def get_overview_stats():
    """Thống kê tổng quan toàn hệ thống"""
    try:
        stats = {
            'chebien': {
                'active': 0,
                'completed': 0,
                'by_beer_type': {'river': 0, 'hanoi': 0, 'chaihg': 0}
            },
            'qa': {
                'lenmen_logs': 0,
                'filter_logs': 0
            },
            'images': {
                'total': 0,
                'by_beer_type': {'river': 0, 'hanoi': 0, 'chaihg': 0},
                'total_size_mb': 0
            },
            'tanks': {
                'with_active_batches': 0,
                'with_metrics': 0
            }
        }
        
        # Đếm active batches
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json'):
                stats['chebien']['active'] += 1
                try:
                    with open(os.path.join(CHEBIEN_ACTIVE_DIR, filename), 'r') as f:
                        data = json.load(f)
                        beer_type = data.get('beer_type', 'river')
                        stats['chebien']['by_beer_type'][beer_type] += 1
                except:
                    pass
        
        # Đếm completed batches
        for filename in os.listdir(CHEBIEN_COMPLETED_DIR):
            if filename.endswith('.json'):
                stats['chebien']['completed'] += 1
        
        # Đếm QA logs
        for filename in os.listdir(QA_DIR):
            if filename.startswith('tank_') and filename.endswith('.json'):
                stats['qa']['lenmen_logs'] += 1
            elif filename.startswith('loc_tank') and filename.endswith('.json'):
                stats['qa']['filter_logs'] += 1
        
        # Đếm ảnh
        beer_dirs = {
            'Chebien/Plato': 'river',
            'Chebien/Hanoi': 'hanoi', 
            'Chebien/ChaiHG': 'chaihg'
        }
        
        for dir_name, beer_type in beer_dirs.items():
            dir_path = os.path.join(UPLOAD_FOLDER, dir_name)
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    if filename.endswith(('.jpg', '.jpeg', '.png')):
                        stats['images']['total'] += 1
                        stats['images']['by_beer_type'][beer_type] += 1
                        file_path = os.path.join(dir_path, filename)
                        stats['images']['total_size_mb'] += os.path.getsize(file_path) / (1024*1024)
        
        # Đếm tank có active batches
        tanks_with_batches = set()
        for filename in os.listdir(CHEBIEN_ACTIVE_DIR):
            if filename.endswith('.json') and '_tank' in filename:
                try:
                    tank_part = filename.split('_tank')[1]
                    tank_num = int(tank_part.split('_')[0])
                    tanks_with_batches.add(tank_num)
                except:
                    pass
        
        stats['tanks']['with_active_batches'] = len(tanks_with_batches)
        
        # Đếm tank có metrics
        if os.path.exists(TANK_METRICS_DIR):
            metrics_files = [f for f in os.listdir(TANK_METRICS_DIR) if f.startswith('tank_') and f.endswith('_metrics.json')]
            stats['tanks']['with_metrics'] = len(metrics_files)
        
        stats['images']['total_size_mb'] = round(stats['images']['total_size_mb'], 2)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/migrate/old-files', methods=['POST'])
def migrate_old_files():
    """Migration từ cấu trúc cũ sang mới"""
    try:
        # Thư mục cũ
        old_chebien_dir = os.path.join(DATA_DIR, 'chebien')
        
        migrated = 0
        errors = []
        
        # Tìm file với format cũ trong thư mục gốc chebien
        if os.path.exists(old_chebien_dir):
            for filename in os.listdir(old_chebien_dir):
                if filename.endswith('.json') and '__me' in filename:
                    old_path = os.path.join(old_chebien_dir, filename)
                    
                    # Skip nếu là thư mục
                    if os.path.isdir(old_path):
                        continue
                    
                    try:
                        # Đọc file cũ
                        with open(old_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Tạo tên file mới
                        new_filename = generate_new_filename(filename, data)
                        new_path = os.path.join(CHEBIEN_ACTIVE_DIR, new_filename)
                        
                        # Thêm metadata migration
                        data['migrated_at'] = datetime.now().isoformat()
                        data['original_filename'] = filename
                        data['migration_status'] = 'migrated'
                        
                        # Lưu vào active directory
                        with open(new_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
                        # Xóa file cũ
                        os.remove(old_path)
                        migrated += 1
                        
                        print(f"✅ Migrated: {filename} -> {new_filename}")
                        
                    except Exception as e:
                        error_msg = f"Error migrating {filename}: {str(e)}"
                        errors.append(error_msg)
                        print(f"❌ {error_msg}")
        
        return jsonify({
            'success': True,
            'migrated_count': migrated,
            'errors': errors,
            'message': f'Migrated {migrated} files successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_new_filename(old_filename, data):
    """Tạo tên file mới từ format cũ"""
    try:
        # Parse old format: YYYY-MM-DD__meXX__HHMMSS.json
        if '__me' in old_filename and '__' in old_filename:
            parts = old_filename.replace('.json', '').split('__')
            if len(parts) >= 3:
                date_part = parts[0]
                me_part = parts[1].replace('me', '')
                time_part = parts[2]
                
                tank_num = str(data.get('field_003', data.get('tank_so', '01'))).zfill(2)
                me_num = me_part.zfill(2)
                
                return f"{date_part}_me{me_num}_tank{tank_num}_{time_part}.json"
    except:
        pass
    
    # Fallback: tạo tên mới hoàn toàn
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H%M%S')
    
    me_num = str(data.get('field_002', data.get('me_so', '01'))).zfill(2)
    tank_num = str(data.get('field_003', data.get('tank_so', '01'))).zfill(2)
    
    return f"{date_str}_me{me_num}_tank{tank_num}_{time_str}.json"

@app.route('/api/cleanup/old-files', methods=['POST'])
def cleanup_old_files():
    """Dọn dẹp file cũ"""
    try:
        data = request.get_json()
        days_old = data.get('days_old', 90)
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        deleted_files = 0
        freed_space = 0
        
        # Dọn dẹp completed files
        for filename in os.listdir(CHEBIEN_COMPLETED_DIR):
            if filename.endswith('.json'):
                file_path = os.path.join(CHEBIEN_COMPLETED_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                
                if file_time < cutoff_date:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_files += 1
                    freed_space += file_size
                    print(f"🗑️ Deleted old file: {filename}")
        
        # Dọn dẹp ảnh cũ
        beer_dirs = ['Chebien/Plato', 'Chebien/Hanoi', 'Chebien/ChaiHG']
        for beer_dir in beer_dirs:
            dir_path = os.path.join(UPLOAD_FOLDER, beer_dir)
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    if filename.endswith(('.jpg', '.jpeg', '.png')):
                        file_path = os.path.join(dir_path, filename)
                        file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                        
                        if file_time < cutoff_date:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_files += 1
                            freed_space += file_size
        
        return jsonify({
            'success': True,
            'deleted_files': deleted_files,
            'freed_space_mb': round(freed_space / (1024*1024), 2),
            'days_old': days_old,
            'message': f'Deleted {deleted_files} old files'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== API USER MANAGEMENT ====================

@app.route('/api/users', methods=['GET'])
def list_users():
    """Liệt kê tất cả users"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, full_name, department, role, active 
                FROM users 
                ORDER BY username
            ''')
            users = cursor.fetchall()
            
            user_list = []
            for username, full_name, department, role, active in users:
                user_list.append({
                    'username': username,
                    'full_name': full_name,
                    'department': department,
                    'role': role,
                    'active': bool(active)
                })
            
            return jsonify({
                'success': True,
                'users': user_list,
                'count': len(user_list)
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset-users', methods=['POST'])
def reset_users():
    """Reset users với default users"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM users')
            
            default_users = [
                ('chebien1', '123456', 'Nhân viên Chế biến 1', 'chebien', 'staff'),
                ('admin', 'admin123', 'Quản trị viên', 'chebien', 'admin'),
                ('qa1', 'qa123', 'Nhân viên QA', 'qa', 'staff')
            ]
            
            for username, password, full_name, department, role in default_users:
                password_hash = hash_password(password)
                cursor.execute('''
                    INSERT INTO users 
                    (username, password_hash, full_name, department, role, active) 
                    VALUES (?, ?, ?, ?, ?, 1)
                ''', (username, password_hash, full_name, department, role))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Đã reset users thành công',
                'users_created': len(default_users)
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File quá lớn (tối đa 10MB)'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint không tồn tại'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Lỗi server nội bộ'}), 500

# ==================== HEALTH CHECK & INFO ====================

@app.route('/health')
def health_check():
    """Kiểm tra trạng thái server"""
    try:
        # Kiểm tra database
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
        
        # Kiểm tra thư mục
        dirs_status = {
            'chebien_active': os.path.exists(CHEBIEN_ACTIVE_DIR),
            'chebien_completed': os.path.exists(CHEBIEN_COMPLETED_DIR),
            'qa': os.path.exists(QA_DIR),
            'qa_lenmen': os.path.exists(QA_LENMEN_DIR),
            'qa_loc': os.path.exists(QA_LOC_DIR),
            'tank_metrics': os.path.exists(TANK_METRICS_DIR),
            'uploads': os.path.exists(UPLOAD_FOLDER)
        }
        
        # Đếm files
        active_count = len([f for f in os.listdir(CHEBIEN_ACTIVE_DIR) if f.endswith('.json')]) if dirs_status['chebien_active'] else 0
        completed_count = len([f for f in os.listdir(CHEBIEN_COMPLETED_DIR) if f.endswith('.json')]) if dirs_status['chebien_completed'] else 0
        
        # Đếm QA files từ các thư mục riêng
        qa_stats = {'filter_logs': 0, 'lenmen_logs': 0, 'tank_metrics': 0}
        if dirs_status['qa_loc']:
            loc_files = os.listdir(QA_LOC_DIR)
            qa_stats['filter_logs'] = len([f for f in loc_files if f.startswith('loc_tank') and f.endswith('.json')])
        
        if dirs_status['qa_lenmen']:
            lenmen_files = os.listdir(QA_LENMEN_DIR)
            qa_stats['lenmen_logs'] = len([f for f in lenmen_files if f.startswith('tank_') and f.endswith('.json')])
        
        if dirs_status['tank_metrics']:
            qa_stats['tank_metrics'] = len([f for f in os.listdir(TANK_METRICS_DIR) if f.endswith('_metrics.json')])
        
        # Đếm ảnh
        image_count = 0
        beer_dirs = ['Chebien/Plato', 'Chebien/Hanoi', 'Chebien/ChaiHG']
        for beer_dir in beer_dirs:
            dir_path = os.path.join(UPLOAD_FOLDER, beer_dir)
            if os.path.exists(dir_path):
                image_count += len([f for f in os.listdir(dir_path) if f.endswith(('.jpg', '.jpeg', '.png'))])
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '2.1.0',
            'features': [
                'login', 'save_form', 'upload_image', 
                'tank_management', 'qa_logs', 'filter_logs',
                'migration', 'file_management', 'statistics',
                'startup_sync'
            ],
            'directories': dirs_status,
            'stats': {
                'user_count': user_count,
                'active_batches': active_count,
                'completed_batches': completed_count,
                'image_count': image_count,
                'qa_stats': qa_stats
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500

@app.route('/')
def index():
    """Trang chủ API"""
    return jsonify({
        'message': 'IBB Flask Server API v2.1',
        'version': '2.1.0',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            # API Authentication
            'login': 'POST /login',
            'create_user': 'POST /create_user',
            'list_users': 'GET /api/users',
            'reset_users': 'POST /api/reset-users',
            
            # API Chế biến
            'save_form': 'POST /save_form',
            'get_active_batches': 'GET /api/chebien/active/tank/<tank_number>',
            'get_all_active': 'GET /api/chebien/all-active',
            'get_all_completed': 'GET /api/chebien/all-completed',
            'move_to_completed': 'POST /api/chebien/move-to-completed/tank/<tank_number>',
            
            # API QA
            'get_filtered_volume': 'GET /api/qa/filtered-volume/tank/<tank_number>',
            'get_tank_metrics': 'GET /api/qa/tank-metrics/tank/<tank_number>',
            'save_lenmen_log': 'POST /api/qa/lenmen/save',
            'save_filter_log': 'POST /api/qa/save-filter-log',
            'qa_startup_sync': 'POST /api/qa/startup-sync',
            
            # API Upload & Images
            'upload_image': 'POST /api/upload-image',
            'get_batch_images': 'GET /api/images/<field_id>/<batch_id>',
            'serve_uploads': 'GET /uploads/<path:filename>',
            
            # API Management
            'overview_stats': 'GET /api/stats/overview',
            'migrate_files': 'POST /api/migrate/old-files',
            'cleanup_files': 'POST /api/cleanup/old-files',
            'health': 'GET /health'
        },
        'directory_structure': {
            'chebien_active': 'data/chebien/active/',
            'chebien_completed': 'data/chebien/completed/',
            'qa_lenmen_logs': 'data/qa/lenmen/',
            'qa_filter_logs': 'data/qa/loc/',
            'tank_metrics': 'data/tank_metrics/',
            'images': 'uploads/'
        }
    })

if __name__ == '__main__':
    # Tạo directories
    create_directories()
    
    # Tạo database table
    create_user_table()
    
    # Cấu hình logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🍺 IBB Flask Server v2.1 Starting...")
    print("=" * 60)
    print(f"🖥️  Pi User: ibb")
    print(f"📁 Data structure:")
    print(f"   • Active batches: {CHEBIEN_ACTIVE_DIR}")
    print(f"   • Completed batches: {CHEBIEN_COMPLETED_DIR}")
    print(f"   • Lenmen logs: {QA_LENMEN_DIR}")
    print(f"   • Filter logs: {QA_LOC_DIR}")
    print(f"   • Tank metrics: {TANK_METRICS_DIR}")
    print(f"   • Images: {UPLOAD_FOLDER}")
    print(f"💾 Database: {DB_PATH}")
    print(f"📷 Max file size: {MAX_FILE_SIZE // (1024*1024)}MB")
    print(f"🖼️  Supported formats: {', '.join(ALLOWED_EXTENSIONS)}")
    print("=" * 60)
    print("🚀 Server running on http://0.0.0.0:5000")
    print("🔗 Access via: https://api.ibb.vn")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)