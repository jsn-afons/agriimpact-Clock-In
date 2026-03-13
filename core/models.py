from django.db import models
from django.utils import timezone
from datetime import datetime, date

class Employee(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.full_name


class AttendanceRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    is_absent = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['employee', 'date'], name='unique_employee_date')
        ]
        ordering = ['-date', 'employee__last_name']

    @property
    def hours_worked(self):
        if self.time_in and self.time_out:
            # Calculate difference in hours
            in_dt = datetime.combine(date.today(), self.time_in)
            out_dt = datetime.combine(date.today(), self.time_out)
            # handle case where time_out is past midnight (next day)
            if out_dt < in_dt:
                from datetime import timedelta
                out_dt = out_dt + timedelta(days=1)
            diff = out_dt - in_dt
            return round(diff.total_seconds() / 3600.0, 2)
        return 0.0

    def __str__(self):
        return f"{self.employee.full_name} - {self.date}"
