from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.logger_view, name='logger'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('search/', views.employee_search, name='employee_search'),
    path('add-employee/', views.add_employee_ajax, name='add_employee_ajax'),
    path('toggle/<int:employee_id>/', views.toggle_attendance, name='toggle_attendance'),
    path('signup/', views.signup_view, name='signup'),
]
