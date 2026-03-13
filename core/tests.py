from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from datetime import time, timedelta
import datetime
from .models import Employee, AttendanceRecord
from django.contrib.auth.models import User


class EmployeeModelTest(TestCase):
    def test_employee_creation_and_str(self):
        """Test creating an employee and its string representation."""
        employee = Employee.objects.create(
            first_name="Jane",
            last_name="Doe",
            department="Engineering"
        )
        self.assertEqual(employee.full_name, "Jane Doe")
        self.assertEqual(str(employee), "Jane Doe")
        self.assertTrue(employee.is_active)

class AttendanceRecordModelTest(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Smith",
            department="Sales"
        )
        self.today = timezone.now().date()

    def test_attendance_creation_and_str(self):
        """Test basic creation and string representation."""
        record = AttendanceRecord.objects.create(
            employee=self.employee,
            date=self.today,
            time_in=time(9, 0),
            time_out=time(17, 0)
        )
        self.assertEqual(str(record), f"John Smith - {self.today}")
        self.assertEqual(record.hours_worked, 8.0)
    
    def test_hours_worked_calculation(self):
        """Test the hours_worked property property."""
        # 8.5 hours
        record1 = AttendanceRecord.objects.create(
            employee=self.employee,
            date=self.today,
            time_in=time(8, 30),
            time_out=time(17, 0)
        )
        self.assertEqual(record1.hours_worked, 8.5)

        # 0 hours active (missing time_out)
        record2 = AttendanceRecord.objects.create(
            employee=self.employee,
            date=self.today + timedelta(days=1),
            time_in=time(9, 0)
        )
        self.assertEqual(record2.hours_worked, 0.0)
        
    def test_hours_worked_after_midnight(self):
        """Test calculation if someone clocks out after midnight."""
        record = AttendanceRecord.objects.create(
            employee=self.employee,
            date=self.today,
            time_in=time(22, 0),
            time_out=time(2, 0) # 4 hours total (10 PM to 2 AM)
        )
        self.assertEqual(record.hours_worked, 4.0)
    
    def test_unique_constraint(self):
        """Test that an employee can only have one record per date."""
        AttendanceRecord.objects.create(
            employee=self.employee,
            date=self.today,
        )
        from django.db.utils import IntegrityError
        with self.assertRaises(IntegrityError):
            AttendanceRecord.objects.create(
                employee=self.employee,
                date=self.today,
            )

class CoreViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client()
        cls.employee1 = Employee.objects.create(
            first_name="Jane", last_name="Doe", department="Engineering", is_active=True
        )
        cls.employee2 = Employee.objects.create(
            first_name="John", last_name="Smith", department="HR", is_active=True
        )
        cls.employee_inactive = Employee.objects.create(
            first_name="Bob", last_name="Ghost", department="Sales", is_active=False
        )
        cls.today = timezone.now().date()

    def setUp(self):
        self.user = User.objects.create_user(username='erica_core', password='testpassword123')
        self.client.force_login(self.user)

    def test_logger_view_status_code_and_context(self):
        """Test the daily logger view returns 200 and correct basic context."""
        url = reverse('core:logger')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'logger.html')
        self.assertIn('today', response.context)
        self.assertIn('form', response.context)

    def test_toggle_attendance_clock_in(self):
        """Test the HTMX toggle endpoint clocks an employee in."""
        url = reverse('core:toggle_attendance', args=[self.employee1.id])
        # HTMX requests are POST
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'partials/employee_card.html')
        
        # Verify database changes
        record = AttendanceRecord.objects.get(employee=self.employee1, date=self.today)
        self.assertIsNotNone(record.time_in)
        self.assertIsNone(record.time_out)

    def test_toggle_attendance_clock_out(self):
        """Test the HTMX toggle endpoint clocks an employee out if already clocked in."""
        # Initial clock in manually setup
        AttendanceRecord.objects.create(employee=self.employee1, date=self.today, time_in=time(9, 0))
        
        # Toggle should clock out
        url = reverse('core:toggle_attendance', args=[self.employee1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        
        # Verify database changes
        record = AttendanceRecord.objects.get(employee=self.employee1, date=self.today)
        self.assertIsNotNone(record.time_out)

    def test_add_employee_ajax_with_sanitation(self):
        """Test the new AJAX endpoint creates an employee and returns the success partial."""
        url = reverse('core:add_employee_ajax')
        data = {
            'first_name': 'Hacker <script>alert(1)</script>',
            'last_name': 'Man',
            'department': '<b>IT</b>'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'partials/instant_clock_in.html')
        
        # Verify employee was created and sanitized
        # Bleach strip=True removes the tags entirely, leaving just the inner content
        new_emp = Employee.objects.get(last_name='Man')
        self.assertEqual(new_emp.first_name, 'Hacker Alert(1)')
        self.assertEqual(new_emp.department, 'It')
        self.assertTrue(new_emp.is_active)

    def test_employee_search_view(self):
        """Test the HTMX search view filters employees correctly."""
        url = reverse('core:employee_search')
        
        # Search for 'doe'
        response = self.client.get(url, {'q': 'doe'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'partials/search_results.html')
        
        # Should contain 'Doe' but not 'Smith'
        self.assertContains(response, 'Doe')
        self.assertNotContains(response, 'Smith')
        
        # Empty search
        response_empty = self.client.get(url, {'q': ''})
        self.assertTemplateUsed(response_empty, 'partials/search_results.html')
        # Based on new logic, empty search returns "No record found" instructions or empty
        self.assertEqual(len(response_empty.context['employee_data']), 0)

class DashboardAnalyticsTest(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(username='erica_dash', password='testpassword123')
        self.client.force_login(self.user)

        self.emp_early = Employee.objects.create(first_name="Early", last_name="Bird", department="Sales", is_active=True)
        self.emp_late = Employee.objects.create(first_name="Late", last_name="Guy", department="Tech", is_active=True)
        self.emp_ghost = Employee.objects.create(first_name="Ghost", last_name="User", department="Ops", is_active=True)
        self.today = timezone.now().date()
        
        # Early bird records (8:00 AM)
        AttendanceRecord.objects.create(employee=self.emp_early, date=self.today, time_in=time(8, 0), time_out=time(17, 0))
        
        # Late guy records (10:00 AM), left early at 4 PM
        AttendanceRecord.objects.create(employee=self.emp_late, date=self.today, time_in=time(10, 0), time_out=time(16, 0))
        
        # Ghost has no records

    def test_dashboard_kpis(self):
        url = reverse('core:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Ghost metric should be 1
        self.assertEqual(response.context['ghost_metric'], 1)
        
        # Early birds should have Emp Early
        early_birds = response.context['early_birds']
        self.assertEqual(early_birds[0]['employee'], self.emp_early)
        
        # Late offenders should have Emp Late first
        late_offenders = response.context['late_offenders']
        self.assertEqual(late_offenders[0]['employee'], self.emp_late)
        
        # Early Departures (left before 5pm) should include Emp Late
        early_deps = response.context['early_departures']
        self.assertIn(self.emp_late, [record.employee for record in early_deps])
        self.assertNotIn(self.emp_early, [record.employee for record in early_deps])

        # Avg hrs spent should be (9 + 6) / 2 = 7.5
        self.assertEqual(response.context['avg_hours_spent'], 7.5)
        
        # Test Chart Context variables
        self.assertIn('chart_punctuality', response.context)
        self.assertIn('chart_overtime', response.context)
        self.assertIn('chart_department', response.context)
        
        # Verify valid JSON-like structures
        self.assertEqual(len(response.context['chart_punctuality']['labels']), 5) # Mon-Fri
        self.assertEqual(len(response.context['chart_punctuality']['data']), 5)
        
        # Emp Early worked 9 hours (1 hr overtime). Emp Late worked 6 hrs (0).
        # Total overtime for the day should be 1.0. (Assuming today falls within Mon-Fri in a standard test env)
        weekday_idx = self.today.weekday()
        if weekday_idx < 5:
            self.assertEqual(response.context['chart_overtime']['data'][weekday_idx], 1.0)
