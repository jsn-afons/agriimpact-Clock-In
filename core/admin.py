from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Employee, AttendanceRecord

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'department', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('first_name', 'last_name', 'department')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ImportExportModelAdmin):
    list_display = ('employee', 'date', 'time_in', 'time_out', 'hours_worked', 'is_absent')
    list_filter = ('date', 'is_absent', 'employee__department')
    search_fields = ('employee__first_name', 'employee__last_name')
    date_hierarchy = 'date'
