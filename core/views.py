from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.db.models import Avg, Count, F, Q, ExpressionWrapper, fields
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from datetime import timedelta, datetime, time
from django.views.decorators.cache import cache_page
from .models import Employee, AttendanceRecord
from .forms import EmployeeForm

def _get_employee_status(employee, today):
    """Helper to determine the current attendance status of an employee today."""
    record = AttendanceRecord.objects.filter(employee=employee, date=today).first()
    if not record:
        return {'status': 'not_started', 'record': None}
    if record.is_absent:
        return {'status': 'absent', 'record': record}
    if record.time_in and not record.time_out:
        return {'status': 'clocked_in', 'record': record}
    if record.time_in and record.time_out:
        return {'status': 'clocked_out', 'record': record}
    return {'status': 'error', 'record': record}

def signup_view(request):
    """View to handle new user registration."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # Automatically log in upon successful signup
            return HttpResponseRedirect(reverse('core:logger'))
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def logger_view(request):
    """The Daily Logger (Home Page) with active search and add employee."""
    form = EmployeeForm()
    today = timezone.now().date()
    
    context = {
        'today': today,
        'form': form,
    }
    # No longer defaulting to showing the full grid of employees; reliant on search
    return render(request, 'logger.html', context)

@login_required
def employee_search(request):
    """HTMX Active Search endpoint for finding employees to clock in/out."""
    query = request.GET.get('q', '').strip()
    today = timezone.now().date()
    
    if query:
        # Search by first name or last name
        employees = Employee.objects.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query),
            is_active=True
        ).order_by('last_name')[:10] # limit results
    else:
        # Empty search box -> return empty results
        employees = []
        
    employee_data = []
    for emp in employees:
        status_info = _get_employee_status(emp, today)
        employee_data.append({
            'employee': emp,
            'status': status_info['status'],
            'record': status_info['record']
        })
        
    context = {
        'employee_data': employee_data,
        'query': query
    }
    return render(request, 'partials/search_results.html', context)

@login_required
def add_employee_ajax(request):
    """HTMX endpoint to add an employee and prompt to clock them in instantly."""
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            new_employee = form.save()
            # Return the success chunk
            context = {
                'employee': new_employee
            }
            return render(request, 'partials/instant_clock_in.html', context)
        else:
            # 1. Create an empty list to hold our clean error sentences
            error_messages = []
            
            # 2. Loop through the form's error dictionary and extract just the text
            for error_list in form.errors.values():
                for error in error_list:
                    error_messages.append(error)
            
            # 3. Join them into a single string (e.g., "Employee already exists.")
            clean_error_text = " ".join(error_messages)
            
            # 4. Return the clean text
            return HttpResponse(f"<p class='text-red-500 text-sm mt-2'>{clean_error_text}</p>")
    return HttpResponse(status=405)

@login_required
def toggle_attendance(request, employee_id):
    """HTMX endpoint to toggle an employee's attendance status."""
    if request.method != 'POST':
        return HttpResponse(status=405)
        
    employee = get_object_or_404(Employee, id=employee_id, is_active=True)
    today = timezone.now().date()
    now_time = timezone.now().time()
    
    record, created = AttendanceRecord.objects.get_or_create(
        employee=employee,
        date=today,
    )
    
    if created or not record.time_in:
        # Clock in
        record.time_in = now_time
        record.is_absent = False
        record.save()
    elif not record.time_out:
        # Clock out
        record.time_out = now_time
        record.save()
    else:
        # Already clocked out, maybe they are clocking back in? 
        # For this MVP, if they are already clocked out we do nothing, or we can reset.
        # Let's say we do nothing.
        pass
        
    status_info = _get_employee_status(employee, today)
    
    context = {
        'data': {
            'employee': employee,
            'status': status_info['status'],
            'record': status_info['record']
        }
    }
    return render(request, 'partials/employee_card.html', context)

@login_required
@cache_page(60 * 15) # Cache for 15 minutes
def dashboard_view(request):
    """The Analytics Dashboard View"""
    today = timezone.now().date()
    
    # Define current week (assuming Monday start)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    active_employees = Employee.objects.filter(is_active=True)
    active_employees_count = active_employees.count()

    # --- Hero Metrics ---
    
    # 1. Average Arrival Time (for current week)
    records_this_week = AttendanceRecord.objects.filter(
        date__range=[start_of_week, end_of_week], 
        time_in__isnull=False
    )
    
    # Calculate average time_in (Requires some python intervention since Avg on TimeField is tricky across DBs)
    avg_arrival_time = None
    if records_this_week.exists():
        total_seconds = sum((r.time_in.hour * 3600 + r.time_in.minute * 60 + r.time_in.second) for r in records_this_week)
        avg_seconds = total_seconds / records_this_week.count()
        avg_hr, rem = divmod(avg_seconds, 3600)
        avg_min, _ = divmod(rem, 60)
        avg_arrival_time = time(int(avg_hr), int(avg_min)).strftime("%I:%M %p")
    
    # 2. Average Hours Spent (for current week)
    # We calculate on the fly since hours_worked is a property, not a DB column in sqlite
    # If we had a durationfield, we could use ORM Avg. 
    total_hours = sum(r.hours_worked for r in records_this_week)
    avg_hours_spent = round(total_hours / records_this_week.count(), 1) if records_this_week.count() > 0 else 0

    # 3. The Ghost Metric (Count of active employees with NO record today)
    employees_with_records_today = AttendanceRecord.objects.filter(date=today).values_list('employee_id', flat=True)
    ghost_metric = active_employees.exclude(id__in=employees_with_records_today).count()


    # --- Anomaly Reports ---
    # Need to group by employee and aggregate their average times.
    # We do a bit of python processing to keep it DB agnostic since SQLite lacks rich TimeField math
    
    employee_stats = []
    for emp in active_employees:
        emp_records = AttendanceRecord.objects.filter(employee=emp, time_in__isnull=False)
        if not emp_records:
            continue
            
        total_secs = sum((r.time_in.hour * 3600 + r.time_in.minute * 60) for r in emp_records)
        avg_secs = total_secs / emp_records.count()
        employee_stats.append({
            'employee': emp,
            'avg_arrival_seconds': avg_secs,
            'avg_arrival_str': time(int(avg_secs // 3600), int((avg_secs % 3600) // 60)).strftime("%I:%M %p")
        })
        
    employee_stats.sort(key=lambda x: x['avg_arrival_seconds'])
    
    # 1. Early Birds (Top 5 earliest avg arrival)
    early_birds = employee_stats[:5]
    
    # 2. Late Offenders (Top 5 latest avg arrival)
    late_offenders = sorted(employee_stats, key=lambda x: x['avg_arrival_seconds'], reverse=True)[:5]
    
    # 3. Early Departures (Clocked out before 5:00 PM today)
    early_departures = AttendanceRecord.objects.filter(
        date=today,
        time_out__isnull=False,
        time_out__lt=time(17, 0)
    ).select_related('employee')


    context = {
        'avg_arrival_time': avg_arrival_time or "N/A",
        'avg_hours_spent': avg_hours_spent,
        'ghost_metric': ghost_metric,
        'early_birds': early_birds,
        'late_offenders': late_offenders,
        'early_departures': early_departures,
        'today': today,
    }
    
    # --- Chart.js Data Preparation ---
    # We will pass JSON dicts to the template for easy consumption by Chart.js
    
    # Chart 1: Punctuality Trend (Line Chart)
    # X-axis: Days of current week (Mon-Fri)
    # Y-axis: Count of people who arrived before 9:00 AM
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    punctuality_counts = []
    
    for i in range(5): # Mon-Fri
        current_day = start_of_week + timedelta(days=i)
        count = AttendanceRecord.objects.filter(
            date=current_day,
            time_in__isnull=False,
            time_in__lte=time(9, 0)
        ).count()
        punctuality_counts.append(count)
        
    context['chart_punctuality'] = {
        'labels': days_of_week,
        'data': punctuality_counts
    }
    
    # Chart 2: Overtime Heatmap / Bar Chart
    # X-axis: Days of current week
    # Y-axis: Total sum of hours worked beyond 8 hours
    overtime_data = []
    for i in range(5):
        current_day = start_of_week + timedelta(days=i)
        day_records = AttendanceRecord.objects.filter(date=current_day)
        daily_overtime = sum(max(0, r.hours_worked - 8) for r in day_records)
        overtime_data.append(round(daily_overtime, 1))
        
    context['chart_overtime'] = {
        'labels': days_of_week,
        'data': overtime_data
    }
    
    # Chart 3: Department-wise Attendance (Pie Chart)
    # Compare average hours worked per department this week
    dept_stats = {}
    for r in records_this_week:
        dept = r.employee.department
        if dept not in dept_stats:
            dept_stats[dept] = {'total_hours': 0, 'count': 0}
        dept_stats[dept]['total_hours'] += r.hours_worked
        dept_stats[dept]['count'] += 1
        
    dept_labels = list(dept_stats.keys())
    dept_avg_hours = [
        round(stats['total_hours'] / stats['count'], 1) 
        for dept, stats in dept_stats.items()
    ]
    
    context['chart_department'] = {
        'labels': dept_labels,
        'data': dept_avg_hours
    }

    return render(request, 'dashboard.html', context)
