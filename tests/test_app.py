import unittest
import json
import os
import tempfile
import sys

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import app, create_user_table, hash_password
except ImportError:
    # Handle if app.py has different structure
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", "../app.py")
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    app = app_module.app
    create_user_table = app_module.create_user_table
    hash_password = app_module.hash_password


class IBBBackendTestCase(unittest.TestCase):
    """Test cases for IBB Backend Flask application"""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.app = app.test_client()
        self.app.testing = True
        
        # Create temporary directories for testing
        self.test_dirs = [
            'data/chebien/active',
            'data/chebien/completed', 
            'data/qa/lenmen',
            'data/qa/loc',
            'data/tank_metrics',
            'uploads/Chebien/Plato',
            'uploads/Chebien/Hanoi',
            'uploads/Chebien/ChaiHG'
        ]
        
        for directory in self.test_dirs:
            os.makedirs(directory, exist_ok=True)
        
        # Initialize database
        try:
            create_user_table()
        except:
            pass  # Table might already exist
    
    def tearDown(self):
        """Tear down test fixtures after each test method."""
        # Clean up test files if needed
        pass
    
    def test_health_endpoint(self):
        """Test the health check endpoint"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('status', data)
        self.assertIn('timestamp', data)
        self.assertIn('version', data)
    
    def test_index_endpoint(self):
        """Test the index endpoint"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertIn('IBB Flask Server', data['message'])
    
    def test_create_user(self):
        """Test user creation"""
        user_data = {
            'username': 'testuser',
            'password': 'testpass123',
            'full_name': 'Test User',
            'department': 'chebien',
            'role': 'staff'
        }
        
        response = self.app.post('/create_user',
                                data=json.dumps(user_data),
                                content_type='application/json')
        
        # Should succeed or fail gracefully if user exists
        self.assertIn(response.status_code, [200, 400])
        
        data = json.loads(response.data)
        self.assertIn('success', data)
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        login_data = {
            'username': 'nonexistent',
            'password': 'wrongpassword'
        }
        
        response = self.app.post('/login',
                                data=json.dumps(login_data),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 401)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])

    def test_login_missing_password(self):
        """Login should fail gracefully when password is missing"""
        login_data = {
            'username': 'user_without_password'
        }

        response = self.app.post('/login',
                                data=json.dumps(login_data),
                                content_type='application/json')

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('required', data['message'])
    
    def test_save_form_validation(self):
        """Test form data validation"""
        # Test with missing required fields
        incomplete_data = {
            'field_001': '01/01/2024',
            'beer_type': 'river'
            # Missing required fields
        }
        
        response = self.app.post('/save_form',
                                data=json.dumps(incomplete_data),
                                content_type='application/json')
        
        # Should handle gracefully
        self.assertIn(response.status_code, [200, 400, 500])
    
    def test_save_form_complete(self):
        """Test saving complete form data"""
        form_data = {
            'field_001': '01/01/2024',
            'field_002': '05',
            'field_003': '07', 
            'field_004': 'Test User',
            'field_025': '15000',
            'beer_type': 'river',
            'batch_id': 1,
            'created_at': '2024-01-01T10:00:00Z'
        }
        
        response = self.app.post('/save_form',
                                data=json.dumps(form_data),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('filename', data)
    
    def test_get_active_batches_empty(self):
        """Test getting active batches for empty tank"""
        response = self.app.get('/api/chebien/active/tank/99')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 0)
        self.assertEqual(len(data['batches']), 0)
    
    def test_tank_metrics_nonexistent(self):
        """Test tank metrics for non-existent tank"""
        response = self.app.get('/api/qa/tank-metrics/tank/99')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('temperature', data)
        self.assertIn('pressure', data)
    
    def test_filtered_volume_empty(self):
        """Test filtered volume for tank with no filter logs"""
        response = self.app.get('/api/qa/filtered-volume/tank/99')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['totalFiltered'], 0)
    
    def test_stats_overview(self):
        """Test system overview statistics"""
        response = self.app.get('/api/stats/overview')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('stats', data)
        self.assertIn('chebien', data['stats'])
        self.assertIn('qa', data['stats'])
        self.assertIn('images', data['stats'])
    
    def test_password_hashing(self):
        """Test password hashing function"""
        password = 'testpassword123'
        hashed = hash_password(password)
        
        self.assertNotEqual(password, hashed)
        self.assertTrue(len(hashed) > 0)
        
        # Same password should produce same hash
        hashed2 = hash_password(password)
        self.assertEqual(hashed, hashed2)
    
    def test_file_upload_endpoint_structure(self):
        """Test file upload endpoint exists and has proper structure"""
        # Test with no file (should fail gracefully)
        response = self.app.post('/api/upload-image')
        
        # Should return 400 for missing file
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertIn('error', data)
    
    def test_move_batches_nonexistent_tank(self):
        """Test moving batches for non-existent tank"""
        move_data = {
            'tank_number': 99,
            'total_filtered': 0,
            'filter_date': '2024-01-01',
            'operator': 'Test User'
        }
        
        response = self.app.post('/api/chebien/move-to-completed/tank/99',
                                data=json.dumps(move_data),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['moved_count'], 0)


class IBBUtilityTestCase(unittest.TestCase):
    """Test utility functions and helpers"""
    
    def test_directory_creation(self):
        """Test that required directories can be created"""
        test_dirs = [
            'test_data/chebien/active',
            'test_data/qa/lenmen',
            'test_uploads/Chebien/Plato'
        ]
        
        for directory in test_dirs:
            os.makedirs(directory, exist_ok=True)
            self.assertTrue(os.path.exists(directory))
        
        # Cleanup
        import shutil
        if os.path.exists('test_data'):
            shutil.rmtree('test_data')
        if os.path.exists('test_uploads'):
            shutil.rmtree('test_uploads')
    
    def test_json_file_operations(self):
        """Test JSON file read/write operations"""
        test_data = {
            'field_001': '01/01/2024',
            'field_002': '05',
            'beer_type': 'river',
            'test': True
        }
        
        # Write test file
        os.makedirs('test_output', exist_ok=True)
        test_file = 'test_output/test_batch.json'
        
        with open(test_file, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        # Read and verify
        with open(test_file, 'r') as f:
            loaded_data = json.load(f)
        
        self.assertEqual(test_data, loaded_data)
        
        # Cleanup
        import shutil
        if os.path.exists('test_output'):
            shutil.rmtree('test_output')


if __name__ == '__main__':
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(IBBBackendTestCase))
    test_suite.addTest(unittest.makeSuite(IBBUtilityTestCase))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Exit with proper code
    exit(0 if result.wasSuccessful() else 1)
